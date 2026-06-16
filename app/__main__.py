"""CLI 入口。

用法:
  python -m app run            跑一次完整管道（采集->分析->推送）
  python -m app run --dry-run  跑一次但不推送、不写去重库，仅打印报告
  python -m app collect        只采集并打印条数（排查数据源用）
  python -m app schedule       常驻进程，每天定时运行
  python -m app check          检查配置/密钥/渠道是否就绪
"""

from __future__ import annotations

import argparse
import sys

from . import pipeline, scheduler
from .collectors.registry import build_collectors
from .config import load_settings
from .llm.factory import build_llm
from .llm.base import LLMError
from .logging_setup import setup_logging
from .notifiers.registry import build_notifiers


def _cmd_run(settings, args) -> int:
    # 「无新内容」也是正常退出（return 0）；异常会以未捕获形式抛出非 0。
    pipeline.run(settings, dry_run=args.dry_run)
    return 0


def _cmd_collect(settings, args) -> int:
    from .http import make_client

    collectors = build_collectors(settings)
    total = 0
    with make_client() as client:
        for c in collectors:
            items = c.collect(client)
            total += len(items)
            print(f"  {c.source.name:<28} {len(items):>3} 条")
    print(f"合计 {total} 条 / {len(collectors)} 个可用源")
    return 0


def _cmd_schedule(settings, args) -> int:
    scheduler.run_forever(settings)
    return 0


def _cmd_check(settings, args) -> int:
    """开机自检：列出可用数据源、LLM 是否可构造、启用的推送渠道。"""
    print("== 数据源 ==")
    collectors = build_collectors(settings)
    for c in collectors:
        print(f"  ✓ {c.source.name} ({c.source.type}, topic={c.source.topic})")
    if not collectors:
        print("  ✗ 没有可用数据源")

    print("\n== LLM ==")
    try:
        build_llm(settings)
        print(f"  ✓ provider={settings.llm.provider} model={settings.llm.model}")
    except LLMError as exc:
        print(f"  ✗ {exc}")

    print("\n== 推送渠道 ==")
    notifiers = build_notifiers(settings)
    for n in notifiers:
        print(f"  ✓ {n.name}")
    if not notifiers:
        print("  ✗ 未启用任何渠道")
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = argparse.ArgumentParser(prog="app", description="每日 AI/股票/财经资讯简报")
    parser.add_argument("-c", "--config", help="配置文件路径（默认 config.yaml）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="跑一次完整管道")
    p_run.add_argument("--dry-run", action="store_true", help="不推送、不写去重库")
    p_run.set_defaults(func=_cmd_run)

    sub.add_parser("collect", help="只采集并打印条数").set_defaults(func=_cmd_collect)
    sub.add_parser("schedule", help="常驻定时运行").set_defaults(func=_cmd_schedule)
    sub.add_parser("check", help="自检配置/密钥/渠道").set_defaults(func=_cmd_check)

    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    return args.func(settings, args)


if __name__ == "__main__":
    sys.exit(main())
