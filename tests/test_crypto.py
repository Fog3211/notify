"""币圈行情/异动的离线测试（纯逻辑，不依赖网络）。"""

from __future__ import annotations

from app.config import MoversCfg
from app.market.crypto import _prev_from_pct
from app.market.movers import detect
from app.models import MoverAlert, Quote
from app.notifiers.render import build_movers_message


def test_prev_from_pct_roundtrips_to_change_pct():
    # 由最新价 + 24h 涨幅反推基准价，Quote.change_pct 应等于该涨幅
    prev = _prev_from_pct(110.0, 10.0)
    q = Quote(symbol="BTC", price=110.0, prev_close=prev)
    assert round(q.change_pct, 2) == 10.0


def test_prev_from_pct_none():
    assert _prev_from_pct(100.0, None) is None


def test_crypto_uses_higher_threshold():
    cfg = MoversCfg(daily_threshold_pct=10.0, hourly_threshold_pct=5.0, volume_multiple=3.0)
    # 股票口径会触发的 +6% 在币圈 10% 阈值下不触发
    quiet = Quote(symbol="ETH", price=106.0, prev_close=_prev_from_pct(106.0, 6.0))
    assert detect([quiet], {}, cfg) == []
    # +12% 触发
    pump = Quote(symbol="SOL", price=112.0, prev_close=_prev_from_pct(112.0, 12.0))
    alerts = detect([pump], {}, cfg)
    assert len(alerts) == 1 and alerts[0].symbol == "SOL"


def test_crypto_daily_label_is_24h():
    cfg = MoversCfg(daily_threshold_pct=10.0, hourly_threshold_pct=99, volume_multiple=99)
    pump = Quote(symbol="SOL", price=112.0, prev_close=_prev_from_pct(112.0, 12.0))
    alert = detect([pump], {}, cfg, daily_label="24h")[0]
    assert "24h" in alert.reason and "日内" not in alert.reason


def test_movers_message_custom_title():
    alerts = [MoverAlert(symbol="BTC", window="daily", change_pct=12.0, price=70000.0, reason="24h涨 12%")]
    msg = build_movers_message(alerts, title="🪙 币圈异动速报")
    assert msg.title == "🪙 币圈异动速报"
    assert "币圈异动速报" in msg.markdown and "BTC" in msg.markdown
