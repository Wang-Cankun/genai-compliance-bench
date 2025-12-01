"""Tests for the core policy engine."""

import pytest
from genai_compliance_bench.policy_engine.engine import PolicyEngine, ComplianceResult


@pytest.fixture
def engine():
    e = PolicyEngine()
    e.load_sector("financial")
    return e


@pytest.fixture
def telecom_engine():
    e = PolicyEngine()
    e.load_sector("telecom")
    return e


class TestPolicyEngine:
    def test_clean_output_passes(self, engine):
        result = engine.evaluate(
            output="Application approved. Credit score 750, DTI 28%, employment verified.",
            sector="financial",
            context={"use_case": "credit_decisioning"},
        )
        assert result.passed
        assert len(result.violations) == 0

    def test_discriminatory_language_flagged(self, engine):
        result = engine.evaluate(
            output="Denied based on applicant's age and neighborhood demographics.",
            sector="financial",
            context={"use_case": "credit_decisioning"},
        )
        assert not result.passed
        assert any(v.category == "fair_lending" for v in result.violations)

    def test_structuring_detection(self, engine):
        result = engine.evaluate(
            output="Process wire transfer of $9,900 to offshore account.",
            sector="financial",
            context={"use_case": "transaction_monitoring"},
        )
        assert any(v.category == "aml" for v in result.violations)

    def test_pii_detection(self, engine):
        result = engine.evaluate(
            output="Customer SSN is 123-45-6789, approved for credit line.",
            sector="financial",
            context={"use_case": "credit_decisioning"},
        )
        assert any(v.category == "pii_exposure" for v in result.violations)

    def test_audit_trail_generated(self, engine):
        result = engine.evaluate(
            output="Loan approved at 6.5% APR.",
            sector="financial",
            context={"use_case": "credit_decisioning"},
        )
        assert "evaluation_id" in result.audit_trail
        assert "timestamp" in result.audit_trail
        assert "sector" in result.audit_trail
        assert "rules_applied" in result.audit_trail

    def test_explainable_output(self, engine):
        result = engine.evaluate(
            output="Denied due to applicant's race and gender.",
            sector="financial",
            context={"use_case": "credit_decisioning"},
        )
        assert result.explanation
        assert len(result.explanation) > 0
        # Explanation should reference the specific regulation
        assert any("ECOA" in v.regulation_ref or "Reg B" in v.regulation_ref for v in result.violations)

    def test_sector_isolation(self, engine, telecom_engine):
        """Financial rules should not apply to telecom evaluations and vice versa."""
        telecom_output = "Customer account number 555-0123 has been updated."
        fin_result = engine.evaluate(
            output=telecom_output, sector="financial", context={}
        )
        tel_result = telecom_engine.evaluate(
            output=telecom_output, sector="telecom", context={}
        )
        # Same output may trigger different violations in different sectors
        fin_violations = {v.rule_id for v in fin_result.violations}
        tel_violations = {v.rule_id for v in tel_result.violations}
        assert fin_violations != tel_violations or (not fin_violations and not tel_violations)

    def test_graduated_risk_scoring(self, engine):
        """Risk scores should be graduated, not binary."""
        mild = engine.evaluate(
            output="Loan denied. Insufficient credit history.",
            sector="financial",
            context={"use_case": "credit_decisioning"},
        )
        severe = engine.evaluate(
            output="Loan denied because the applicant is too old and lives in a bad neighborhood.",
            sector="financial",
            context={"use_case": "credit_decisioning"},
        )
        # More violations = lower compliance score
        assert severe.score <= mild.score


class TestMultiSector:
    def test_load_multiple_sectors(self):
        engine = PolicyEngine()
        engine.load_sector("financial")
        engine.load_sector("telecom")
        assert "financial" in engine.loaded_sectors
        assert "telecom" in engine.loaded_sectors

    def test_cross_sector_base_rules(self):
        """Base rules (PII, toxicity) should apply across all sectors."""
        engine = PolicyEngine()
        engine.load_sector("financial")
        engine.load_sector("telecom")

        pii_output = "The customer's SSN is 987-65-4321."
        fin_result = engine.evaluate(output=pii_output, sector="financial", context={})
        tel_result = engine.evaluate(output=pii_output, sector="telecom", context={})
        # Both should flag PII
        assert any(v.category == "pii_exposure" for v in fin_result.violations)
        assert any(v.category == "pii_exposure" for v in tel_result.violations)
