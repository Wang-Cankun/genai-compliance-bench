# Contributing to genai-compliance-bench

## Development Setup

```bash
git clone https://github.com/genai-compliance-bench/genai-compliance-bench.git
cd genai-compliance-bench
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
ruff check src/ tests/
mypy src/
```

## What We Need

**Benchmark contributions** are the highest priority. Each new benchmark expands the tool's coverage of real regulatory requirements.

To add a benchmark:

1. Create a directory under `benchmarks/<sector>/<category>/`
2. Write `test_cases.yaml` with input/output pairs and expected violations
3. Write `rules.yaml` with the compliance rules being tested
4. Write `thresholds.yaml` with pass/fail criteria
5. Add a `README.md` explaining what regulation the benchmark covers and why these test cases matter

**Sector expertise** -- if you work in a regulated industry, your knowledge of actual compliance requirements is more valuable than code contributions. Open an issue describing a compliance scenario that should be tested.

**New sectors** -- healthcare (HIPAA), energy (NERC CIP), and insurance are planned. If you have domain knowledge, reach out.

## Code Standards

- Python 3.10+, type hints everywhere
- Format with `ruff format`, lint with `ruff check`
- Tests for all new rules and evaluator logic
- Docstrings on public APIs

## Pull Request Process

1. Fork the repo, create a feature branch
2. Add tests for your changes
3. Run `ruff check` and `mypy` -- CI will reject PRs with lint errors
4. Open a PR with a description of what regulation or compliance gap your change addresses

## Benchmark Quality

Test cases should come from real regulatory requirements, not hypothetical scenarios. Reference the specific regulation section (e.g., "12 CFR 1002.9" not just "ECOA") in your rule definitions. If you're unsure whether a test case reflects actual regulatory expectations, open a draft PR and ask for review.

## License

By contributing, you agree that your contributions will be licensed under Apache 2.0.
