"""Batch evaluation of AI outputs against sector compliance rules."""

from __future__ import annotations

import csv
import io
import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from genai_compliance_bench.types import (
    ComplianceResult,
    ComplianceRule,
    EvaluationRecord,
    OutputFormat,
    Severity,
    Violation,
)


@dataclass
class BatchProgress:
    """Tracks progress of a batch evaluation run."""

    total: int
    completed: int = 0
    failed: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def elapsed_s(self) -> float:
        return time.time() - self.start_time

    @property
    def rate(self) -> float:
        """Evaluations per second."""
        if self.elapsed_s == 0:
            return 0.0
        return self.completed / self.elapsed_s

    @property
    def pct_complete(self) -> float:
        if self.total == 0:
            return 100.0
        return (self.completed / self.total) * 100


@dataclass
class AggregateReport:
    """Summary statistics from a batch evaluation."""

    total_evaluated: int
    total_passed: int
    total_failed: int
    pass_rate: float
    violation_distribution: dict[str, int]  # category -> count
    severity_distribution: dict[str, int]  # severity -> count
    risk_heatmap: dict[str, dict[str, int]]  # sector -> category -> count
    elapsed_s: float
    results: list[ComplianceResult]

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self._summary_dict(), indent=indent)

    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "sector",
            "passed",
            "violation_count",
            "max_severity",
            "categories",
            "latency_ms",
        ])
        for r in self.results:
            cats = sorted({v.category for v in r.violations})
            writer.writerow([
                r.sector,
                r.passed,
                r.violation_count,
                r.max_severity.value if r.max_severity else "",
                "; ".join(cats),
                f"{r.latency_ms:.1f}",
            ])
        return buf.getvalue()

    def to_markdown(self) -> str:
        lines = [
            "# Compliance Batch Report",
            "",
            f"**Total evaluated:** {self.total_evaluated}",
            f"**Pass rate:** {self.pass_rate:.1%}",
            f"**Elapsed:** {self.elapsed_s:.2f}s",
            "",
            "## Violation Distribution",
            "",
        ]
        for cat, count in sorted(
            self.violation_distribution.items(), key=lambda x: -x[1]
        ):
            lines.append(f"- **{cat}** — {count}")

        lines += ["", "## Severity Distribution", ""]
        for sev, count in sorted(
            self.severity_distribution.items(), key=lambda x: -x[1]
        ):
            lines.append(f"- **{sev}** — {count}")

        lines += ["", "## Risk Heatmap (sector / category)", ""]
        for sector, cats in sorted(self.risk_heatmap.items()):
            lines.append(f"### {sector}")
            for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
                lines.append(f"- {cat}: {count}")
            lines.append("")

        return "\n".join(lines)

    def format(self, fmt: OutputFormat) -> str:
        dispatch = {
            OutputFormat.JSON: self.to_json,
            OutputFormat.CSV: self.to_csv,
            OutputFormat.MARKDOWN: self.to_markdown,
        }
        return dispatch[fmt]()

    def _summary_dict(self) -> dict[str, Any]:
        return {
            "total_evaluated": self.total_evaluated,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "pass_rate": self.pass_rate,
            "violation_distribution": self.violation_distribution,
            "severity_distribution": self.severity_distribution,
            "risk_heatmap": self.risk_heatmap,
            "elapsed_s": self.elapsed_s,
        }


class BatchEvaluator:
    """Evaluate a dataset of AI outputs against compliance rules.

    Usage::

        rules = [ComplianceRule(...), ...]
        evaluator = BatchEvaluator(rules)
        records = [EvaluationRecord(output="...", sector="financial", context={...})]
        report = evaluator.run(records)
        print(report.to_json())
    """

    def __init__(
        self,
        rules: list[ComplianceRule],
        *,
        max_workers: int = 4,
        on_progress: Callable[[BatchProgress], None] | None = None,
    ) -> None:
        self._rules = rules
        self._rules_by_sector: dict[str, list[ComplianceRule]] = {}
        for rule in rules:
            self._rules_by_sector.setdefault(rule.sector, []).append(rule)
        self._max_workers = max_workers
        self._on_progress = on_progress

    @property
    def sectors(self) -> list[str]:
        return sorted(self._rules_by_sector.keys())

    def evaluate_one(self, record: EvaluationRecord) -> ComplianceResult:
        """Evaluate a single record against all matching sector rules."""
        t0 = time.perf_counter()
        sector_rules = self._rules_by_sector.get(record.sector, [])
        violations = _check_rules(record.output, sector_rules)
        latency_ms = (time.perf_counter() - t0) * 1000

        return ComplianceResult(
            output_text=record.output,
            sector=record.sector,
            context=record.context,
            passed=len(violations) == 0,
            violations=violations,
            latency_ms=latency_ms,
        )

    def run(self, dataset: list[EvaluationRecord]) -> AggregateReport:
        """Run batch evaluation over the full dataset.

        Uses ThreadPoolExecutor for parallelism. Progress callbacks fire
        after each completed evaluation.
        """
        progress = BatchProgress(total=len(dataset))
        results: list[ComplianceResult] = []

        if self._max_workers <= 1:
            for record in dataset:
                result = self.evaluate_one(record)
                results.append(result)
                progress.completed += 1
                self._notify_progress(progress)
        else:
            with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
                futures = {
                    pool.submit(self.evaluate_one, rec): i
                    for i, rec in enumerate(dataset)
                }
                indexed: list[tuple[int, ComplianceResult]] = []
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        result = future.result()
                        indexed.append((idx, result))
                    except Exception:
                        progress.failed += 1
                    progress.completed += 1
                    self._notify_progress(progress)
                # preserve original order
                indexed.sort(key=lambda x: x[0])
                results = [r for _, r in indexed]

        return _build_report(results, progress.elapsed_s)

    def _notify_progress(self, progress: BatchProgress) -> None:
        if self._on_progress is not None:
            self._on_progress(progress)


def _check_rules(text: str, rules: list[ComplianceRule]) -> list[Violation]:
    """Check text against a list of rules, returning all violations found."""
    violations: list[Violation] = []
    text_lower = text.lower()

    for rule in rules:
        # keyword matching
        for kw in rule.keywords:
            if kw.lower() in text_lower:
                violations.append(
                    Violation(
                        rule_id=rule.rule_id,
                        description=f"Keyword match: '{kw}' — {rule.description}",
                        severity=rule.severity,
                        category=rule.category,
                    )
                )
                break  # one violation per rule is enough

        # regex pattern matching
        for pattern in rule.patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                violations.append(
                    Violation(
                        rule_id=rule.rule_id,
                        description=f"Pattern match — {rule.description}",
                        severity=rule.severity,
                        category=rule.category,
                        span=(match.start(), match.end()),
                    )
                )
                break

    return violations


def _build_report(results: list[ComplianceResult], elapsed_s: float) -> AggregateReport:
    """Aggregate individual results into a summary report."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)

    violation_dist: Counter[str] = Counter()
    severity_dist: Counter[str] = Counter()
    heatmap: dict[str, Counter[str]] = {}

    for r in results:
        for v in r.violations:
            violation_dist[v.category] += 1
            severity_dist[v.severity.value] += 1
            sector_counter = heatmap.setdefault(r.sector, Counter())
            sector_counter[v.category] += 1

    return AggregateReport(
        total_evaluated=total,
        total_passed=passed,
        total_failed=total - passed,
        pass_rate=passed / total if total > 0 else 1.0,
        violation_distribution=dict(violation_dist),
        severity_distribution=dict(severity_dist),
        risk_heatmap={s: dict(c) for s, c in heatmap.items()},
        elapsed_s=elapsed_s,
        results=results,
    )
# Updated: 250f8435
