"""行情快照 + 异动冷却存储（SQLite）。

- snapshot：每标的上一次的价格，用于小时级涨跌幅对比（盘中相邻两次运行）。
- cooldown：每个「标的+口径+方向」上次告警时间，冷却期内不重复推送。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path


class SnapshotStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        import sqlite3

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS snapshot (symbol TEXT PRIMARY KEY, price REAL, ts TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cooldown (key TEXT PRIMARY KEY, ts TEXT)"
        )
        self._conn.commit()

    def last_prices(self) -> dict[str, float]:
        rows = self._conn.execute("SELECT symbol, price FROM snapshot").fetchall()
        return {sym: price for sym, price in rows}

    def save_prices(self, quotes) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.executemany(
            "INSERT OR REPLACE INTO snapshot (symbol, price, ts) VALUES (?, ?, ?)",
            [(q.symbol, q.price, now) for q in quotes],
        )
        self._conn.commit()

    def in_cooldown(self, key: str, cooldown_hours: int) -> bool:
        row = self._conn.execute(
            "SELECT ts FROM cooldown WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return False
        last = datetime.fromisoformat(row[0])
        return datetime.now(timezone.utc) - last < timedelta(hours=cooldown_hours)

    def mark_alerted(self, keys: list[str]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.executemany(
            "INSERT OR REPLACE INTO cooldown (key, ts) VALUES (?, ?)",
            [(k, now) for k in keys],
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
