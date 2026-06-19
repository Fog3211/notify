"""离线核心逻辑测试：去重、JSON 解析、渲染。不依赖网络与 API key。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.analyzer import _extract_json
from app.dedup import SeenStore
from app.models import NewsItem, Report, TopicAnalysis
from app.notifiers.render import build_events_message, render_feishu_card, render_markdown
from app.pipeline import _filter_recent, _group_and_cap


def _item(url: str, topic: str = "ai") -> NewsItem:
    return NewsItem(source="s", topic=topic, title="t", url=url)


def _dated(hours_ago: float, topic: str = "ai") -> NewsItem:
    pub = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return NewsItem(source="s", topic=topic, title="t", url=f"http://x/{topic}/{hours_ago}", published_at=pub)


def test_filter_recent_drops_old_keeps_undated():
    kept = _filter_recent([_dated(1), _dated(50), _item("http://x/none")], 30)
    urls = {i.url for i in kept}
    assert "http://x/ai/1" in urls and "http://x/none" in urls and "http://x/ai/50" not in urls


def test_group_and_cap_caps_and_sorts_newest_first():
    items = [_dated(3, "ai"), _dated(1, "ai"), _dated(2, "ai"), _dated(1, "finance")]
    grouped = _group_and_cap(items, 2)
    assert len(grouped["ai"]) == 2 and len(grouped["finance"]) == 1
    assert grouped["ai"][0].url == "http://x/ai/1"   # 最新在前


def test_dedup_filters_seen_and_within_batch(tmp_path):
    store = SeenStore(tmp_path / "seen.sqlite")
    a, b = _item("http://x/1"), _item("http://x/2")

    # 同一批内重复（同 URL）只保留一条
    fresh = store.filter_new([a, b, _item("http://x/1")])
    assert len(fresh) == 2

    store.mark_seen([a])
    # a 已标记，再过滤应被剔除
    assert [i.url for i in store.filter_new([a, b])] == ["http://x/2"]
    store.close()


def test_dedup_purge(tmp_path):
    store = SeenStore(tmp_path / "seen.sqlite")
    store.mark_seen([_item("http://x/1")])
    # 0 天保留 = 立即清空
    assert store.purge_older_than(0) == 1
    assert len(store.filter_new([_item("http://x/1")])) == 1
    store.close()


def test_extract_json_strips_fences():
    raw = '```json\n{"overview": "ok", "topics": []}\n```'
    assert _extract_json(raw)["overview"] == "ok"


def test_extract_json_finds_object_in_prose():
    raw = '分析如下：{"overview": "x", "topics": []} 以上。'
    assert _extract_json(raw)["topics"] == []


def _sample_report() -> Report:
    return Report(
        title="测试简报",
        generated_at=datetime(2026, 6, 16, 0, 0, tzinfo=timezone.utc),
        overview="今日主线",
        analyses=[
            TopicAnalysis(
                topic="ai",
                headline="模型大战",
                bullets=["要点1", "要点2"],
                sentiment="bullish",
                tickers=["NVDA"],
            )
        ],
        stats={"ai": 3},
    )


def test_render_markdown_contains_key_sections():
    md = render_markdown(_sample_report())
    assert "测试简报" in md
    assert "模型大战" in md
    assert "要点1" in md
    assert "NVDA" in md


def test_render_feishu_card_structure():
    card = render_feishu_card(_sample_report())
    assert card["header"]["title"]["content"] == "测试简报"
    assert any(e.get("tag") == "div" for e in card["elements"])


def test_calendar_section_in_markdown():
    r = _sample_report()
    r.calendar = ["NVDA 2026-06-25 盘后"]
    md = render_markdown(r)
    assert "近期财报" in md and "NVDA 2026-06-25" in md


def test_events_message():
    items = [_item("http://x/8k")]
    items[0].title = "NVDA 8-K · 业绩/财务结果"
    items[0].topic = "events"
    msg = build_events_message(items)
    assert "重大事件" in msg.title
    assert "NVDA 8-K" in msg.markdown and "http://x/8k" in msg.markdown
