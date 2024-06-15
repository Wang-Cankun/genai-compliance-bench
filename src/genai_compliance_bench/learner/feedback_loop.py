"""Feedback loop for learning from evaluation outcomes."""

from __future__ import annotations
import json, time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class FeedbackVerdict(Enum):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    TRUE_NEGATIVE = "true_negative"
    FALSE_NEGATIVE = "false_negative"


@dataclass
class FeedbackEntry:
    rule_id: str
    verdict: FeedbackVerdict
    timestamp: float = field(default_factory=time.time)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "verdict": self.verdict.value,
                "timestamp": self.timestamp, "notes": self.notes}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FeedbackEntry:
        return cls(rule_id=d["rule_id"], verdict=FeedbackVerdict(d["verdict"]),
                   timestamp=d.get("timestamp", 0.0), notes=d.get("notes", ""))


@dataclass
class RuleStats:
    rule_id: str
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        d = self.true_positives + self.false_positives
        return self.true_positives / d if d > 0 else 1.0

    @property
    def recall(self) -> float:
        d = self.true_positives + self.false_negatives
        return self.true_positives / d if d > 0 else 1.0


class FeedbackLoop:
    def __init__(self, storage_path: Path | None = None) -> None:
        self._entries: list[FeedbackEntry] = []
        self._stats: dict[str, RuleStats] = {}
        self._storage_path = storage_path
        if storage_path and storage_path.exists():
            self._load(storage_path)

    def record(self, entry: FeedbackEntry) -> None:
        self._entries.append(entry)
        self._update_stats(entry)
        if self._storage_path:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._storage_path, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")

    def rule_stats(self, rule_id: str) -> RuleStats:
        return self._stats.get(rule_id, RuleStats(rule_id=rule_id))

    def _update_stats(self, entry):
        if entry.rule_id not in self._stats:
            self._stats[entry.rule_id] = RuleStats(rule_id=entry.rule_id)
        s = self._stats[entry.rule_id]
        v = entry.verdict
        if v is FeedbackVerdict.TRUE_POSITIVE: s.true_positives += 1
        elif v is FeedbackVerdict.FALSE_POSITIVE: s.false_positives += 1
        elif v is FeedbackVerdict.TRUE_NEGATIVE: s.true_negatives += 1
        elif v is FeedbackVerdict.FALSE_NEGATIVE: s.false_negatives += 1

    def _load(self, path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = FeedbackEntry.from_dict(json.loads(line))
                    self._entries.append(entry)
                    self._update_stats(entry)
