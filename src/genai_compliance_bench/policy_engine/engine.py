"""
Core compliance evaluation engine.

Loads sector-specific rules and checks AI-generated text against them.
Each rule defines a pattern or condition; the engine scores outputs and
collects violations with full audit context.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from genai_compliance_bench.policy_engine.rule_loader import (
    ComplianceRule,
    RuleLoader,
)


class RiskLevel(Enum):
    """Graduated risk classification, not binary pass/fail."""

    CRITICAL = "critical"  # Immediate regulatory exposure
    HIGH = "high"          # Likely violation, needs remediation
    MEDIUM = "medium"      # Potential issue, review recommended
    LOW = "low"            # Minor concern, informational
    NONE = "none"          # No issues detected


# Map severity strings from YAML rules to RiskLevel
_SEVERITY_MAP: dict[str, RiskLevel] = {
    "critical": RiskLevel.CRITICAL,
    "high": RiskLevel.HIGH,
    "medium": RiskLevel.MEDIUM,
    "low": RiskLevel.LOW,
}


@dataclass(frozen=True)
class Violation:
    """A single compliance violation found during evaluation."""

    rule_id: str
    sector: str
    category: str
    severity: RiskLevel
    regulation_ref: str
    description: str
    matched_text: str          # The substring that triggered the violation
    span: tuple[int, int]      # Character offsets (start, end) in the output
    context_snippet: str       # Surrounding text for audit readability


@dataclass
class ComplianceResult:
    """Full result of evaluating one AI output."""

    passed: bool
    violations: list[Violation]
    score: float               # 0.0 (total failure) to 1.0 (clean)
    risk_level: RiskLevel
    explanation: str
    audit_trail: dict[str, Any]

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == RiskLevel.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == RiskLevel.HIGH)


class PolicyEngine:
    """
    Evaluate AI model outputs against sector-specific compliance rules.

    Usage:
        engine = PolicyEngine(benchmarks_dir="benchmarks/")
        engine.load_sector("financial")
        result = engine.evaluate(output_text, sector="financial")
    """

    def __init__(
        self,
        benchmarks_dir: str | Path = "benchmarks",
        *,
        rule_loader: RuleLoader | None = None,
    ) -> None:
        self._benchmarks_dir = Path(benchmarks_dir)
        self._loader = rule_loader or RuleLoader(self._benchmarks_dir)
        # sector -> list of compiled rules
        self._sector_rules: dict[str, list[_CompiledRule]] = {}
        # All loaded sectors
        self._loaded_sectors: set[str] = set()

    # -- Public API ----------------------------------------------------------

    def load_sector(self, sector: str) -> int:
        """
        Load and compile rules for a sector. Returns rule count.
        Idempotent: reloading a sector refreshes its rules.
        """
        raw_rules = self._loader.load_sector(sector)
        compiled = [_compile_rule(r) for r in raw_rules]
        self._sector_rules[sector] = compiled
        self._loaded_sectors.add(sector)
        return len(compiled)

    def load_sectors(self, *sectors: str) -> dict[str, int]:
        """Load multiple sectors. Returns {sector: rule_count}."""
        return {s: self.load_sector(s) for s in sectors}

    @property
    def loaded_sectors(self) -> frozenset[str]:
        return frozenset(self._loaded_sectors)

    def evaluate(
        self,
        output: str,
        sector: str,
        context: dict[str, Any] | None = None,
    ) -> ComplianceResult:
        """
        Evaluate an AI-generated output against loaded rules for the sector.

        Args:
            output: The AI model's text output to check.
            sector: Which sector's rules to apply.
            context: Optional metadata (model_name, prompt, use_case, etc.)
                     that rules can reference for conditional evaluation.

        Returns:
            ComplianceResult with violations, score, and audit trail.
        """
        if sector not in self._sector_rules:
            raise ValueError(
                f"Sector '{sector}' not loaded. "
                f"Call load_sector('{sector}') first. "
                f"Loaded: {sorted(self._loaded_sectors)}"
            )

        ctx = context or {}
        start_ts = time.monotonic()
        violations: list[Violation] = []

        for compiled in self._sector_rules[sector]:
            violations.extend(compiled.check(output, ctx))

        elapsed = time.monotonic() - start_ts
        score = _compute_score(violations, len(self._sector_rules[sector]))
        risk_level = _aggregate_risk(violations)
        passed = risk_level in (RiskLevel.NONE, RiskLevel.LOW)

        explanation = _build_explanation(violations, score, risk_level, sector)

        audit_trail = {
            "sector": sector,
            "rules_evaluated": len(self._sector_rules[sector]),
            "violations_found": len(violations),
            "risk_level": risk_level.value,
            "score": round(score, 4),
            "evaluation_time_ms": round(elapsed * 1000, 2),
            "context": ctx,
            "output_length": len(output),
        }

        return ComplianceResult(
            passed=passed,
            violations=violations,
            score=score,
            risk_level=risk_level,
            explanation=explanation,
            audit_trail=audit_trail,
        )

    def evaluate_multi(
        self,
        output: str,
        sectors: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, ComplianceResult]:
        """Evaluate output against multiple sectors (default: all loaded)."""
        targets = sectors or sorted(self._loaded_sectors)
        return {s: self.evaluate(output, s, context) for s in targets}


# -- Internal: compiled rule wrapper -----------------------------------------


@dataclass
class _CompiledRule:
    """
    A rule with its regex pre-compiled for fast repeated evaluation.
    Some rules use patterns (regex match); others use keyword lists
    or callable conditions.
    """

    rule: ComplianceRule
    # None if the rule has no regex pattern
    pattern: re.Pattern[str] | None
    # Keyword sets for keyword-type rules
    keywords: frozenset[str]
    # If the rule has a `condition` field, we parse it into a callable
    condition_type: str | None  # "contains_any", "exceeds_length", etc.
    condition_params: dict[str, Any]

    def check(self, output: str, context: dict[str, Any]) -> list[Violation]:
        """Run this rule against the output. Returns 0+ violations."""
        # Check context-based gating first: if the rule specifies
        # applicable use_cases, skip if context doesn't match.
        if self.rule.applies_to:
            use_case = context.get("use_case", "")
            if use_case and use_case not in self.rule.applies_to:
                return []

        has_trigger = bool(self.pattern or self.keywords)
        violations: list[Violation] = []

        # Strategy 1: regex pattern matching
        if self.pattern:
            for m in self.pattern.finditer(output):
                violations.append(self._make_violation(
                    matched_text=m.group(),
                    span=(m.start(), m.end()),
                    output=output,
                ))

        # Strategy 2: keyword presence
        if self.keywords:
            output_lower = output.lower()
            for kw in self.keywords:
                idx = 0
                kw_lower = kw.lower()
                while True:
                    pos = output_lower.find(kw_lower, idx)
                    if pos == -1:
                        break
                    end = pos + len(kw)
                    violations.append(self._make_violation(
                        matched_text=output[pos:end],
                        span=(pos, end),
                        output=output,
                    ))
                    idx = end  # advance past this match

        # Strategy 3: structural conditions
        # When a rule has both triggers (pattern/keywords) AND a condition,
        # the condition acts as a modifier: only checked if a trigger matched.
        # When a rule has ONLY a condition, it fires standalone.
        if self.condition_type:
            if not has_trigger or violations:
                cond_violations = self._check_condition(output, context)
                violations.extend(cond_violations)

        return violations

    def _check_condition(
        self, output: str, context: dict[str, Any]
    ) -> list[Violation]:
        """Evaluate non-pattern conditions (length limits, required disclaimers, etc.)."""
        ct = self.condition_type
        params = self.condition_params

        if ct == "missing_disclaimer":
            # Output must contain at least one of the required phrases
            required = params.get("phrases", [])
            output_lower = output.lower()
            if required and not any(p.lower() in output_lower for p in required):
                return [self._make_violation(
                    matched_text="<missing required disclaimer>",
                    span=(0, 0),
                    output=output,
                )]

        elif ct == "exceeds_length":
            max_len = params.get("max_chars", float("inf"))
            if len(output) > max_len:
                return [self._make_violation(
                    matched_text=f"<output length {len(output)} exceeds {max_len}>",
                    span=(0, len(output)),
                    output=output,
                )]

        elif ct == "missing_any_keyword":
            # At least one of these keywords must appear
            required_any = params.get("keywords", [])
            output_lower = output.lower()
            if required_any and not any(
                k.lower() in output_lower for k in required_any
            ):
                return [self._make_violation(
                    matched_text=f"<missing required keyword from: {required_any}>",
                    span=(0, 0),
                    output=output,
                )]

        elif ct == "pii_proximity":
            # Flag when PII-type patterns appear near financial data patterns
            pii_pat = re.compile(
                params.get("pii_pattern", r"\b\d{3}-\d{2}-\d{4}\b")
            )
            fin_pat = re.compile(
                params.get("data_pattern", r"\$[\d,]+\.?\d*")
            )
            pii_matches = list(pii_pat.finditer(output))
            fin_matches = list(fin_pat.finditer(output))
            proximity = params.get("max_char_distance", 200)
            violations = []
            for pm in pii_matches:
                for fm in fin_matches:
                    dist = min(
                        abs(pm.start() - fm.end()),
                        abs(fm.start() - pm.end()),
                    )
                    if dist <= proximity:
                        violations.append(self._make_violation(
                            matched_text=pm.group(),
                            span=(pm.start(), pm.end()),
                            output=output,
                        ))
                        break  # One violation per PII match is enough
            return violations

        return []

    def _make_violation(
        self,
        matched_text: str,
        span: tuple[int, int],
        output: str,
    ) -> Violation:
        snippet_start = max(0, span[0] - 40)
        snippet_end = min(len(output), span[1] + 40)
        snippet = output[snippet_start:snippet_end]
        if snippet_start > 0:
            snippet = "..." + snippet
        if snippet_end < len(output):
            snippet = snippet + "..."

        return Violation(
            rule_id=self.rule.id,
            sector=self.rule.sector,
            category=self.rule.category,
            severity=_SEVERITY_MAP.get(self.rule.severity, RiskLevel.MEDIUM),
            regulation_ref=self.rule.regulation_ref,
            description=self.rule.description,
            matched_text=matched_text,
            span=span,
            context_snippet=snippet,
        )


def _compile_rule(rule: ComplianceRule) -> _CompiledRule:
    """Pre-compile a rule's pattern and parse its condition."""
    pattern = None
    if rule.pattern:
        flags = re.IGNORECASE if rule.case_insensitive else 0
        pattern = re.compile(rule.pattern, flags)

    keywords = frozenset(rule.keywords) if rule.keywords else frozenset()

    condition_type = None
    condition_params: dict[str, Any] = {}
    if rule.condition:
        condition_type = rule.condition.get("type")
        condition_params = {
            k: v for k, v in rule.condition.items() if k != "type"
        }

    return _CompiledRule(
        rule=rule,
        pattern=pattern,
        keywords=keywords,
        condition_type=condition_type,
        condition_params=condition_params,
    )


# -- Scoring and risk aggregation -------------------------------------------


# Weight violations by severity when computing the score
_SEVERITY_WEIGHTS: dict[RiskLevel, float] = {
    RiskLevel.CRITICAL: 1.0,
    RiskLevel.HIGH: 0.6,
    RiskLevel.MEDIUM: 0.3,
    RiskLevel.LOW: 0.1,
}


def _compute_score(violations: list[Violation], total_rules: int) -> float:
    """
    Score from 0.0 (worst) to 1.0 (clean).
    Weighted by violation severity relative to total rules evaluated.
    A single critical violation tanks the score hard.
    """
    if total_rules == 0:
        return 1.0
    if not violations:
        return 1.0

    weighted_penalty = sum(
        _SEVERITY_WEIGHTS.get(v.severity, 0.3) for v in violations
    )
    # Normalize: penalty of total_rules means score 0
    raw = 1.0 - (weighted_penalty / total_rules)
    return max(0.0, min(1.0, round(raw, 4)))


def _aggregate_risk(violations: list[Violation]) -> RiskLevel:
    """Overall risk is the worst severity found."""
    if not violations:
        return RiskLevel.NONE

    severity_order = [
        RiskLevel.CRITICAL, RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW
    ]
    found = {v.severity for v in violations}
    for level in severity_order:
        if level in found:
            return level
    return RiskLevel.LOW


def _build_explanation(
    violations: list[Violation],
    score: float,
    risk_level: RiskLevel,
    sector: str,
) -> str:
    """One-paragraph summary suitable for a compliance review."""
    if not violations:
        return (
            f"Output passed all {sector} compliance checks. "
            f"Score: {score:.2f}. No violations detected."
        )

    counts_by_sev = {}
    for v in violations:
        counts_by_sev[v.severity.value] = counts_by_sev.get(v.severity.value, 0) + 1

    counts_str = ", ".join(f"{cnt} {sev}" for sev, cnt in counts_by_sev.items())
    regs = sorted({v.regulation_ref for v in violations if v.regulation_ref})
    regs_str = f" Relevant regulations: {', '.join(regs)}." if regs else ""

    return (
        f"Output flagged {len(violations)} violation(s) in {sector} compliance "
        f"({counts_str}). Overall risk: {risk_level.value}. "
        f"Score: {score:.2f}.{regs_str}"
    )
