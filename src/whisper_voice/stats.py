# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Usage statistics computed from on-disk history.

Everything here is pure/local: no network, no live service connection, no
RAM-only counters that vanish between restarts. Each invocation rebuilds
metrics from the history files so numbers are always accurate.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Tuple

from .backup import Backup
from .config import get_config


@dataclass
class UsageStats:
    total_sessions: int = 0
    total_words: int = 0
    total_chars: int = 0
    avg_words_per_session: float = 0.0
    sessions_today: int = 0
    sessions_past_7d: int = 0
    sessions_past_30d: int = 0
    first_session: datetime | None = None
    last_session: datetime | None = None
    top_words: List[Tuple[str, int]] = field(default_factory=list)
    top_replacements_triggered: List[Tuple[str, int]] = field(default_factory=list)


_STOPWORDS = {
    # Tiny default stopword set so the "top words" list isn't all "the/a/and".
    # Intentionally minimal; we want genuine signal, not fluff.
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "i", "you", "he", "she", "it", "we", "they",
    "this", "that", "these", "those", "with", "as", "at", "by", "from",
    "my", "your", "his", "her", "its", "our", "their",
    "so", "if", "not", "no", "yes", "just", "then", "than",
    "um", "uh",
}


def compute_usage_stats(top_n: int = 10) -> UsageStats:
    """Build a fresh :class:`UsageStats` from history files on disk."""
    stats = UsageStats()
    backup = Backup()
    entries = backup.get_history(limit=10_000)
    if not entries:
        return stats

    now = datetime.now()
    word_counter: Counter[str] = Counter()
    replacement_counter: Counter[str] = Counter()

    cfg = get_config()
    replacement_rules = cfg.replacements.rules if cfg.replacements.enabled else {}

    for entry in entries:
        ts = entry.get("timestamp")
        text = (entry.get("fixed") or entry.get("raw") or "").strip()
        if not text:
            continue
        stats.total_sessions += 1
        stats.total_chars += len(text)

        words = [w for w in _words(text) if w]
        stats.total_words += len(words)

        for w in words:
            lowered = w.lower()
            if lowered in _STOPWORDS or len(lowered) < 3:
                continue
            word_counter[lowered] += 1

        if isinstance(ts, datetime):
            if stats.first_session is None or ts < stats.first_session:
                stats.first_session = ts
            if stats.last_session is None or ts > stats.last_session:
                stats.last_session = ts
            if ts.date() == now.date():
                stats.sessions_today += 1
            if ts >= now - timedelta(days=7):
                stats.sessions_past_7d += 1
            if ts >= now - timedelta(days=30):
                stats.sessions_past_30d += 1

        # Count replacement-rule matches in the fixed text.
        if replacement_rules:
            lowered_text = text.lower()
            for spoken in replacement_rules:
                needle = spoken.lower()
                if needle and needle in lowered_text:
                    replacement_counter[spoken] += 1

    if stats.total_sessions:
        stats.avg_words_per_session = stats.total_words / stats.total_sessions

    stats.top_words = word_counter.most_common(top_n)
    stats.top_replacements_triggered = replacement_counter.most_common(top_n)
    return stats


def format_stats_text(stats: UsageStats) -> str:
    """Render stats as a human-readable block for ``wh stats``."""
    if stats.total_sessions == 0:
        return "No transcriptions yet."
    lines = []
    lines.append(f"Total sessions      : {stats.total_sessions}")
    lines.append(f"Total words         : {stats.total_words:,}")
    lines.append(f"Total characters    : {stats.total_chars:,}")
    lines.append(f"Avg words / session : {stats.avg_words_per_session:.1f}")
    lines.append("")
    lines.append(f"Today               : {stats.sessions_today}")
    lines.append(f"Past 7 days         : {stats.sessions_past_7d}")
    lines.append(f"Past 30 days        : {stats.sessions_past_30d}")
    if stats.first_session and stats.last_session:
        lines.append("")
        lines.append(f"First session       : {stats.first_session:%Y-%m-%d %H:%M}")
        lines.append(f"Last session        : {stats.last_session:%Y-%m-%d %H:%M}")
    if stats.top_words:
        lines.append("")
        lines.append("Top words (stopwords excluded):")
        for word, count in stats.top_words:
            lines.append(f"  {count:>4}  {word}")
    if stats.top_replacements_triggered:
        lines.append("")
        lines.append("Top replacement rules triggered:")
        for spoken, count in stats.top_replacements_triggered:
            lines.append(f"  {count:>4}  {spoken}")
    return "\n".join(lines)


def _words(text: str) -> list:
    current = []
    out = []
    for ch in text:
        if ch.isalpha() or ch == "'":
            current.append(ch)
        else:
            if current:
                out.append("".join(current))
                current = []
    if current:
        out.append("".join(current))
    return out
