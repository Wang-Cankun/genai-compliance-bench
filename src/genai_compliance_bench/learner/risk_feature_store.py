"""Persistent store for risk features discovered across industries.

Uses SQLite as the backend. Each risk feature captures a pattern or signal
discovered during compliance evaluations, tagged by sector, category, and
severity. Feature provenance tracks which evaluation runs contributed each
feature.

This accumulated multi-industry knowledge is the key differentiator:
patterns discovered in one sector (e.g., financial fair-lending violations)
can inform evaluations in another sector (e.g., insurance underwriting).
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from genai_compliance_bench.types import Severity


@dataclass
class RiskFeature:
    """A risk pattern discovered during compliance evaluation."""

    feature_id: str
    sector: str
    category: str
    severity: Severity
    description: str
    pattern: str  # regex or keyword pattern
    provenance: list[str] = field(default_factory=list)  # evaluation run IDs
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS risk_features (
    feature_id TEXT PRIMARY KEY,
    sector TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    pattern TEXT NOT NULL,
    provenance TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sector ON risk_features(sector);
CREATE INDEX IF NOT EXISTS idx_category ON risk_features(category);
CREATE INDEX IF NOT EXISTS idx_severity ON risk_features(severity);
CREATE INDEX IF NOT EXISTS idx_sector_category ON risk_features(sector, category);
"""


class RiskFeatureStore:
    """SQLite-backed store for accumulated risk features.

    Usage::

        store = RiskFeatureStore(Path("risk_features.db"))
        store.upsert(RiskFeature(
            feature_id="fin-pii-001",
            sector="financial",
            category="pii_exposure",
            severity=Severity.HIGH,
            description="SSN pattern in output",
            pattern=r"\\b\\d{3}-\\d{2}-\\d{4}\\b",
            provenance=["batch-run-2024-03-01"],
        ))
        features = store.query(sector="financial", severity=Severity.HIGH)
    """

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _ensure_schema(self) -> None:
        with self._cursor() as cur:
            cur.executescript(_SCHEMA)

    def upsert(self, feature: RiskFeature) -> None:
        """Insert or update a risk feature.

        On conflict (same feature_id), merges provenance lists and updates
        the timestamp + description.
        """
        existing = self.get(feature.feature_id)
        now = time.time()

        if existing is None:
            feature.created_at = now
            feature.updated_at = now
            self._insert(feature)
        else:
            # merge provenance
            merged_provenance = list(
                dict.fromkeys(existing.provenance + feature.provenance)
            )
            feature.provenance = merged_provenance
            feature.created_at = existing.created_at
            feature.updated_at = now
            self._update(feature)

    def upsert_batch(self, features: list[RiskFeature]) -> None:
        """Upsert multiple features in one transaction."""
        for f in features:
            self.upsert(f)

    def get(self, feature_id: str) -> RiskFeature | None:
        """Retrieve a single feature by ID."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM risk_features WHERE feature_id = ?",
                (feature_id,),
            )
            row = cur.fetchone()
            return _row_to_feature(row) if row else None

    def query(
        self,
        *,
        sector: str | None = None,
        category: str | None = None,
        severity: Severity | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RiskFeature]:
        """Query features by sector, category, and/or severity.

        All filter parameters are optional. Omitting all returns the most
        recently updated features up to ``limit``.
        """
        clauses: list[str] = []
        params: list[Any] = []

        if sector is not None:
            clauses.append("sector = ?")
            params.append(sector)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if severity is not None:
            clauses.append("severity = ?")
            params.append(severity.value)

        where = ""
        if clauses:
            where = "WHERE " + " AND ".join(clauses)

        sql = f"SELECT * FROM risk_features {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]

        with self._cursor() as cur:
            cur.execute(sql, params)
            return [_row_to_feature(row) for row in cur.fetchall()]

    def count(
        self,
        *,
        sector: str | None = None,
        category: str | None = None,
        severity: Severity | None = None,
    ) -> int:
        """Count features matching the given filters."""
        clauses: list[str] = []
        params: list[Any] = []

        if sector is not None:
            clauses.append("sector = ?")
            params.append(sector)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if severity is not None:
            clauses.append("severity = ?")
            params.append(severity.value)

        where = ""
        if clauses:
            where = "WHERE " + " AND ".join(clauses)

        sql = f"SELECT COUNT(*) FROM risk_features {where}"
        with self._cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]

    def delete(self, feature_id: str) -> bool:
        """Delete a feature. Returns True if a row was deleted."""
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM risk_features WHERE feature_id = ?",
                (feature_id,),
            )
            return cur.rowcount > 0

    def sectors(self) -> list[str]:
        """List all distinct sectors in the store."""
        with self._cursor() as cur:
            cur.execute("SELECT DISTINCT sector FROM risk_features ORDER BY sector")
            return [row[0] for row in cur.fetchall()]

    def categories(self, sector: str | None = None) -> list[str]:
        """List distinct categories, optionally filtered by sector."""
        if sector:
            sql = "SELECT DISTINCT category FROM risk_features WHERE sector = ? ORDER BY category"
            params: tuple[Any, ...] = (sector,)
        else:
            sql = "SELECT DISTINCT category FROM risk_features ORDER BY category"
            params = ()
        with self._cursor() as cur:
            cur.execute(sql, params)
            return [row[0] for row in cur.fetchall()]

    def provenance_for(self, feature_id: str) -> list[str]:
        """Get the list of evaluation run IDs that contributed to a feature."""
        feature = self.get(feature_id)
        return feature.provenance if feature else []

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> RiskFeatureStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _insert(self, f: RiskFeature) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO risk_features
                   (feature_id, sector, category, severity, description,
                    pattern, provenance, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f.feature_id,
                    f.sector,
                    f.category,
                    f.severity.value,
                    f.description,
                    f.pattern,
                    json.dumps(f.provenance),
                    json.dumps(f.metadata),
                    f.created_at,
                    f.updated_at,
                ),
            )

    def _update(self, f: RiskFeature) -> None:
        with self._cursor() as cur:
            cur.execute(
                """UPDATE risk_features
                   SET sector = ?, category = ?, severity = ?, description = ?,
                       pattern = ?, provenance = ?, metadata = ?, updated_at = ?
                   WHERE feature_id = ?""",
                (
                    f.sector,
                    f.category,
                    f.severity.value,
                    f.description,
                    f.pattern,
                    json.dumps(f.provenance),
                    json.dumps(f.metadata),
                    f.updated_at,
                    f.feature_id,
                ),
            )


def _row_to_feature(row: sqlite3.Row) -> RiskFeature:
    return RiskFeature(
        feature_id=row["feature_id"],
        sector=row["sector"],
        category=row["category"],
        severity=Severity(row["severity"]),
        description=row["description"],
        pattern=row["pattern"],
        provenance=json.loads(row["provenance"]),
        metadata=json.loads(row["metadata"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
# Updated: b887c3e7
