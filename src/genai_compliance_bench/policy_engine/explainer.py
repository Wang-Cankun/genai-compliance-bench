"""Generate human-readable compliance explanations."""

from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from genai_compliance_bench.policy_engine.engine import ComplianceResult, RiskLevel, Violation


class ComplianceExplainer:
    def __init__(self, *, include_snippets: bool = True) -> None:
        self._include_snippets = include_snippets

    def explain(self, result: ComplianceResult) -> str:
        lines = [f"Risk Level: {result.risk_level.value.upper()}",
                 f"Score: {result.score:.2f}/1.00",
                 f"Violations: {len(result.violations)}", ""]
        if not result.violations:
            lines.append("No compliance issues detected.")
            return "\n".join(lines)
        by_cat: dict[str, list] = defaultdict(list)
        for v in result.violations:
            by_cat[v.category].append(v)
        for cat, vs in sorted(by_cat.items()):
            lines.append(f"[{cat}]")
            for v in vs:
                lines.append(f"  - [{v.severity.value.upper()}] {v.description}")
            lines.append("")
        return "\n".join(lines)
