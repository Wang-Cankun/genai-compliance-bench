# genai-compliance-bench

Pre-deployment compliance evaluation benchmarks for generative AI in regulated industries.

## Problem

Companies deploying LLMs in financial services and telecom lack standardized tools to test whether model outputs meet sector-specific regulatory requirements before production.

## Features

- **Sector-adaptive policy engine** -- domain-specific compliance rules per industry
- **Explainable compliance assessments** -- graduated risk scores with regulation-specific reasoning
- **Self-evolving risk intelligence** -- learning from evaluation cycles
- **Pre-built benchmarks** -- fair lending, AML, SOX audit trail, CPNI protection

## Quick Start

```bash
pip install genai-compliance-bench
```

```python
from genai_compliance_bench import PolicyEngine

engine = PolicyEngine()
engine.load_sector("financial")
result = engine.evaluate(
    output="Based on the applicant\'s profile, we recommend denying the loan.",
    sector="financial",
    context={"use_case": "credit_decisioning"},
)
print(f"Compliant: {result.passed}")
print(f"Risk score: {result.score:.2f}")
```

## Documentation

- [Architecture](docs/architecture.md)
- [Evaluation Methodology](docs/methodology.md)
- [NIST AI RMF Mapping](docs/nist-ai-rmf-mapping.md)

## License

Apache 2.0.
