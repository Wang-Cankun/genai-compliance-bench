"""Quick start: evaluate an AI output for financial compliance in 10 lines."""

from genai_compliance_bench import PolicyEngine

engine = PolicyEngine()
engine.load_sector("financial")

result = engine.evaluate(
    output="Based on the applicant's profile, we recommend denying the loan application.",
    sector="financial",
    context={"use_case": "credit_decisioning", "model": "gpt-4"},
)

print(f"Compliant: {result.passed}")
print(f"Risk score: {result.score:.2f}")
print(f"Violations: {len(result.violations)}")

for v in result.violations:
    print(f"  [{v.severity}] {v.rule_id}: {v.explanation}")
    print(f"    Regulation: {v.regulation_ref}")
