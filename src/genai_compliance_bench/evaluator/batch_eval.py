"""Batch evaluation of AI outputs."""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any
from genai_compliance_bench.types import ComplianceResult, ComplianceRule, EvaluationRecord, Severity, Violation


@dataclass
class BatchProgress:
    total: int
    completed: int = 0
    failed: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def elapsed_s(self) -> float:
        return time.time() - self.start_time


class BatchEvaluator:
    def __init__(self, rules: list[ComplianceRule]) -> None:
        self._rules = rules
        self._rules_by_sector: dict[str, list[ComplianceRule]] = {}
        for rule in rules:
            self._rules_by_sector.setdefault(rule.sector, []).append(rule)

    def evaluate_one(self, record: EvaluationRecord) -> ComplianceResult:
        t0 = time.perf_counter()
        latency = (time.perf_counter() - t0) * 1000
        return ComplianceResult(output_text=record.output, sector=record.sector,
            context=record.context, passed=True, latency_ms=latency)
