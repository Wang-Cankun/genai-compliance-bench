"""Load compliance rules from YAML config files."""

from __future__ import annotations
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

logger = logging.getLogger(__name__)
_REQUIRED_FIELDS = {"id", "sector", "category", "severity", "description"}
_VALID_SEVERITIES = {"critical", "high", "medium", "low"}


@dataclass(frozen=True)
class ComplianceRule:
    id: str
    sector: str
    category: str
    severity: str
    description: str
    regulation_ref: str = ""
    pattern: str | None = None
    case_insensitive: bool = True
    keywords: tuple[str, ...] = ()
    enabled: bool = True


class RuleValidationError(Exception):
    pass


class RuleLoader:
    def __init__(self, benchmarks_dir: str | Path = "benchmarks") -> None:
        self._base_dir = Path(benchmarks_dir)
        if not self._base_dir.is_dir():
            raise FileNotFoundError(f"Benchmarks dir not found: {self._base_dir.resolve()}")
        self._cache: dict[str, list[ComplianceRule]] = {}

    def load_sector(self, sector: str) -> list[ComplianceRule]:
        if sector in self._cache:
            return self._cache[sector]
        sector_dir = self._base_dir / sector
        if not sector_dir.is_dir():
            raise FileNotFoundError(f"No rules for sector: {sector}")
        rules: list[ComplianceRule] = []
        for path in sorted(sector_dir.glob("*.yaml")):
            rules.extend(self._load_file(path, sector))
        self._cache[sector] = rules
        return rules

    def _load_file(self, path: Path, sector: str) -> list[ComplianceRule]:
        with open(path) as f:
            data = yaml.safe_load(f)
        if data is None:
            return []
        raw = data.get("rules", []) if isinstance(data, dict) else data
        results = []
        for i, r in enumerate(raw):
            r.setdefault("sector", sector)
            missing = _REQUIRED_FIELDS - r.keys()
            if missing:
                raise RuleValidationError(f"{path}[{i}]: Missing {sorted(missing)}")
            kw = r.get("keywords", [])
            if isinstance(kw, str):
                kw = [kw]
            results.append(ComplianceRule(
                id=str(r["id"]), sector=str(r["sector"]), category=str(r["category"]),
                severity=r["severity"], description=str(r["description"]),
                regulation_ref=str(r.get("regulation_ref", "")),
                pattern=r.get("pattern"), case_insensitive=r.get("case_insensitive", True),
                keywords=tuple(kw), enabled=r.get("enabled", True)))
        return [r for r in results if r.enabled]
