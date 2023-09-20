"""Shared types used across evaluator, learner, and policy_engine modules."""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OutputFormat(Enum):
    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


@dataclass
class Violation:
    rule_id: str
    description: str
    severity: Severity
    category: str
    span: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "description": self.description,
                "severity": self.severity.value, "category": self.category,
                "span": list(self.span) if self.span else None}


@dataclass
class ComplianceResult:
    output_text: str
    sector: str
    context: dict[str, Any]
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    evaluated_at: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    @property
    def max_severity(self) -> Severity | None:
        if not self.violations:
            return None
        order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        return max(self.violations, key=lambda v: order.index(v.severity)).severity

    def to_dict(self) -> dict[str, Any]:
        return {"output_text": self.output_text, "sector": self.sector,
                "context": self.context, "passed": self.passed,
                "violations": [v.to_dict() for v in self.violations],
                "violation_count": self.violation_count,
                "max_severity": self.max_severity.value if self.max_severity else None,
                "evaluated_at": self.evaluated_at, "latency_ms": self.latency_ms,
                "metadata": self.metadata}
