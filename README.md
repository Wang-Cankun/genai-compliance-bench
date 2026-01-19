# genai-compliance-bench

Pre-deployment compliance evaluation benchmarks for generative AI in regulated industries.

## Problem

Companies deploying LLMs in financial services and telecom lack standardized tools to test whether model outputs meet sector-specific regulatory requirements before production. Each company builds ad-hoc safety testing internally, duplicating effort and missing edge cases that only surface after deployment. The [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework) defines what trustworthy AI requires but provides no evaluation tools. This project fills that gap with open-source, sector-specific compliance benchmarks.

## Features

- **Sector-adaptive policy engine** -- loads domain-specific compliance rules per industry (financial services, telecom)
- **Explainable compliance assessments** -- graduated risk scores with regulation-specific reasoning, not binary pass/fail
- **Self-evolving risk intelligence** -- LLM-powered learning from evaluation cycles; accumulates multi-industry risk features
- **Pre-built benchmarks** -- test suites for fair lending, AML, SOX audit trail, CPNI protection, TCPA consent
- **NIST AI RMF aligned** -- maps directly to GOVERN, MAP, MEASURE, MANAGE functions ([mapping](docs/nist-ai-rmf-mapping.md))

## Quick Start

```bash
pip install genai-compliance-bench
```

```python
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
```

Output:
```
Compliant: False
Risk score: 0.82
Violations: 2
  [HIGH] ECOA-001: Credit decision output lacks required adverse action reasoning.
    Regulation: ECOA / Regulation B, 12 CFR 1002.9
  [MEDIUM] FAIR-002: Output does not reference specific, non-discriminatory factors.
    Regulation: ECOA / Regulation B, 12 CFR 1002.6
```

## Supported Regulations

### Financial Services

| Regulation | Scope | Benchmark Path |
|---|---|---|
| SOX (Sarbanes-Oxley) | Audit trail integrity, internal controls | `benchmarks/financial/sox_audit/` |
| PCI-DSS | Cardholder data protection in AI outputs | `benchmarks/financial/` |
| GLBA (Gramm-Leach-Bliley) | Customer financial data privacy | `benchmarks/financial/` |
| ECOA / Reg B | Fair lending, adverse action notices | `benchmarks/financial/fair_lending/` |
| BSA/AML | Suspicious activity detection, reporting | `benchmarks/financial/aml/` |

### Healthcare

| Regulation | Scope | Benchmark Path |
|---|---|---|
| HIPAA Privacy Rule | Protected health information in AI outputs | `benchmarks/healthcare/` |
| HIPAA Security Rule | Technical safeguards for ePHI | `benchmarks/healthcare/` |

### Telecommunications

| Regulation | Scope | Benchmark Path |
|---|---|---|
| FCC Section 222 (CPNI) | Customer proprietary network information | `benchmarks/telecom/data_privacy/` |
| TCPA | Telemarketing consent, autodialer restrictions | `benchmarks/telecom/` |
| FCC Privacy Rules | Broadband privacy, data collection notices | `benchmarks/telecom/content_safety/` |

## Architecture

```
                        ┌─────────────────────┐
                        │   AI Model Output    │
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │   Sector Detector    │
                        │  (financial/telecom) │
                        └──────────┬──────────┘
                                   │
              ┌────────────────────▼────────────────────┐
              │            Policy Engine                 │
              │  ┌──────────┐  ┌──────────┐            │
              │  │   Rule   │  │  Rule    │            │
              │  │  Loader  │  │ Matcher  │            │
              │  └────┬─────┘  └────┬─────┘            │
              │       │             │                    │
              │  ┌────▼─────────────▼─────┐            │
              │  │   Compliance Evaluator  │            │
              │  └────────────┬───────────┘            │
              └───────────────┼────────────────────────┘
                              │
              ┌───────────────▼────────────────────────┐
              │          Explainer Module                │
              │  (regulation refs, risk reasoning)      │
              └───────────────┬────────────────────────┘
                              │
              ┌───────────────▼────────────────────────┐
              │       Learner (feedback loop)           │
              │  (risk feature accumulation, weight     │
              │   adjustment across eval cycles)        │
              └───────────────┬────────────────────────┘
                              │
                   ┌──────────▼──────────┐
                   │  ComplianceResult   │
                   │  (score, violations,│
                   │   explanations,     │
                   │   audit trail)      │
                   └─────────────────────┘
```

## Benchmark Structure

Each benchmark suite contains:

```
benchmarks/<sector>/<category>/
├── test_cases.yaml      # Input/output pairs with expected violations
├── rules.yaml           # Sector-specific compliance rules
├── thresholds.yaml      # Pass/fail thresholds per regulation
└── README.md            # What this benchmark tests and why
```

Test cases include:
- **Clean outputs** -- model outputs that should pass all rules
- **Single-violation outputs** -- outputs that fail exactly one rule (tests precision)
- **Multi-violation outputs** -- outputs with overlapping regulatory concerns
- **Edge cases** -- outputs that are technically compliant but warrant review

## Documentation

- [Evaluation Methodology](docs/methodology.md)
- [NIST AI RMF Mapping](docs/nist-ai-rmf-mapping.md)
- [Architecture](docs/architecture.md)
- [Financial Services Guide](docs/sector_guides/financial_services.md)
- [Telecommunications Guide](docs/sector_guides/telecommunications.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and contribution guidelines.

## License

Apache 2.0. See [LICENSE](LICENSE).

## Citation

If you use genai-compliance-bench in research, please cite:

```bibtex
@software{genai_compliance_bench,
  title  = {genai-compliance-bench: Pre-deployment Compliance Evaluation Benchmarks for Generative AI},
  year   = {2026},
  url    = {https://github.com/Wang-Cankun/genai-compliance-bench},
  license = {Apache-2.0}
}
```
