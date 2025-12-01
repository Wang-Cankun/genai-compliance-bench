"""Demonstrate the self-evolving risk intelligence capability.

The system learns from evaluation results and human feedback,
accumulating industry-specific risk features over time.
"""

from genai_compliance_bench import PolicyEngine, FeedbackLoop, RiskFeatureStore

engine = PolicyEngine()
engine.load_sector("financial")

# Initialize the learning components
store = RiskFeatureStore("risk_features.db")
feedback = FeedbackLoop(engine, store)

# Simulate evaluation cycle
output = "Transfer $9,800 to account ending in 4521. Reason: consulting fees."
result = engine.evaluate(
    output=output,
    sector="financial",
    context={"use_case": "transaction_monitoring"},
)

print(f"Initial evaluation: {'PASS' if result.passed else 'FAIL'}")
print(f"Violations: {len(result.violations)}")

# Human reviewer marks this as a true positive (structuring attempt)
feedback.record(
    evaluation_id=result.audit_trail["evaluation_id"],
    human_label="true_positive",
    notes="Classic structuring pattern: amount just below $10K CTR threshold",
    risk_features=["sub_ctr_threshold_amount", "round_number_proximity"],
)

# The system learns: amounts near $10K reporting thresholds are a risk signal
# This pattern gets stored in the risk feature store
features = store.query(sector="financial", category="aml")
print(f"\nAccumulated AML risk features: {len(features)}")
for f in features[:5]:
    print(f"  {f.feature_id}: {f.description} (confidence: {f.confidence:.2f})")

# Over time, the feature store accumulates cross-industry risk patterns
# that no newly-built tool would have
print(f"\nTotal features in store: {store.total_features}")
print(f"Sectors covered: {store.sectors}")
print(f"Oldest feature: {store.oldest_feature_date}")
