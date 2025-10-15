# NIST AI Risk Management Framework Mapping

This document maps genai-compliance-bench capabilities to the [NIST AI Risk Management Framework (AI RMF 1.0)](https://doi.org/10.6028/NIST.AI.100-1), published January 2023. Section references follow the AI RMF document structure.

## Overview

The NIST AI RMF defines four core functions: GOVERN, MAP, MEASURE, and MANAGE. genai-compliance-bench directly supports MEASURE and MANAGE through automated compliance evaluation. It supports GOVERN and MAP indirectly by producing artifacts (audit trails, violation reports) that feed into governance and risk mapping processes.

---

## GOVERN: Policies, processes, procedures, and practices across the organization

The GOVERN function establishes organizational AI risk management culture and processes. genai-compliance-bench does not replace governance structures but produces outputs that governance processes consume.

### GV-1: Policies, processes, procedures to map, measure, and manage AI risks

| Subcategory | Tool Capability |
|---|---|
| GV-1.1: Legal and regulatory requirements are identified | Rule definitions reference specific statutes and CFR citations (e.g., `12 CFR 1002.9` for ECOA). The `rules.yaml` files in each benchmark serve as machine-readable inventories of applicable regulations. |
| GV-1.2: Trustworthy AI characteristics are integrated into policies | Evaluation results map to NIST trustworthy characteristics: fairness (fair lending rules), privacy (CPNI/GLBA rules), accountability (audit trail generation). |

### GV-3: Workforce diversity, equity, inclusion, and accessibility

| Subcategory | Tool Capability |
|---|---|
| GV-3.2: Policies addressing AI risks of bias | Fair lending benchmarks (`benchmarks/financial/fair_lending/`) directly test for outputs that violate ECOA/Reg B anti-discrimination requirements. Results feed into organizational bias policy compliance reporting. |

### GV-4: Organizational teams are committed to a culture of managing AI risk

| Subcategory | Tool Capability |
|---|---|
| GV-4.3: Organizational practices foster critical thinking | Explainable assessments with regulation-specific reasoning give compliance teams concrete material for review, rather than opaque scores. |

### GV-6: Policies and procedures are in place to address AI risks and benefits arising from third-party software and data

| Subcategory | Tool Capability |
|---|---|
| GV-6.1: Policies address third-party AI risks | When evaluating outputs from third-party LLMs (OpenAI, Anthropic, etc.), the tool produces compliance evidence that can be included in vendor risk assessments. |

---

## MAP: Context, capability, and risk identification

The MAP function characterizes the AI system's context of use and identifies risks. genai-compliance-bench supports this through sector detection and rule loading.

### MP-2: Categorization of the AI system

| Subcategory | Tool Capability |
|---|---|
| MP-2.1: The AI system's intended purpose and context of use | The `sector` and `context` parameters in `engine.evaluate()` explicitly declare the deployment context. The policy engine loads rules appropriate to that context. |
| MP-2.3: Scientific integrity and data collection transparency | Benchmark test cases (`test_cases.yaml`) document exactly what outputs are tested and what constitutes a violation, making the evaluation methodology transparent and reproducible. |

### MP-3: AI system benefits and costs

| Subcategory | Tool Capability |
|---|---|
| MP-3.4: Risks due to interaction with other AI systems | The tool evaluates outputs regardless of source. When multiple models contribute to a pipeline (e.g., retrieval model + generation model), each output can be independently evaluated for compliance. |

### MP-4: Risks and impacts of AI systems

| Subcategory | Tool Capability |
|---|---|
| MP-4.1: Identify potential harms | Each compliance rule defines a specific regulatory harm. The `severity` field (LOW, MEDIUM, HIGH, CRITICAL) maps to impact levels. |
| MP-4.2: Internal risk controls | Pre-deployment evaluation acts as a risk control gate. Integration into CI/CD pipelines provides automated enforcement. |

---

## MEASURE: Analysis, assessment, and tracking

This is the primary alignment area. genai-compliance-bench is fundamentally a measurement tool.

### MS-1: Appropriate methods and metrics

| Subcategory | Tool Capability |
|---|---|
| MS-1.1: Approaches for measurement of AI risks | The policy engine uses pattern matching, keyword analysis, and context-aware evaluation. Each rule specifies what constitutes a violation and how to detect it. Metrics include violation count, maximum severity, risk score, and per-regulation pass rates. |
| MS-1.3: Internal experts contribute to measurement approach | The learner module incorporates compliance officer feedback. When a human overrides an automated result, that correction adjusts future evaluations. |

### MS-2: AI systems are evaluated for trustworthy characteristics

| Subcategory | Tool Capability |
|---|---|
| MS-2.1: Tests for validity and reliability | Benchmark suites include known-compliant and known-violating outputs. Running the benchmarks validates that the evaluator correctly identifies violations (precision) and doesn't miss real violations (recall). |
| MS-2.3: Tests for bias | Fair lending benchmarks test specifically for ECOA/Reg B violations including proxy discrimination. |
| MS-2.5: AI system privacy risks | CPNI (FCC Section 222), GLBA, and PCI-DSS rules test whether AI outputs leak protected information. |
| MS-2.6: AI system security risks | SOX audit trail rules verify that AI outputs don't compromise internal controls or create audit gaps. |
| MS-2.7: AI system is evaluated for safety | Severity levels map to safety impact. CRITICAL severity violations block deployment in recommended CI/CD configurations. |
| MS-2.8: AI system is evaluated for transparency and accountability | Every `ComplianceResult` includes an audit trail: timestamp, rules evaluated, violations found, explanations, and the original output text. |
| MS-2.11: Fairness assessment includes stakeholder consultation | The learner feedback loop allows compliance officers and affected stakeholders to correct evaluation results, directly influencing future assessments. |

### MS-3: AI risks are prioritized and tracked

| Subcategory | Tool Capability |
|---|---|
| MS-3.1: Metrics for AI risk prioritization | Severity levels (LOW, MEDIUM, HIGH, CRITICAL) and weighted risk scores provide prioritization. Different regulations carry different weights reflecting regulatory penalty exposure. |
| MS-3.2: Risk tracking over time | Evaluation results include timestamps. Running benchmarks across model versions creates a compliance trajectory that shows whether risk is increasing or decreasing. |

### MS-4: Feedback and learning

| Subcategory | Tool Capability |
|---|---|
| MS-4.1: Measurement results inform AI risk management | Results export to JSON, CSV, and Markdown for integration with risk management dashboards and reporting tools. |
| MS-4.2: Measurement results contribute to improvement | The learner module accumulates risk features across evaluation cycles. Rule weights adjust based on observed violation patterns and human feedback. |

---

## MANAGE: Risk treatment and response

The MANAGE function addresses identified risks. genai-compliance-bench supports this by providing actionable violation reports with remediation guidance.

### MG-1: Risk treatments are planned

| Subcategory | Tool Capability |
|---|---|
| MG-1.1: Risk treatment options | Each violation includes a suggested fix. Compliance teams can prioritize fixes by severity and regulation. |
| MG-1.3: Risk treatments are documented | Evaluation results and violation explanations serve as documentation of identified risks and planned treatments. |

### MG-2: Risk treatments are implemented

| Subcategory | Tool Capability |
|---|---|
| MG-2.1: Risk management strategies are implemented | CI/CD integration blocks deployment when CRITICAL violations are found. This is a direct implementation of a risk management gate. |
| MG-2.2: Contingency processes | The tool can run in real-time evaluation mode (via `RealtimeEvaluator`) as a runtime guard, not just a pre-deployment gate. |
| MG-2.6: Planned monitoring metrics are in place | Benchmark pass rates serve as the monitoring metric. Decreasing pass rates on re-evaluation trigger investigation. |

### MG-3: Risks are documented and monitored

| Subcategory | Tool Capability |
|---|---|
| MG-3.1: Post-deployment risk monitoring | `RealtimeEvaluator` enables continuous compliance monitoring of production outputs. |
| MG-3.2: Performance deviations are responded to | The severity system defines response thresholds. Organizations can configure which severity levels trigger automatic responses (alerts, circuit breakers) versus manual review. |

### MG-4: Risk treatments are communicated to stakeholders

| Subcategory | Tool Capability |
|---|---|
| MG-4.1: Risk management results are shared | Markdown and CSV output formats are designed for stakeholder communication. Violation explanations use plain language regulatory references, not internal codes. |

---

## Coverage Summary

| NIST AI RMF Function | Coverage Level | Primary Mechanism |
|---|---|---|
| GOVERN | Indirect | Audit artifacts, regulation inventories |
| MAP | Partial | Sector detection, context parameters, risk categorization |
| MEASURE | Direct | Compliance evaluation, benchmarks, feedback loop |
| MANAGE | Direct | Violation reports, CI/CD gates, remediation guidance |

## References

- NIST AI 100-1: Artificial Intelligence Risk Management Framework (AI RMF 1.0). https://doi.org/10.6028/NIST.AI.100-1
- NIST AI 100-1 Playbook. https://airc.nist.gov/AI_RMF_Knowledge_Base/Playbook
- NIST AI 600-1: Generative AI Profile. https://doi.org/10.6028/NIST.AI.600-1
# Updated: 7417b350
