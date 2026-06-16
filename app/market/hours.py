"""美股交易时段判断。盘中速报只在交易时段运行，省调用、避免盘后噪音。

用 IANA 时区 America/New_York 处理夏令时；不含节假日（节假日会照常运行但通常
拉到的是前收数据，不会误报异动）。
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_OPEN = time(9, 30)
_CLOSE = time(16, 0)


def is_us_market_open(now_utc: datetime | None = None) -> bool:
    now = (now_utc or datetime.now(timezone.utc)).astimezone(_ET)
    if now.weekday() >= 5:  # 周六/周日
        return False
    return _OPEN <= now.time() <= _CLOSE
