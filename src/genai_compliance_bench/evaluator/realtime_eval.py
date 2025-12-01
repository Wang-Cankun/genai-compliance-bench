"""Lightweight realtime evaluator for ML deployment pipelines."""

from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from genai_compliance_bench.types import (
    ComplianceResult,
    ComplianceRule,
    Severity,
    Violation,
)


@dataclass
class LatencyStats:
    """Rolling latency statistics over a fixed window."""

    window_size: int = 1000
    _samples: deque[float] = field(default_factory=deque)

    def record(self, ms: float) -> None:
        self._samples.append(ms)
        if len(self._samples) > self.window_size:
            self._samples.popleft()

    @property
    def count(self) -> int:
        return len(self._samples)

    @property
    def mean_ms(self) -> float:
        if not self._samples:
            return 0.0
        return sum(self._samples) / len(self._samples)

    @property
    def p50_ms(self) -> float:
        return self._percentile(50)

    @property
    def p95_ms(self) -> float:
        return self._percentile(95)

    @property
    def p99_ms(self) -> float:
        return self._percentile(99)

    def to_dict(self) -> dict[str, float]:
        return {
            "count": self.count,
            "mean_ms": round(self.mean_ms, 3),
            "p50_ms": round(self.p50_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "p99_ms": round(self.p99_ms, 3),
        }

    def _percentile(self, pct: float) -> float:
        if not self._samples:
            return 0.0
        s = sorted(self._samples)
        idx = int(len(s) * pct / 100)
        idx = min(idx, len(s) - 1)
        return s[idx]


class RealtimeEvaluator:
    """Single-output compliance evaluator for deployment pipelines.

    Designed for low overhead. Call ``evaluate()`` synchronously or
    ``evaluate_async()`` from an asyncio context.

    Usage::

        rules = [ComplianceRule(...)]
        rt = RealtimeEvaluator(rules)
        result = rt.evaluate("Some AI output", sector="financial", context={})
        print(result.passed, result.violations)
        print(rt.latency_stats.to_dict())
    """

    def __init__(
        self,
        rules: list[ComplianceRule],
        *,
        latency_window: int = 1000,
    ) -> None:
        self._rules_by_sector: dict[str, list[ComplianceRule]] = {}
        for rule in rules:
            self._rules_by_sector.setdefault(rule.sector, []).append(rule)
        self.latency_stats = LatencyStats(window_size=latency_window)

    @property
    def sectors(self) -> list[str]:
        return sorted(self._rules_by_sector.keys())

    def evaluate(
        self,
        output: str,
        sector: str,
        context: dict[str, Any] | None = None,
    ) -> ComplianceResult:
        """Evaluate a single AI output against sector rules.

        Returns a ComplianceResult with pass/fail status, violations,
        and latency measurement.
        """
        ctx = context or {}
        t0 = time.perf_counter()
        rules = self._rules_by_sector.get(sector, [])
        violations = _check_rules_fast(output, rules)
        latency_ms = (time.perf_counter() - t0) * 1000
        self.latency_stats.record(latency_ms)

        return ComplianceResult(
            output_text=output,
            sector=sector,
            context=ctx,
            passed=len(violations) == 0,
            violations=violations,
            latency_ms=latency_ms,
        )

    async def evaluate_async(
        self,
        output: str,
        sector: str,
        context: dict[str, Any] | None = None,
    ) -> ComplianceResult:
        """Async wrapper around evaluate().

        Runs the synchronous evaluation in the default executor to avoid
        blocking the event loop on large rule sets.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self.evaluate, output, sector, context
        )


def _check_rules_fast(text: str, rules: list[ComplianceRule]) -> list[Violation]:
    """Check text against rules. Optimized for single-output latency.

    Stops accumulating violations from the same rule after the first match.
    Pre-lowercases the text once.
    """
    violations: list[Violation] = []
    text_lower = text.lower()

    for rule in rules:
        found = False

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
                found = True
                break

        if found:
            continue

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
