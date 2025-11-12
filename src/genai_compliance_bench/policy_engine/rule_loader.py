"""
Load and validate compliance rules from YAML config files.

Rule files live under benchmarks/<sector>/*.yaml. A special _base.yaml
in benchmarks/ provides cross-sector defaults that sector files can override.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Required fields every rule must have after merging with base defaults
_REQUIRED_FIELDS = {"id", "sector", "category", "severity", "description"}

# Allowed severity values
_VALID_SEVERITIES = {"critical", "high", "medium", "low"}


@dataclass(frozen=True)
class ComplianceRule:
    """
    A single compliance rule loaded from YAML.

    Rules check AI output via one or more of:
    - pattern: regex to match against the output
    - keywords: list of literal strings to flag
    - condition: structured check (missing_disclaimer, exceeds_length, etc.)
    """

    id: str
    sector: str
    category: str
    severity: str                          # "critical" | "high" | "medium" | "low"
    description: str
    regulation_ref: str = ""
    pattern: str | None = None
    case_insensitive: bool = True
    keywords: tuple[str, ...] = ()
    condition: dict[str, Any] | None = None
    applies_to: tuple[str, ...] = ()       # Optional use_case filter
    enabled: bool = True


class RuleValidationError(Exception):
    """Raised when a rule file has schema problems."""


class RuleLoader:
    """
    Load compliance rules from YAML files, with caching and inheritance.

    Directory layout:
        benchmarks/
            _base.yaml          # optional cross-sector defaults
            financial/
                disclosure.yaml
                pii.yaml
            telecom/
                cpni.yaml
            healthcare/
                hipaa.yaml
    """

    def __init__(self, benchmarks_dir: str | Path = "benchmarks") -> None:
        self._base_dir = Path(benchmarks_dir)
        if not self._base_dir.is_dir():
            raise FileNotFoundError(
                f"Benchmarks directory not found: {self._base_dir.resolve()}"
            )
        # Cache: sector -> list[ComplianceRule]
        self._cache: dict[str, list[ComplianceRule]] = {}
        # Base defaults (loaded once)
        self._base_defaults: dict[str, Any] | None = None

    def load_sector(self, sector: str, *, force_reload: bool = False) -> list[ComplianceRule]:
        """
        Load all rules for a sector. Returns cached results unless force_reload.
        Base defaults from _base.yaml are merged into each rule.
        """
        if not force_reload and sector in self._cache:
            return self._cache[sector]

        sector_dir = self._base_dir / sector
        if not sector_dir.is_dir():
            raise FileNotFoundError(
                f"No rules directory for sector '{sector}': "
                f"{sector_dir.resolve()}"
            )

        base = self._load_base_defaults()
        rules: list[ComplianceRule] = []
        seen_ids: set[str] = set()

        yaml_files = sorted(sector_dir.glob("*.yaml")) + sorted(sector_dir.glob("*.yml"))
        if not yaml_files:
            logger.warning("No YAML files found in %s", sector_dir)
            return []

        for path in yaml_files:
            file_rules = self._load_file(path, base, sector)
            for rule in file_rules:
                if rule.id in seen_ids:
                    logger.warning(
                        "Duplicate rule id '%s' in sector '%s', "
                        "later definition wins",
                        rule.id, sector,
                    )
                seen_ids.add(rule.id)
                rules.append(rule)

        self._cache[sector] = rules
        logger.info("Loaded %d rules for sector '%s'", len(rules), sector)
        return rules

    def load_all_sectors(self) -> dict[str, list[ComplianceRule]]:
        """Load rules from every sector directory found."""
        results = {}
        for child in sorted(self._base_dir.iterdir()):
            if child.is_dir() and not child.name.startswith(("_", ".")):
                results[child.name] = self.load_sector(child.name)
        return results

    def invalidate_cache(self, sector: str | None = None) -> None:
        """Clear cached rules. If sector is None, clear everything."""
        if sector:
            self._cache.pop(sector, None)
        else:
            self._cache.clear()
            self._base_defaults = None

    # -- Internal ------------------------------------------------------------

    def _load_base_defaults(self) -> dict[str, Any]:
        """Load _base.yaml if it exists. Cached after first load."""
        if self._base_defaults is not None:
            return self._base_defaults

        base_path = self._base_dir / "_base.yaml"
        if base_path.exists():
            with open(base_path) as f:
                data = yaml.safe_load(f) or {}
            self._base_defaults = data.get("defaults", {})
        else:
            self._base_defaults = {}

        return self._base_defaults

    def _load_file(
        self,
        path: Path,
        base_defaults: dict[str, Any],
        sector: str,
    ) -> list[ComplianceRule]:
        """Parse one YAML file into ComplianceRule objects."""
        with open(path) as f:
            data = yaml.safe_load(f)

        if data is None:
            return []

        # File can have top-level "rules" list or be a list directly
        raw_rules: list[dict[str, Any]]
        if isinstance(data, list):
            raw_rules = data
        elif isinstance(data, dict):
            raw_rules = data.get("rules", [])
            if not isinstance(raw_rules, list):
                raise RuleValidationError(
                    f"{path}: 'rules' must be a list, got {type(raw_rules).__name__}"
                )
        else:
            raise RuleValidationError(
                f"{path}: Expected list or dict at top level"
            )

        results = []
        for i, raw in enumerate(raw_rules):
            if not isinstance(raw, dict):
                raise RuleValidationError(
                    f"{path}[{i}]: Rule must be a dict, got {type(raw).__name__}"
                )
            merged = {**base_defaults, "sector": sector, **raw}
            rule = self._validate_and_build(merged, path, i)
            if rule.enabled:
                results.append(rule)

        return results

    def _validate_and_build(
        self,
        data: dict[str, Any],
        source_path: Path,
        index: int,
    ) -> ComplianceRule:
        """Validate required fields and construct a ComplianceRule."""
        missing = _REQUIRED_FIELDS - data.keys()
        if missing:
            raise RuleValidationError(
                f"{source_path}[{index}]: Missing required fields: {sorted(missing)}"
            )

        severity = data["severity"]
        if severity not in _VALID_SEVERITIES:
            raise RuleValidationError(
                f"{source_path}[{index}]: Invalid severity '{severity}'. "
                f"Must be one of: {sorted(_VALID_SEVERITIES)}"
            )

        # Normalize keywords to tuple
        kw = data.get("keywords", [])
        if isinstance(kw, str):
            kw = [kw]
        keywords = tuple(kw)

        # Normalize applies_to
        at = data.get("applies_to", [])
        if isinstance(at, str):
            at = [at]
        applies_to = tuple(at)

        return ComplianceRule(
            id=str(data["id"]),
            sector=str(data["sector"]),
            category=str(data["category"]),
            severity=severity,
            description=str(data["description"]),
            regulation_ref=str(data.get("regulation_ref", "")),
            pattern=data.get("pattern"),
            case_insensitive=data.get("case_insensitive", True),
            keywords=keywords,
            condition=data.get("condition"),
            applies_to=applies_to,
            enabled=data.get("enabled", True),
        )
# Updated: 654abcdd
