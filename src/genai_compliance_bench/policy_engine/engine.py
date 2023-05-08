"""Core compliance evaluation engine."""

from __future__ import annotations
import re, time
from dataclasses import dataclass
from typing import Any
from genai_compliance_bench.policy_engine.rule_loader import ComplianceRule, RuleLoader


@dataclass(frozen=True)
class Violation:
    rule_id: str
    sector: str
    category: str
    severity: str
    description: str
    matched_text: str
    span: tuple[int, int]


@dataclass
class ComplianceResult:
    passed: bool
    violations: list[Violation]
    score: float
    explanation: str
    audit_trail: dict[str, Any]


class PolicyEngine:
    def __init__(self, benchmarks_dir: str = "benchmarks") -> None:
        self._loader = RuleLoader(benchmarks_dir)
        self._sector_rules: dict[str, list[ComplianceRule]] = {}
        self._loaded_sectors: set[str] = set()

    def load_sector(self, sector: str) -> int:
        raw = self._loader.load_sector(sector)
        self._sector_rules[sector] = raw
        self._loaded_sectors.add(sector)
        return len(raw)

    @property
    def loaded_sectors(self) -> frozenset[str]:
        return frozenset(self._loaded_sectors)

    def evaluate(self, output: str, sector: str, context: dict[str, Any] | None = None) -> ComplianceResult:
        if sector not in self._sector_rules:
            raise ValueError(f"Sector not loaded: {sector}")
        start = time.monotonic()
        violations = []
        for rule in self._sector_rules[sector]:
            if rule.keywords:
                lower = output.lower()
                for kw in rule.keywords:
                    if kw.lower() in lower:
                        pos = lower.find(kw.lower())
                        violations.append(Violation(rule.id, rule.sector, rule.category,
                            rule.severity, rule.description, kw, (pos, pos + len(kw))))
            if rule.pattern:
                flags = re.IGNORECASE if rule.case_insensitive else 0
                for m in re.finditer(rule.pattern, output, flags):
                    violations.append(Violation(rule.id, rule.sector, rule.category,
                        rule.severity, rule.description, m.group(), (m.start(), m.end())))
        elapsed = time.monotonic() - start
        total = max(len(self._sector_rules[sector]), 1)
        score = max(0.0, 1.0 - len(violations) / total)
        expl = f"Output passed all {sector} checks." if not violations else f"{len(violations)} violation(s) in {sector}."
        return ComplianceResult(passed=not violations, violations=violations, score=score,
            explanation=expl, audit_trail={"sector": sector, "rules_evaluated": total,
            "violations_found": len(violations), "evaluation_time_ms": round(elapsed * 1000, 2)})
