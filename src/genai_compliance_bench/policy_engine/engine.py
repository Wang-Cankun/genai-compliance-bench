"""Core compliance evaluation engine.

Loads sector-specific rules and checks AI-generated text against them.
Each rule defines a pattern or condition; the engine scores outputs and
collects violations with full audit context.
"""

from __future__ import annotations
import re, time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from genai_compliance_bench.policy_engine.rule_loader import ComplianceRule, RuleLoader


class RiskLevel(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"

_SEVERITY_MAP: dict[str, RiskLevel] = {
    "critical": RiskLevel.CRITICAL, "high": RiskLevel.HIGH,
    "medium": RiskLevel.MEDIUM, "low": RiskLevel.LOW,
}

@dataclass(frozen=True)
class Violation:
    rule_id: str
    sector: str
    category: str
    severity: RiskLevel
    regulation_ref: str
    description: str
    matched_text: str
    span: tuple[int, int]
    context_snippet: str

@dataclass
class ComplianceResult:
    passed: bool
    violations: list[Violation]
    score: float
    risk_level: RiskLevel
    explanation: str
    audit_trail: dict[str, Any]

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == RiskLevel.CRITICAL)

_SEVERITY_WEIGHTS: dict[RiskLevel, float] = {
    RiskLevel.CRITICAL: 1.0, RiskLevel.HIGH: 0.6,
    RiskLevel.MEDIUM: 0.3, RiskLevel.LOW: 0.1,
}

class PolicyEngine:
    def __init__(self, benchmarks_dir: str | Path = "benchmarks", *, rule_loader: RuleLoader | None = None) -> None:
        self._benchmarks_dir = Path(benchmarks_dir)
        self._loader = rule_loader or RuleLoader(self._benchmarks_dir)
        self._sector_rules: dict[str, list[ComplianceRule]] = {}
        self._loaded_sectors: set[str] = set()

    def load_sector(self, sector: str) -> int:
        raw = self._loader.load_sector(sector)
        self._sector_rules[sector] = raw
        self._loaded_sectors.add(sector)
        return len(raw)

    def load_sectors(self, *sectors: str) -> dict[str, int]:
        return {s: self.load_sector(s) for s in sectors}

    @property
    def loaded_sectors(self) -> frozenset[str]:
        return frozenset(self._loaded_sectors)

    def evaluate(self, output: str, sector: str, context: dict[str, Any] | None = None) -> ComplianceResult:
        if sector not in self._sector_rules:
            raise ValueError(f"Sector \'{sector}\' not loaded.")
        ctx = context or {}
        start = time.monotonic()
        violations: list[Violation] = []
        for rule in self._sector_rules[sector]:
            violations.extend(self._check_rule(rule, output))
        elapsed = time.monotonic() - start
        score = self._compute_score(violations, len(self._sector_rules[sector]))
        risk = self._aggregate_risk(violations)
        passed = risk in (RiskLevel.NONE, RiskLevel.LOW)
        expl = self._build_explanation(violations, score, risk, sector)
        return ComplianceResult(passed=passed, violations=violations, score=score,
            risk_level=risk, explanation=expl, audit_trail={
                "sector": sector, "rules_evaluated": len(self._sector_rules[sector]),
                "violations_found": len(violations), "risk_level": risk.value,
                "score": round(score, 4), "evaluation_time_ms": round(elapsed * 1000, 2),
                "context": ctx, "output_length": len(output)})

    def _check_rule(self, rule, output):
        violations = []
        if rule.keywords:
            lower = output.lower()
            for kw in rule.keywords:
                idx = 0
                while True:
                    pos = lower.find(kw.lower(), idx)
                    if pos == -1:
                        break
                    end = pos + len(kw)
                    violations.append(self._make_violation(rule, output[pos:end], (pos, end), output))
                    idx = end
        if rule.pattern:
            flags = re.IGNORECASE if rule.case_insensitive else 0
            for m in re.finditer(rule.pattern, output, flags):
                violations.append(self._make_violation(rule, m.group(), (m.start(), m.end()), output))
        return violations

    def _make_violation(self, rule, matched, span, output):
        s = max(0, span[0] - 40)
        e = min(len(output), span[1] + 40)
        snippet = ("..." if s > 0 else "") + output[s:e] + ("..." if e < len(output) else "")
        return Violation(rule.id, rule.sector, rule.category,
            _SEVERITY_MAP.get(rule.severity, RiskLevel.MEDIUM),
            rule.regulation_ref, rule.description, matched, span, snippet)

    def _compute_score(self, violations, total):
        if not total or not violations:
            return 1.0
        penalty = sum(_SEVERITY_WEIGHTS.get(v.severity, 0.3) for v in violations)
        return max(0.0, min(1.0, round(1.0 - penalty / total, 4)))

    def _aggregate_risk(self, violations):
        if not violations:
            return RiskLevel.NONE
        for level in [RiskLevel.CRITICAL, RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW]:
            if any(v.severity == level for v in violations):
                return level
        return RiskLevel.LOW

    @staticmethod
    def _build_explanation(violations, score, risk, sector):
        if not violations:
            return f"Output passed all {sector} compliance checks. Score: {score:.2f}."
        counts = {}
        for v in violations:
            counts[v.severity.value] = counts.get(v.severity.value, 0) + 1
        counts_str = ", ".join(f"{c} {s}" for s, c in counts.items())
        regs = sorted({v.regulation_ref for v in violations if v.regulation_ref})
        regs_str = f" Relevant regulations: {', '.join(regs)}." if regs else ""
        return f"Output flagged {len(violations)} violation(s) in {sector} ({counts_str}). Risk: {risk.value}. Score: {score:.2f}.{regs_str}"
