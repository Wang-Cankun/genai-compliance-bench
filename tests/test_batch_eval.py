"""Tests for batch evaluation."""

import pytest
from genai_compliance_bench import PolicyEngine, BatchEvaluator


@pytest.fixture
def evaluator():
    engine = PolicyEngine()
    engine.load_sector("financial")
    return BatchEvaluator(engine)


class TestBatchEvaluator:
    def test_batch_evaluation(self, evaluator):
        outputs = [
            {
                "output": "Approved. Good credit history.",
                "sector": "financial",
                "context": {"use_case": "credit_decisioning"},
            },
            {
                "output": "Denied due to applicant's ethnicity.",
                "sector": "financial",
                "context": {"use_case": "credit_decisioning"},
            },
        ]
        report = evaluator.evaluate_batch(outputs)
        assert report.total == 2
        assert report.passed >= 0
        assert report.failed >= 0
        assert report.passed + report.failed == report.total

    def test_empty_batch(self, evaluator):
        report = evaluator.evaluate_batch([])
        assert report.total == 0

    def test_report_has_violation_distribution(self, evaluator):
        outputs = [
            {
                "output": "Denied. Applicant too old for this product.",
                "sector": "financial",
                "context": {},
            },
            {
                "output": "SSN 123-45-6789 confirmed. Transfer $9,999 to offshore.",
                "sector": "financial",
                "context": {},
            },
        ]
        report = evaluator.evaluate_batch(outputs)
        assert isinstance(report.violations_by_severity, dict)
        assert isinstance(report.violations_by_regulation, dict)
