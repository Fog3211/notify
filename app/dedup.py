"""基于 SQLite 的已推送指纹存储。

为什么要持久化：新闻源每天有大量重叠的旧条目，没有跨运行的记忆就会反复
推送同一条。这里只存指纹 + 时间戳，不存正文，文件极小。
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import NewsItem

log = logging.getLogger("dedup")


class SeenStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False：调度器线程与主线程可能不同
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                fingerprint TEXT PRIMARY KEY,
                seen_at     TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def filter_new(self, items: list[NewsItem]) -> list[NewsItem]:
        """返回未见过的条目；同一批内部也去重（同指纹只保留首条）。"""
        fresh: list[NewsItem] = []
        batch_seen: set[str] = set()
        for item in items:
            fp = item.fingerprint
            if fp in batch_seen:
                continue
            batch_seen.add(fp)
            row = self._conn.execute(
                "SELECT 1 FROM seen WHERE fingerprint = ?", (fp,)
            ).fetchone()
            if row is None:
                fresh.append(item)
        return fresh

    def mark_seen(self, items: list[NewsItem]) -> None:
        """把条目标记为已推送。应在推送成功后调用，避免推送失败却丢内容。"""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.executemany(
            "INSERT OR IGNORE INTO seen (fingerprint, seen_at) VALUES (?, ?)",
            [(it.fingerprint, now) for it in items],
        )
        self._conn.commit()

    def purge_older_than(self, days: int) -> int:
        """清理超期指纹，控制库大小。返回删除行数。"""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self._conn.execute("DELETE FROM seen WHERE seen_at < ?", (cutoff,))
        self._conn.commit()
        if cur.rowcount:
            log.info("清理过期去重指纹 %d 条", cur.rowcount)
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
