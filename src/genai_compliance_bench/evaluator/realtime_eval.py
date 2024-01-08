"""Lightweight realtime evaluator for deployment pipelines."""

from __future__ import annotations
import re, time
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from genai_compliance_bench.types import ComplianceResult, ComplianceRule, Severity, Violation


@dataclass
class LatencyStats:
    window_size: int = 1000
    _samples: deque[float] = field(default_factory=deque)

    def record(self, ms: float) -> None:
        self._samples.append(ms)
        if len(self._samples) > self.window_size:
            self._samples.popleft()

    @property
    def mean_ms(self) -> float:
        return sum(self._samples) / len(self._samples) if self._samples else 0.0


class RealtimeEvaluator:
    def __init__(self, rules: list[ComplianceRule]) -> None:
        self._rules_by_sector: dict[str, list[ComplianceRule]] = {}
        for rule in rules:
            self._rules_by_sector.setdefault(rule.sector, []).append(rule)
        self.latency_stats = LatencyStats()

    def evaluate(self, output: str, sector: str, context: dict[str, Any] | None = None) -> ComplianceResult:
        ctx = context or {}
        t0 = time.perf_counter()
        rules = self._rules_by_sector.get(sector, [])
        violations: list[Violation] = []
        lower = output.lower()
        for rule in rules:
            for kw in rule.keywords:
                if kw.lower() in lower:
                    violations.append(Violation(rule_id=rule.rule_id, description=f"Keyword: {kw}",
                        severity=rule.severity, category=rule.category))
                    break
        latency = (time.perf_counter() - t0) * 1000
        self.latency_stats.record(latency)
        return ComplianceResult(output_text=output, sector=sector, context=ctx,
            passed=not violations, violations=violations, latency_ms=latency)
