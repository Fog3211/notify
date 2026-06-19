"""SEC 8-K 条目代码中文化的离线测试（纯逻辑，不依赖网络）。"""

from __future__ import annotations

from app.brief import build_message
from app.collectors.sec import _label_items
from app.models import NewsItem


def test_label_known_items_and_drops_exhibits():
    # 9.01（附件）无信息量，应被忽略
    assert _label_items("2.02,9.01") == "业绩/财务结果"


def test_label_director_change():
    assert _label_items("5.02") == "高管/董事变动"


def test_label_multiple():
    assert _label_items("1.01,5.02") == "签订重大协议 / 高管/董事变动"


def test_label_unknown_code_passthrough():
    assert _label_items("1.99") == "1.99"


def test_label_empty_or_only_exhibits():
    assert _label_items("") == "重大事件申报"
    assert _label_items("9.01") == "重大事件申报"


def test_brief_prioritizes_8k_above_news():
    ev = NewsItem(source="SEC 8-K", topic="events", title="NVDA 8-K · 业绩/财务结果", url="http://x/8k")
    nw = NewsItem(source="Finnhub:NVDA", topic="events", title="Some routine headline", url="http://x/news")
    md = build_message("NVDA", None, [ev], [nw], take="").markdown
    # 8-K 公告栏排在新闻栏前面，且两者都在
    assert md.index("重大公告") < md.index("近期新闻")
    assert "NVDA 8-K" in md and "Some routine headline" in md


def test_brief_no_events_still_renders_news():
    nw = NewsItem(source="Finnhub:NVDA", topic="events", title="headline", url="http://x/n")
    md = build_message("NVDA", None, [], [nw], take="").markdown
    assert "重大公告" not in md and "近期新闻" in md
