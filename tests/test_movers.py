"""异动检测与冷却存储的离线测试。不依赖网络与 key。"""

from __future__ import annotations

from app.config import MoversCfg
from app.market.movers import detect
from app.market.snapshot import SnapshotStore
from app.models import MoverAlert, Quote


def _cfg(**kw) -> MoversCfg:
    base = dict(daily_threshold_pct=5.0, hourly_threshold_pct=3.0, volume_multiple=3.0)
    base.update(kw)
    return MoversCfg(**base)


def _q(symbol, price, prev_close=None, volume=None, avg_volume=None) -> Quote:
    return Quote(symbol=symbol, price=price, prev_close=prev_close, volume=volume, avg_volume=avg_volume)


def test_daily_breach_triggers():
    alerts = detect([_q("WDC", 116.0, prev_close=100.0)], {}, _cfg())
    assert len(alerts) == 1
    a = alerts[0]
    assert a.symbol == "WDC" and a.window == "daily" and a.direction == "up"
    assert round(a.change_pct) == 16


def test_below_threshold_no_alert():
    assert detect([_q("AAPL", 102.0, prev_close=100.0)], {}, _cfg()) == []


def test_downside_breach_direction():
    a = detect([_q("MU", 90.0, prev_close=100.0)], {}, _cfg())[0]
    assert a.direction == "down" and a.change_pct < 0


def test_hourly_uses_last_snapshot():
    # 日内仅 +2%（不破日阈值），但相对上次快照 +4%（破小时阈值）
    alerts = detect([_q("NVDA", 104.0, prev_close=102.0)], {"NVDA": 100.0}, _cfg())
    assert len(alerts) == 1 and alerts[0].window == "hourly"


def test_volume_anomaly_triggers():
    alerts = detect([_q("STX", 101.0, prev_close=100.0, volume=400, avg_volume=100)], {}, _cfg())
    assert len(alerts) == 1 and alerts[0].window == "volume"


def test_one_alert_per_symbol_priority_daily():
    # 同时破日阈值与量能：只产一条，取优先级最高 daily，reason 含两者
    alerts = detect([_q("ARM", 108.0, prev_close=100.0, volume=400, avg_volume=100)], {}, _cfg())
    assert len(alerts) == 1
    assert alerts[0].window == "daily"
    assert "成交量" in alerts[0].reason


def test_sorted_by_magnitude():
    alerts = detect(
        [_q("A", 106.0, prev_close=100.0), _q("B", 120.0, prev_close=100.0)], {}, _cfg()
    )
    assert [a.symbol for a in alerts] == ["B", "A"]


def test_cooldown_key():
    a = MoverAlert(symbol="MU", window="daily", change_pct=10.0, price=100.0)
    assert a.cooldown_key == "MU:daily:up"


def test_snapshot_store_cooldown(tmp_path):
    store = SnapshotStore(tmp_path / "m.sqlite")
    assert store.in_cooldown("MU:daily:up", 4) is False
    store.mark_alerted(["MU:daily:up"])
    assert store.in_cooldown("MU:daily:up", 4) is True   # 刚标记，在冷却内
    assert store.in_cooldown("MU:daily:up", 0) is False  # 冷却 0 小时 = 不冷却
    store.close()


def test_snapshot_store_prices_roundtrip(tmp_path):
    store = SnapshotStore(tmp_path / "m.sqlite")
    store.save_prices([_q("NVDA", 200.0), _q("MU", 100.0)])
    assert store.last_prices() == {"NVDA": 200.0, "MU": 100.0}
    store.close()
