"""Shared types for compliance bench modules."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Violation:
    rule_id: str
    description: str
    severity: Severity
    category: str
    span: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "severity": self.severity.value,
            "category": self.category,
            "span": list(self.span) if self.span else None,
        }
