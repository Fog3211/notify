"""管道编排：采集 -> 过滤/去重 -> 分组 -> AI 分析 -> 推送 -> 标记已读。

设计为「一次运行即幂等」：触发方式（Docker cron / launchd / n8n / 手动）无关，
任何触发跑一遍都安全 —— 去重保证不重复推送。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from .analyzer import safe_analyze
from .collectors.registry import build_collectors
from .collectors.sec import recent_8k
from .config import Settings
from .dedup import SeenStore
from .http import make_client
from .llm.base import LLMError
from .llm.factory import build_llm
from .market.attribution import apply as apply_attribution, attribute
from .market.calendar import upcoming_earnings
from .market.hours import is_us_market_open
from .market.movers import detect
from .market.provider import fetch_quotes
from .market.snapshot import SnapshotStore
from .models import MoverAlert, NewsItem, Report
from .notifiers.registry import build_notifiers
from .notifiers.render import build_daily_message, build_events_message, build_movers_message

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

        # 附上近期财报安排（免费 Finnhub；无 key 则为空，不影响简报）
        if settings.market.enabled:
            with make_client() as client:
                report.calendar = upcoming_earnings(client, settings, days=7)

        msg = build_daily_message(report, settings.report.show_stats)
        if dry_run:
            log.info("[dry-run] 报告如下，不推送、不写去重库：\n%s", msg.markdown)
            return report

        notifiers = build_notifiers(settings)
        results = [n.send(msg) for n in notifiers]

        # 只要有渠道推送成功（或本就没配渠道）就标记已读，避免重复推送；
        # 全部渠道失败则不标记，留待下次重试。
        if not notifiers or any(results):
            store.mark_seen(analyzed_items)
        else:
            log.warning("所有渠道推送失败，本批不标记已读")
        return report
    finally:
        store.close()


def run_events(settings: Settings, *, dry_run: bool = False) -> list[NewsItem]:
    """重大事件速报：拉关注个股的最新 8-K -> 去重 -> 命中即推。返回本次推送的事件。

    与每日简报共用去重库：经速报推过的 8-K 不会再在简报里重复出现，反之亦然。
    不受交易时段限制（8-K 盘后也会申报）。
    """
    if not settings.market.enabled:
        log.info("未启用 market，跳过重大事件监控")
        return []

    store = SeenStore(settings.dedup_db_path())
    try:
        with make_client() as client:
            try:
                events = recent_8k(client, settings, settings.all_tickers(), days=2)
            except Exception as exc:   # SEC 故障不应让调度循环崩溃
                log.warning("SEC 8-K 拉取失败：%s", exc)
                return []
        fresh = store.filter_new(events)
        log.info("8-K 事件 %d 起，去重后 %d 起为新", len(events), len(fresh))
        if not fresh:
            return []

        msg = build_events_message(fresh)
        if dry_run:
            log.info("[dry-run] 重大事件速报如下，不推送、不写去重库：\n%s", msg.markdown)
            return fresh

        notifiers = build_notifiers(settings)
        results = [n.send(msg) for n in notifiers]
        if not notifiers or any(results):
            store.mark_seen(fresh)
        else:
            log.warning("所有渠道推送失败，本批不标记已读")
        return fresh
    finally:
        store.close()


def _attribute_movers(settings: Settings, alerts: list[MoverAlert]) -> None:
    """为异动个股做 AI 归因（原地改写 reason）。LLM 不可用时静默跳过。"""
    try:
        llm = build_llm(settings)
    except LLMError as exc:
        log.info("未配置可用 LLM，跳过异动归因（%s）", exc)
        return
    # 复用每日新闻采集，关联到异动个股；只在确有异动时才付出这次采集成本
    news = _filter_recent(_collect_all(settings), settings.processing.lookback_hours)
    reasons = attribute(llm, alerts, news)
    apply_attribution(alerts, reasons)
    if reasons:
        log.info("已为 %d 只异动生成 AI 归因", len(reasons))


def run_movers(
    settings: Settings, *, dry_run: bool = False, force: bool = False
) -> list[MoverAlert]:
    """盘中速报：拉行情 -> 检测异动 -> 冷却过滤 -> 推送。返回本次推送的告警。

    dry_run=True 时不推送、不写快照/冷却（可重复测试）；force=True 时绕过交易时段门控。
    """
    if not settings.market.enabled:
        log.info("行情/异动监控未启用 (market.enabled=false)")
        return []
    if not force and not is_us_market_open():
        log.info("当前非美股交易时段，跳过盘中速报（--force 可强制）")
        return []

    store = SnapshotStore(settings.snapshot_db_path())
    try:
        last_prices = store.last_prices()
        with make_client() as client:
            quotes = fetch_quotes(settings, settings.all_tickers(), client)
        if not quotes:
            log.warning("未取到任何行情，跳过")
            return []

        alerts = detect(quotes, last_prices, settings.market.movers)
        if not dry_run:
            store.save_prices(quotes)   # 更新快照，供下次小时级对比

        # 冷却过滤：同标的同方向同口径在冷却期内不重复推送
        cooldown_h = settings.market.movers.cooldown_hours
        fresh = [a for a in alerts if not store.in_cooldown(a.cooldown_key, cooldown_h)]
        log.info("检测到 %d 条异动，冷却过滤后 %d 条待推送", len(alerts), len(fresh))
        if not fresh:
            return []

        # 可选：关联近期新闻，给每只异动个股一句话 AI 归因（无 LLM key 则自动跳过）
        if settings.market.ai_attribution:
            _attribute_movers(settings, fresh)

        msg = build_movers_message(fresh)
        if dry_run:
            log.info("[dry-run] 异动速报如下，不推送、不写状态：\n%s", msg.markdown)
            return fresh

        notifiers = build_notifiers(settings)
        results = [n.send(msg) for n in notifiers]
        if not notifiers or any(results):
            store.mark_alerted([a.cooldown_key for a in fresh])
        else:
            log.warning("所有渠道推送失败，本批不标记冷却")
        return fresh
    finally:
        store.close()
