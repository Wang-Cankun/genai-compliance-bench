# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Public API                               │
│  PolicyEngine.evaluate()  BatchEvaluator  RealtimeEvaluator     │
└───────────────────────────────┬─────────────────────────────────┘
                                │
         ┌──────────────────────▼──────────────────────┐
         │              Policy Engine                   │
         │                                              │
         │  ┌────────────┐    ┌──────────────────────┐ │
         │  │ RuleLoader │───▶│  Rule Store (sector)  │ │
         │  └────────────┘    └──────────┬───────────┘ │
         │                               │              │
         │  ┌────────────────────────────▼───────────┐ │
         │  │         Rule Matcher                    │ │
         │  │  (keyword + regex + context matching)   │ │
         │  └────────────────────────────┬───────────┘ │
         │                               │              │
         │  ┌────────────────────────────▼───────────┐ │
         │  │         Violation Collector             │ │
         │  │  (dedup, severity ranking, scoring)     │ │
         │  └────────────────────────────┬───────────┘ │
         └───────────────────────────────┼─────────────┘
                                         │
         ┌───────────────────────────────▼─────────────┐
         │             Explainer Module                 │
         │  (regulation refs, reasoning, remediation)   │
         └───────────────────────────────┬─────────────┘
                                         │
         ┌───────────────────────────────▼─────────────┐
         │           ComplianceResult                   │
         │  (score, violations, explanations, metadata) │
         └───────────────────────────────┬─────────────┘
                                         │
                            ┌────────────▼────────────┐
                            │    Learner (optional)    │
                            │  feedback → weight adj.  │
                            │  risk feature accum.     │
                            │  rule suggestions (LLM)  │
                            └─────────────────────────┘
```

## Components

### Policy Engine (`src/genai_compliance_bench/policy_engine/`)

The core component. Loads compliance rules, evaluates AI outputs, and produces structured results.

**RuleLoader** reads YAML rule definitions from benchmark directories or custom paths. Rules are indexed by sector and category for fast lookup. Loading a sector (`engine.load_sector("financial")`) pulls all rules for that sector into memory.

**Rule Matcher** runs loaded rules against an AI output string. Matching uses three strategies in order:
1. **Keyword match** -- fast pre-filter using the rule's `keywords` list
2. **Regex match** -- pattern matching using the rule's `patterns` list
3. **Context match** -- checks whether the rule applies given the evaluation context (e.g., a rule specific to `credit_decisioning` won't fire for `customer_service`)

Rules that match produce `Violation` objects. The matcher records character offsets (`span`) where the violation was detected.

**Violation Collector** deduplicates violations (same rule triggered by multiple patterns), ranks by severity, and computes the overall risk score. The score is a weighted sum of violation severities, normalized to [0, 1].

### Evaluator (`src/genai_compliance_bench/evaluator/`)

Two evaluation modes wrapping the policy engine:

**BatchEvaluator** takes a list of `EvaluationRecord` objects and returns a list of `ComplianceResult` objects. Designed for CI/CD pipelines and benchmark runs. Supports parallel evaluation.

**RealtimeEvaluator** evaluates a single output with minimal latency. Designed for runtime guardrails where you need a compliance check before showing a response to a user.

### Explainer (`policy_engine/explainer.py`)

Transforms raw `Violation` objects into human-readable explanations. For each violation, the explainer generates:
- A summary of what regulation was violated
- The specific regulatory citation (e.g., "12 CFR 1002.9(a)(2)")
- Why the detected pattern constitutes a violation
- A suggested remediation

The explainer is deterministic -- it uses templates keyed to rule categories, not an LLM. Explanations are reproducible across runs.

### Learner (`src/genai_compliance_bench/learner/`)

Optional module (requires `openai` dependency). Implements the feedback loop described in the [methodology](methodology.md).

**Feedback ingestion**: accepts corrections from compliance officers (marking false positives and false negatives).

**Risk feature accumulation**: tracks which rules are frequently overridden, which output patterns correlate with manual corrections, and how violation patterns shift across evaluation cycles.

**Weight adjustment**: modifies rule weights based on accumulated feedback. Rules that produce many false positives get lower weights; rules that miss violations flagged by humans get higher weights. Weight changes are logged and reversible.

**Rule suggestion**: uses an LLM to analyze clusters of corrected evaluations and propose new rules. Proposed rules are written to a staging file for human review -- they are never auto-deployed.

### Types (`src/genai_compliance_bench/types.py`)

Shared dataclasses used across all modules:

- `ComplianceRule` -- a single compliance rule definition
- `ComplianceResult` -- evaluation result with violations, score, and metadata
- `Violation` -- a specific compliance violation with severity and location
- `EvaluationRecord` -- input format for batch evaluation
- `Severity` -- LOW, MEDIUM, HIGH, CRITICAL
- `OutputFormat` -- JSON, CSV, MARKDOWN

## Data Flow

```
1. Input
   AI output text + sector + context
        │
2. Sector Detection
   Load rules for specified sector
        │
3. Rule Matching
   For each rule in sector:
     keyword pre-filter → regex match → context check
        │
4. Violation Collection
   Dedup → severity ranking → score computation
        │
5. Explanation Generation
   For each violation:
     regulation lookup → reasoning template → remediation
        │
6. Result Assembly
   ComplianceResult with score, violations, explanations
        │
7. Output
   JSON / CSV / Markdown + audit trail
        │
8. (Optional) Learner Feedback
   Human corrections → weight adjustment → risk features
```

## Benchmark Data Flow

Benchmark suites follow the same evaluation pipeline but with predefined inputs and expected outputs:

```
benchmarks/<sector>/<category>/
├── test_cases.yaml      ──▶  EvaluationRecord objects
├── rules.yaml           ──▶  ComplianceRule objects (loaded by RuleLoader)
└── thresholds.yaml      ──▶  Pass/fail criteria for the benchmark

BatchEvaluator runs all test cases against loaded rules.
Results are compared against expected violations in test_cases.yaml.
Benchmark passes if precision and recall meet thresholds.
```

## Extension Points

**Adding a new sector**: create a directory under `benchmarks/<sector>/`, add rule YAML files, and register the sector in the policy engine's sector registry.

**Adding rules to an existing sector**: add entries to the sector's `rules.yaml` or create a new category directory with its own `rules.yaml`.

**Custom evaluator logic**: subclass `PolicyEngine` and override the matching pipeline. The `RuleLoader` and `Explainer` are designed to be used independently.

**Output integration**: `ComplianceResult.to_dict()` returns a serializable dictionary. Pipe this to your existing compliance reporting tools.
# Updated: 5a4cf30f
