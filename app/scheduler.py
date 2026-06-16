"""daemon 模式：进程常驻，每天定时跑一次 pipeline。

仅在「本地常驻 / 容器内不依赖外部 cron」时使用。若用 Docker cron / launchd /
n8n 触发，则直接调 `run` 子命令即可，无需本模块。
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Settings
from . import pipeline

log = logging.getLogger("scheduler")


def run_forever(settings: Settings) -> None:
    hour, minute = (int(x) for x in settings.schedule.daily_at.split(":"))
    sched = BlockingScheduler(timezone=settings.schedule.timezone)

    @sched.scheduled_job(
        CronTrigger(hour=hour, minute=minute, timezone=settings.schedule.timezone)
    )
    def _job() -> None:
        log.info("定时触发，开始执行管道")
        try:
            pipeline.run(settings)
        except Exception as exc:  # 守护循环不能被单次失败打断
            log.exception("本次管道执行异常：%s", exc)

    log.info(
        "调度器已启动：每天 %s (%s) 运行；Ctrl+C 退出",
        settings.schedule.daily_at,
        settings.schedule.timezone,
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("调度器退出")
