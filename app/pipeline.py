"""管道编排：采集 -> 过滤/去重 -> 分组 -> AI 分析 -> 推送 -> 标记已读。

设计为「一次运行即幂等」：触发方式（Docker cron / launchd / n8n / 手动）无关，
任何触发跑一遍都安全 —— 去重保证不重复推送。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from .analyzer import safe_analyze
from .collectors.registry import build_collectors
from .config import Settings
from .dedup import SeenStore
from .http import make_client
from .llm.factory import build_llm
from .models import NewsItem, Report
from .notifiers.registry import build_notifiers
from .notifiers.render import render_markdown

log = logging.getLogger("pipeline")


def _collect_all(settings: Settings) -> list[NewsItem]:
    """并发拉取所有数据源。单源失败已在 Collector.collect 内吞掉。"""
    collectors = build_collectors(settings)
    if not collectors:
        log.warning("没有可用数据源")
        return []
    items: list[NewsItem] = []
    with make_client() as client:
        # I/O 密集，用线程池并发；httpx.Client 线程安全可共享
        with ThreadPoolExecutor(max_workers=min(8, len(collectors))) as pool:
            for batch in pool.map(lambda c: c.collect(client), collectors):
                items.extend(batch)
    return items


def _filter_recent(items: list[NewsItem], lookback_hours: int) -> list[NewsItem]:
    """丢掉超过回溯窗口的旧闻；无发布时间的条目保留（部分源不带时间）。"""
    kept: list[NewsItem] = []
    for it in items:
        age = it.age_hours
        if age is None or age <= lookback_hours:
            kept.append(it)
    return kept


def _group_and_cap(
    items: list[NewsItem], max_per_topic: int
) -> dict[str, list[NewsItem]]:
    """按 topic 分组并截断，控制喂给 AI 的体量。新→旧排序，优先保留新内容。"""
    grouped: dict[str, list[NewsItem]] = {}
    for it in items:
        grouped.setdefault(it.topic, []).append(it)
    for topic, lst in grouped.items():
        # 无时间的排最后；有时间的按发布时间倒序
        lst.sort(key=lambda x: (x.published_at is not None, x.published_at), reverse=True)
        grouped[topic] = lst[:max_per_topic]
    return grouped


def run(settings: Settings, *, dry_run: bool = False) -> Report | None:
    """执行一次完整管道。dry_run=True 时不推送、不写去重库，仅打印报告。"""
    store = SeenStore(settings.dedup_db_path())
    try:
        store.purge_older_than(settings.processing.dedup_retention_days)

        raw = _collect_all(settings)
        log.info("共采集 %d 条原始资讯", len(raw))

        recent = _filter_recent(raw, settings.processing.lookback_hours)
        fresh = store.filter_new(recent)
        log.info("过滤后 %d 条，去重后 %d 条为新内容", len(recent), len(fresh))

        if not fresh:
            log.info("没有新内容，跳过分析与推送")
            return None

        grouped = _group_and_cap(fresh, settings.processing.max_items_per_topic)
        analyzed_items = [it for lst in grouped.values() for it in lst]

        llm = build_llm(settings)
        report = safe_analyze(settings, llm, grouped)
        if report is None or report.is_empty:
            log.warning("分析无产出，跳过推送（本批不标记已读，下次重试）")
            return None

        if dry_run:
            log.info("[dry-run] 报告如下，不推送、不写去重库：\n%s",
                     render_markdown(report, settings.report.show_stats))
            return report

        notifiers = build_notifiers(settings)
        results = [n.send(report) for n in notifiers]

        # 只要有渠道推送成功（或本就没配渠道）就标记已读，避免重复推送；
        # 全部渠道失败则不标记，留待下次重试。
        if not notifiers or any(results):
            store.mark_seen(analyzed_items)
        else:
            log.warning("所有渠道推送失败，本批不标记已读")
        return report
    finally:
        store.close()
