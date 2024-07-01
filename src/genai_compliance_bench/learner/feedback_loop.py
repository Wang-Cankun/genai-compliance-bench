"""Self-evolving feedback loop that learns from evaluation outcomes.

Records evaluation results alongside human corrections, then computes
weight adjustments for compliance rules based on false-positive and
false-negative rates.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class FeedbackVerdict(Enum):
    """Human reviewer's correction of an evaluation result."""

    TRUE_POSITIVE = "true_positive"  # rule correctly flagged a violation
    FALSE_POSITIVE = "false_positive"  # rule incorrectly flagged a violation
    TRUE_NEGATIVE = "true_negative"  # rule correctly passed
    FALSE_NEGATIVE = "false_negative"  # rule missed a real violation


@dataclass
class FeedbackEntry:
    """One piece of human feedback on an evaluation."""

    rule_id: str
    verdict: FeedbackVerdict
    timestamp: float = field(default_factory=time.time)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "verdict": self.verdict.value,
            "timestamp": self.timestamp,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FeedbackEntry:
        return cls(
            rule_id=d["rule_id"],
            verdict=FeedbackVerdict(d["verdict"]),
            timestamp=d.get("timestamp", 0.0),
            notes=d.get("notes", ""),
        )


@dataclass
class RuleStats:
    """Accumulated accuracy statistics for a single rule."""

    rule_id: str
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0

    @property
    def total(self) -> int:
        return (
            self.true_positives
            + self.false_positives
            + self.true_negatives
            + self.false_negatives
        )

    @property
    def precision(self) -> float:
        """Of all flagged violations, how many were real."""
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 1.0

    @property
    def recall(self) -> float:
        """Of all real violations, how many did we catch."""
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


class FeedbackLoop:
    """Records evaluation results and human feedback to improve rule accuracy.

    Each feedback entry marks a rule's output on a specific evaluation as
    TP/FP/TN/FN. The loop aggregates these into per-rule precision/recall
    stats and exports weight adjustments.

    Persistence is a simple JSONL file. Each line is a FeedbackEntry.

    Usage::

        loop = FeedbackLoop(Path("feedback.jsonl"))
        loop.record(FeedbackEntry(rule_id="fin-001", verdict=FeedbackVerdict.FALSE_POSITIVE))
        loop.record(FeedbackEntry(rule_id="fin-001", verdict=FeedbackVerdict.TRUE_POSITIVE))
        print(loop.rule_stats("fin-001").precision)
        adjustments = loop.export_weight_updates()
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        self._entries: list[FeedbackEntry] = []
        self._stats: dict[str, RuleStats] = {}
        self._storage_path = storage_path
        if storage_path and storage_path.exists():
            self._load(storage_path)

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def record(self, entry: FeedbackEntry) -> None:
        """Record a single feedback entry and update stats."""
        self._entries.append(entry)
        self._update_stats(entry)
        if self._storage_path:
            self._append_to_file(entry)

    def record_batch(self, entries: list[FeedbackEntry]) -> None:
        """Record multiple feedback entries at once."""
        for entry in entries:
            self.record(entry)

    def rule_stats(self, rule_id: str) -> RuleStats:
        """Get accumulated stats for a rule. Returns zero-stats if unseen."""
        return self._stats.get(rule_id, RuleStats(rule_id=rule_id))

    def all_rule_stats(self) -> dict[str, RuleStats]:
        """Get stats for all rules that have received feedback."""
        return dict(self._stats)

    def export_weight_updates(
        self, *, min_samples: int = 5
    ) -> dict[str, float]:
        """Compute weight adjustments for rules based on feedback.

        Rules with fewer than ``min_samples`` feedback entries are excluded.

        The weight multiplier is the rule's F1 score: rules that are both
        precise and sensitive keep weight ~1.0, while rules that produce
        many false positives or miss real violations get downweighted.

        Returns a dict of rule_id -> weight multiplier (0.0 to 1.0).
        """
        updates: dict[str, float] = {}
        for rule_id, stats in self._stats.items():
            if stats.total < min_samples:
                continue
            updates[rule_id] = round(stats.f1, 4)
        return updates

    def effectiveness_report(self) -> list[dict[str, Any]]:
        """Summary of per-rule effectiveness, sorted by F1 ascending (worst first)."""
        rows = []
        for rule_id, stats in self._stats.items():
            rows.append({
                "rule_id": rule_id,
                "total_feedback": stats.total,
                "precision": round(stats.precision, 4),
                "recall": round(stats.recall, 4),
                "f1": round(stats.f1, 4),
                "true_positives": stats.true_positives,
                "false_positives": stats.false_positives,
                "true_negatives": stats.true_negatives,
                "false_negatives": stats.false_negatives,
            })
        rows.sort(key=lambda r: r["f1"])
        return rows

    def _update_stats(self, entry: FeedbackEntry) -> None:
        if entry.rule_id not in self._stats:
            self._stats[entry.rule_id] = RuleStats(rule_id=entry.rule_id)
        s = self._stats[entry.rule_id]
        v = entry.verdict
        if v is FeedbackVerdict.TRUE_POSITIVE:
            s.true_positives += 1
        elif v is FeedbackVerdict.FALSE_POSITIVE:
            s.false_positives += 1
        elif v is FeedbackVerdict.TRUE_NEGATIVE:
            s.true_negatives += 1
        elif v is FeedbackVerdict.FALSE_NEGATIVE:
            s.false_negatives += 1

    def _append_to_file(self, entry: FeedbackEntry) -> None:
        assert self._storage_path is not None
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._storage_path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def _load(self, path: Path) -> None:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = FeedbackEntry.from_dict(json.loads(line))
                self._entries.append(entry)
                self._update_stats(entry)
