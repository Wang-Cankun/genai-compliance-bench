"""
Generate human-readable compliance explanations and audit reports.

This is NOT a binary pass/fail reporter. Every assessment includes graduated
risk levels, specific regulation references, and actionable remediation guidance.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from genai_compliance_bench.policy_engine.engine import (
    ComplianceResult,
    RiskLevel,
    Violation,
)


# Regulation metadata: short descriptions for audit reports
_REGULATION_INFO: dict[str, _RegInfo] = {}


@dataclass(frozen=True)
class _RegInfo:
    full_name: str
    authority: str
    summary: str


# Populated at module load
_REGULATIONS: dict[str, _RegInfo] = {
    "SOX": _RegInfo(
        full_name="Sarbanes-Oxley Act",
        authority="SEC",
        summary="Financial reporting accuracy and internal controls for public companies.",
    ),
    "SOX-302": _RegInfo(
        full_name="SOX Section 302 - Corporate Responsibility",
        authority="SEC",
        summary="CEO/CFO certification of financial report accuracy.",
    ),
    "SOX-404": _RegInfo(
        full_name="SOX Section 404 - Internal Controls",
        authority="SEC",
        summary="Assessment of internal control over financial reporting.",
    ),
    "PCI-DSS": _RegInfo(
        full_name="Payment Card Industry Data Security Standard",
        authority="PCI SSC",
        summary="Security standards for organizations handling cardholder data.",
    ),
    "PCI-DSS-3.4": _RegInfo(
        full_name="PCI-DSS Requirement 3.4 - Render PAN Unreadable",
        authority="PCI SSC",
        summary="Primary account numbers must be rendered unreadable anywhere they are stored.",
    ),
    "GLBA": _RegInfo(
        full_name="Gramm-Leach-Bliley Act",
        authority="FTC",
        summary="Financial institutions must explain information-sharing practices and safeguard sensitive data.",
    ),
    "GLBA-501": _RegInfo(
        full_name="GLBA Section 501 - Protection of NPI",
        authority="FTC",
        summary="Standards for safeguarding nonpublic personal information.",
    ),
    "FCC-222": _RegInfo(
        full_name="FCC Section 222 - CPNI",
        authority="FCC",
        summary="Telecommunications carriers must protect Customer Proprietary Network Information.",
    ),
    "FCC-64": _RegInfo(
        full_name="47 CFR Part 64 - CPNI Rules",
        authority="FCC",
        summary="Detailed rules governing use and disclosure of CPNI.",
    ),
    "HIPAA": _RegInfo(
        full_name="Health Insurance Portability and Accountability Act",
        authority="HHS",
        summary="Privacy and security standards for protected health information.",
    ),
    "HIPAA-164.502": _RegInfo(
        full_name="HIPAA Privacy Rule - Uses and Disclosures",
        authority="HHS OCR",
        summary="Permitted and required uses/disclosures of PHI.",
    ),
    "HIPAA-164.312": _RegInfo(
        full_name="HIPAA Security Rule - Technical Safeguards",
        authority="HHS OCR",
        summary="Technical measures to protect electronic PHI.",
    ),
    "TCPA": _RegInfo(
        full_name="Telephone Consumer Protection Act",
        authority="FCC",
        summary="Restrictions on telemarketing calls, auto-dialers, and pre-recorded messages.",
    ),
    "FCRA": _RegInfo(
        full_name="Fair Credit Reporting Act",
        authority="FTC / CFPB",
        summary="Accuracy, fairness, and privacy of consumer credit information.",
    ),
    "GDPR-Art.22": _RegInfo(
        full_name="GDPR Article 22 - Automated Decision-Making",
        authority="EU DPA",
        summary="Right not to be subject to decisions based solely on automated processing.",
    ),
}


class ComplianceExplainer:
    """
    Turn raw ComplianceResults into structured, audit-ready reports.

    Reports include:
    - Graduated risk assessment (not binary)
    - Per-violation regulation mapping with context
    - Remediation suggestions per category
    - JSON and Markdown output formats
    """

    def __init__(self, *, include_snippets: bool = True) -> None:
        self._include_snippets = include_snippets

    # -- Public API ----------------------------------------------------------

    def explain(self, result: ComplianceResult) -> str:
        """Return a plain-text explanation with regulation context."""
        lines: list[str] = []
        lines.append(f"Risk Level: {result.risk_level.value.upper()}")
        lines.append(f"Score: {result.score:.2f}/1.00")
        lines.append(f"Violations: {len(result.violations)}")
        lines.append("")

        if not result.violations:
            lines.append("No compliance issues detected.")
            return "\n".join(lines)

        # Group by category
        by_cat = self._group_by_category(result.violations)
        for cat, violations in sorted(by_cat.items()):
            lines.append(f"[{cat}]")
            for v in violations:
                lines.append(f"  - [{v.severity.value.upper()}] {v.description}")
                lines.append(f"    Rule: {v.rule_id}")
                if v.regulation_ref:
                    reg_detail = self._regulation_detail(v.regulation_ref)
                    lines.append(f"    Regulation: {v.regulation_ref} ({reg_detail})")
                if self._include_snippets and v.matched_text:
                    display = v.matched_text[:80]
                    if len(v.matched_text) > 80:
                        display += "..."
                    lines.append(f"    Matched: {display}")
            lines.append("")

        # Remediation summary
        lines.append("Remediation:")
        remediations = self._suggest_remediations(result.violations)
        for action in remediations:
            lines.append(f"  - {action}")

        return "\n".join(lines)

    def to_json(
        self,
        result: ComplianceResult,
        *,
        model_id: str = "",
        run_id: str = "",
    ) -> str:
        """
        Generate an audit-ready JSON report.

        Designed for ingestion by compliance dashboards, SIEM systems,
        or audit trail databases.
        """
        report = self._build_report_dict(result, model_id, run_id)
        return json.dumps(report, indent=2, default=str)

    def to_markdown(
        self,
        result: ComplianceResult,
        *,
        model_id: str = "",
        run_id: str = "",
    ) -> str:
        """Generate a Markdown report suitable for review documentation."""
        report = self._build_report_dict(result, model_id, run_id)
        lines: list[str] = []

        lines.append(f"# Compliance Assessment Report")
        lines.append("")
        if run_id:
            lines.append(f"**Run ID:** {run_id}")
        if model_id:
            lines.append(f"**Model:** {model_id}")
        lines.append(f"**Timestamp:** {report['timestamp']}")
        lines.append(f"**Sector:** {report['sector']}")
        lines.append("")

        # Summary table as a list (no markdown tables per style rules)
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Risk Level** -- {result.risk_level.value.upper()}")
        lines.append(f"- **Score** -- {result.score:.2f}/1.00")
        lines.append(f"- **Passed** -- {'Yes' if result.passed else 'No'}")
        lines.append(f"- **Violations** -- {len(result.violations)}")
        lines.append(f"- **Rules Evaluated** -- {report['rules_evaluated']}")
        lines.append("")

        if not result.violations:
            lines.append("No compliance violations detected.")
            return "\n".join(lines)

        # Violations by category
        lines.append("## Violations")
        lines.append("")
        by_cat = self._group_by_category(result.violations)
        for cat, violations in sorted(by_cat.items()):
            lines.append(f"### {cat}")
            lines.append("")
            for v in violations:
                sev_badge = self._severity_badge(v.severity)
                lines.append(f"- {sev_badge} **{v.rule_id}**: {v.description}")
                if v.regulation_ref:
                    reg = self._regulation_detail(v.regulation_ref)
                    lines.append(f"  - Regulation: {v.regulation_ref} -- {reg}")
                if self._include_snippets and v.matched_text:
                    safe_text = v.matched_text[:100].replace("`", "'")
                    lines.append(f"  - Matched: `{safe_text}`")
            lines.append("")

        # Regulation reference appendix
        refs = sorted({v.regulation_ref for v in result.violations if v.regulation_ref})
        if refs:
            lines.append("## Regulation References")
            lines.append("")
            for ref in refs:
                info = _REGULATIONS.get(ref)
                if info:
                    lines.append(f"- **{ref}** -- {info.full_name} ({info.authority}): {info.summary}")
                else:
                    lines.append(f"- **{ref}** -- (no additional information available)")
            lines.append("")

        # Remediation
        lines.append("## Recommended Remediation")
        lines.append("")
        for action in self._suggest_remediations(result.violations):
            lines.append(f"- {action}")

        return "\n".join(lines)

    # -- Internal ------------------------------------------------------------

    def _build_report_dict(
        self,
        result: ComplianceResult,
        model_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        """Common structure used by both JSON and Markdown output."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "model_id": model_id,
            "sector": result.audit_trail.get("sector", "unknown"),
            "rules_evaluated": result.audit_trail.get("rules_evaluated", 0),
            "risk_level": result.risk_level.value,
            "score": round(result.score, 4),
            "passed": result.passed,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "sector": v.sector,
                    "category": v.category,
                    "severity": v.severity.value,
                    "description": v.description,
                    "regulation_ref": v.regulation_ref,
                    "matched_text": v.matched_text if self._include_snippets else "<redacted>",
                    "span": list(v.span),
                    "regulation_detail": self._regulation_detail(v.regulation_ref),
                }
                for v in result.violations
            ],
            "remediations": self._suggest_remediations(result.violations),
            "audit_trail": result.audit_trail,
        }

    @staticmethod
    def _group_by_category(violations: list[Violation]) -> dict[str, list[Violation]]:
        grouped: dict[str, list[Violation]] = defaultdict(list)
        for v in violations:
            grouped[v.category].append(v)
        return dict(grouped)

    @staticmethod
    def _regulation_detail(ref: str) -> str:
        """Look up regulation metadata, return a short description."""
        info = _REGULATIONS.get(ref)
        if info:
            return f"{info.full_name} ({info.authority})"
        # Try prefix match for sub-section refs like "HIPAA-164.502(a)"
        base = ref.split("(")[0].split("-")[0] if "-" in ref else ref
        info = _REGULATIONS.get(base)
        if info:
            return f"{info.full_name} ({info.authority}) [subsection]"
        return "Unknown regulation"

    @staticmethod
    def _severity_badge(level: RiskLevel) -> str:
        """Text-only severity indicator for Markdown."""
        return {
            RiskLevel.CRITICAL: "[CRITICAL]",
            RiskLevel.HIGH: "[HIGH]",
            RiskLevel.MEDIUM: "[MEDIUM]",
            RiskLevel.LOW: "[LOW]",
            RiskLevel.NONE: "[NONE]",
        }.get(level, "[?]")

    @staticmethod
    def _suggest_remediations(violations: list[Violation]) -> list[str]:
        """
        Generate actionable remediation suggestions based on violation categories.
        Groups similar violations to avoid redundant suggestions.
        """
        suggestions: list[str] = []
        seen_categories: set[str] = set()

        # Category-specific remediation templates
        category_actions: dict[str, str] = {
            "pii_exposure": "Strip or mask all personally identifiable information (SSN, account numbers) from model outputs before delivery.",
            "financial_disclosure": "Add required financial disclaimers and risk warnings to all investment-related outputs.",
            "credit_data": "Ensure credit-related outputs include adverse action notices and FCRA-required disclosures.",
            "cpni": "Remove or redact Customer Proprietary Network Information from outputs per FCC Section 222.",
            "phi_exposure": "Redact all Protected Health Information. Apply HIPAA Safe Harbor de-identification before output.",
            "medical_advice": "Add disclaimers that AI output does not constitute medical advice. Route to licensed professional.",
            "automated_decisions": "Include transparency notices when output influences automated decision-making.",
            "data_retention": "Verify that output does not expose data beyond its authorized retention period.",
            "marketing_compliance": "Validate marketing outputs against TCPA opt-in requirements before distribution.",
        }

        # Severity-based escalation
        has_critical = any(v.severity == RiskLevel.CRITICAL for v in violations)
        has_high = any(v.severity == RiskLevel.HIGH for v in violations)

        for v in violations:
            if v.category not in seen_categories:
                seen_categories.add(v.category)
                action = category_actions.get(
                    v.category,
                    f"Review and remediate {v.category} violations per {v.regulation_ref or 'applicable regulations'}."
                )
                suggestions.append(action)

        if has_critical:
            suggestions.append(
                "ESCALATE: Critical violations detected. Block this output from production until remediated."
            )
        elif has_high:
            suggestions.append(
                "Flag for manual compliance review before deployment."
            )

        return suggestions
