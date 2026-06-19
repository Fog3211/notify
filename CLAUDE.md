# CLAUDE.md — 项目级开发指引

> 本文件供 Claude Code 在本仓库工作时自动加载。全局个人规范（注释维护、Git 提交、
> 技术方案文档写法等）仍然适用，本文件只补充**本项目特有**的约定。

## 项目是什么

每日 / 盘中自动采集 **美股**（科技 · 存储 · CPO · AI · 半导体）与财经 AI 资讯及行情，
经 AI 分析后推送到微信（PushPlus / Server酱）与飞书机器人。
**只做美股、不做 A 股；自建、全代码、尽量白嫖、触发器无关。**

- 需求与验收：[SPEC.md](SPEC.md)
- 架构取舍与决策：[docs/PLAN.md](docs/PLAN.md)
- 使用与部署：[README.md](README.md)

## 当前状态

- ✅ 资讯链路：新闻采集（RSS）→ 去重 → 每日 AI 结构化分析 → 推送（飞书 / PushPlus / Server酱）；
  LLM provider 可切换（含 Groq / Gemini 免费档，OpenAI 兼容端点接入）；离线单测；Docker。
- ✅ 行情/异动链路：美股行情采集（CNBC + Nasdaq 兜底，免 key）→ 暴涨暴跌异动检测
  （阈值 + 冷却去重）→ 异动速报渲染推送（纯规则可跑，配 LLM 时叠加关联新闻的一句话 AI 归因）。
- ✅ 多频率：每日简报 + 盘中每小时速报（交易时段门控）；GitHub Actions 两个 cron 工作流。
- ✅ 实时事件源：Finnhub（市场/公司新闻、免费 key）+ SEC EDGAR 8-K 重大事件（免 key，
  ticker→CIK，条目代码中文化，topic=events）；`brief <ticker>` 即时查询（行情+新闻+8-K+AI 点评）。
- 🚧 规划中：RSSHub 中文财经源、Finnhub 经济/财报日历入简报、更多推送渠道（企业微信 / Bark / ntfy）、
  8-K 命中即单独推。详见 SPEC 的状态标记与 PLAN 的路线图。**A 股不做。**

## 架构与数据流

```
采集(collectors) → 过滤窗口+去重(dedup) → 按主题分组 → AI 分析(analyzer)
  → 渲染(notifiers/render) → 推送(notifiers) → 标记已读(dedup)
```

目录结构：

```
app/
  collectors/   采集层：base / rss / finnhub / sec(8-K) + registry（按 key 可用性筛选源）
  market/       行情/异动：provider(CNBC+Nasdaq) / movers / snapshot / hours / attribution
  llm/          LLM 抽象：base / anthropic_client / openai_compat + factory（按 provider 构造）
  notifiers/    推送层：base / feishu / pushplus / serverchan + render + message + registry
  analyzer.py   构造 prompt、调 LLM、解析结构化结论
  brief.py      brief <ticker> 即时查询（行情+新闻+8-K+AI 点评）
  config.py     合并 config.yaml(业务) + .env(密钥) 成强类型 Settings
  models.py     NewsItem / Quote / MoverAlert / TopicAnalysis / Report
  dedup.py      SQLite 去重指纹存储
  http.py       共享 httpx.Client（浏览器 UA，绕过部分站点 403/429）
  pipeline.py   编排：run(每日简报) / run_movers(盘中速报)，一次运行即幂等
  scheduler.py  daemon 定时器（每日 + 盘中每小时，APScheduler）
  __main__.py   CLI 入口：run / movers / brief / collect / quotes / check / schedule
config.yaml     业务配置        .env(.example)  密钥
tests/          离线单测（去重 / JSON 解析 / 渲染）
```

## 常用命令

```bash
source .venv/bin/activate
python -m app check          # 自检：数据源 / LLM / 行情 / 渠道
python -m app collect        # 只采集新闻并打印各源条数
python -m app quotes         # 只拉美股行情并打印
python -m app brief NVDA     # 即时查询单票：行情+新闻+8-K+AI 点评（--push 推送）
python -m app run --dry-run  # 每日简报跑一遍不推送、不写去重库
python -m app run            # 每日简报正式跑一次
python -m app movers --force # 盘中异动速报（--force 绕过交易时段）
python -m pytest -q          # 离线单测
```

## 必须遵守的设计不变量

改动时不要破坏以下约束（它们是系统正确性的基础）：

1. **一次运行即幂等**：任何触发器跑一遍都安全，靠去重保证不重复推送。
2. **触发器无关**：业务逻辑收敛在「跑一次」的命令里，不耦合具体调度方式。
3. **单源容错**：采集器 / 推送器单个失败只记录并跳过，绝不让一个源 / 渠道拖垮整体。
4. **密钥只走环境变量**：不把任何 key / token / webhook 写进 config.yaml 或代码。
5. **去读后置标记**：仅在推送成功后才标记已读；全渠道失败则不标记，留待下次重试。
6. **provider 切换零代码**：新增 OpenAI 兼容 provider 只在 `llm/factory.py` 注册一行。

## 扩展点（加东西时照这里走）

- **加数据源**：实现 `collectors/base.py` 的 `Collector` 子类，在 `collectors/registry.py`
  注册类型（含所需 env key）；纯 RSS 源直接往 `config.yaml` 的 `sources` 加一行。
- **加 LLM provider**：OpenAI 兼容的在 `llm/factory.py` 的 `_PROVIDERS` 加一行。
- **加推送渠道**：实现 `notifiers/base.py` 的 `Notifier` 子类，在 `notifiers/registry.py` 注册。
- **加行情 / 异动（🚧）**：行情采集独立成模块产出 `Quote`；异动检测按 SPEC §7 口径产出
  `MoverAlert`；接入现有 AI 与推送能力，复用 dedup 思路做冷却去重。

## 开发规范（本项目）

- **注释**：遵循全局规范——改逻辑同步改注释，删代码删对应注释，注释解释「为什么」。
- **新增功能须可自检**：能跑 `check` / `dry-run` 验证，不依赖真实推送也能验证主链路。
- **新增逻辑配离线测试**：去重 / 解析 / 渲染等不依赖网络与 key 的逻辑写进 `tests/`。
- **文档同源**：改了行为要同步更新 SPEC（功能/验收）与 PLAN（若涉及架构决策）。
- **Git 提交**：英文、Conventional Commits、保留 `Co-Authored-By`（遵循全局规范）。
- **技术方案文档**：PLAN/SPEC 按模块与数据流描述，正文不写文件路径与代码行号（遵循全局规范）。

## 重要约束（务必在产出与代码中体现）

- **非投资建议**：系统只做信息采集、摘要与异动提醒，**不预测涨跌、不给买卖点**。
- **行情延迟**：免费行情源约 15 分钟延迟，不用于高频 / 秒级交易判断。
- **只读不写**：不接券商、不下单、不执行交易。
