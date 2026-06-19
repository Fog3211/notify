"""SEC 8-K 条目代码中文化的离线测试（纯逻辑，不依赖网络）。"""

from __future__ import annotations

from app.collectors.sec import _label_items


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
