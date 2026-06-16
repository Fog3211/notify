"""daemon 模式：进程常驻，每天定时跑一次 pipeline。

仅在「本地常驻 / 容器内不依赖外部 cron」时使用。若用 Docker cron / launchd /
n8n 触发，则直接调 `run` 子命令即可，无需本模块。
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import Settings
from . import pipeline

log = logging.getLogger("scheduler")


def run_forever(settings: Settings) -> None:
    hour, minute = (int(x) for x in settings.schedule.daily_at.split(":"))
    sched = BlockingScheduler(timezone=settings.schedule.timezone)

    @sched.scheduled_job(
        CronTrigger(hour=hour, minute=minute, timezone=settings.schedule.timezone)
    )
    def _daily() -> None:
        log.info("每日触发，执行简报管道")
        try:
            pipeline.run(settings)
        except Exception as exc:  # 守护循环不能被单次失败打断
            log.exception("每日管道异常：%s", exc)

    # 盘中速报：每 N 分钟跑一次，run_movers 内部自带交易时段门控
    if settings.market.enabled:
        @sched.scheduled_job(
            IntervalTrigger(minutes=settings.schedule.intraday_every_minutes)
        )
        def _intraday() -> None:
            try:
                pipeline.run_movers(settings)
            except Exception as exc:
                log.exception("盘中速报异常：%s", exc)

    log.info(
        "调度器已启动：每天 %s 简报 + 每 %d 分钟盘中速报(%s)；Ctrl+C 退出",
        settings.schedule.daily_at,
        settings.schedule.intraday_every_minutes,
        settings.schedule.timezone,
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("调度器退出")
