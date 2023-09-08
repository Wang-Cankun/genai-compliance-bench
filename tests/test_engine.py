"""Tests for the core policy engine."""
import pytest
from genai_compliance_bench.policy_engine.engine import PolicyEngine

@pytest.fixture
def engine():
    e = PolicyEngine()
    e.load_sector("financial")
    return e

class TestPolicyEngine:
    def test_clean_output_passes(self, engine):
        result = engine.evaluate(output="Approved. Credit score 750.", sector="financial")
        assert result.passed

    def test_pii_detection(self, engine):
        result = engine.evaluate(output="Customer SSN is 123-45-6789.", sector="financial")
        assert any(v.category == "pii_exposure" for v in result.violations)

    def test_discriminatory_language(self, engine):
        result = engine.evaluate(output="Denied based on age and neighborhood.", sector="financial")
        assert not result.passed
