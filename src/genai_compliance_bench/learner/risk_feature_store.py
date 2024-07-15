"""SQLite store for cross-industry risk features."""

from __future__ import annotations
import json, sqlite3, time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from genai_compliance_bench.types import Severity


@dataclass
class RiskFeature:
    feature_id: str
    sector: str
    category: str
    severity: Severity
    description: str
    pattern: str
    provenance: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS risk_features (
    feature_id TEXT PRIMARY KEY, sector TEXT NOT NULL, category TEXT NOT NULL,
    severity TEXT NOT NULL, description TEXT NOT NULL, pattern TEXT NOT NULL,
    provenance TEXT NOT NULL DEFAULT '[]', metadata TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sector ON risk_features(sector);
"""


class RiskFeatureStore:
    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    def _get_conn(self):
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

    def _ensure_schema(self):
        with self._cursor() as cur:
            cur.executescript(_SCHEMA)

    def upsert(self, feature: RiskFeature) -> None:
        existing = self.get(feature.feature_id)
        now = time.time()
        if existing is None:
            feature.created_at = now
            feature.updated_at = now
            with self._cursor() as cur:
                cur.execute("INSERT INTO risk_features VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (feature.feature_id, feature.sector, feature.category, feature.severity.value,
                     feature.description, feature.pattern, json.dumps(feature.provenance),
                     json.dumps(feature.metadata), feature.created_at, feature.updated_at))
        else:
            merged = list(dict.fromkeys(existing.provenance + feature.provenance))
            feature.provenance = merged
            feature.updated_at = now
            with self._cursor() as cur:
                cur.execute("UPDATE risk_features SET provenance=?, metadata=?, updated_at=? WHERE feature_id=?",
                    (json.dumps(feature.provenance), json.dumps(feature.metadata), feature.updated_at, feature.feature_id))

    def get(self, feature_id: str) -> RiskFeature | None:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM risk_features WHERE feature_id = ?", (feature_id,))
            row = cur.fetchone()
            if not row:
                return None
            return RiskFeature(feature_id=row["feature_id"], sector=row["sector"],
                category=row["category"], severity=Severity(row["severity"]),
                description=row["description"], pattern=row["pattern"],
                provenance=json.loads(row["provenance"]), metadata=json.loads(row["metadata"]),
                created_at=row["created_at"], updated_at=row["updated_at"])

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
