# 规格说明 SPEC — notify

定义本系统「做什么、产出什么、达到什么标准」。架构取舍见 [docs/PLAN.md](docs/PLAN.md)；
代码导航与规范见 [CLAUDE.md](CLAUDE.md)。

状态标记：✅ 已实现 · 🚧 规划中。

---

## 1. 目标与范围

每日 / 盘中自动采集资讯与行情，经 AI 分析后推送到微信与飞书，覆盖领域：

- AI / 大模型
- 美股科技
- 存储（内存 / HDD / SSD / HBM）
- CPO / 光模块（共封装光学）
- 半导体
- 宏观财经大事件

**只做美股**（科技 / 存储 / CPO / AI / 半导体）。

**不在范围**：A 股 / 港股、自动交易 / 下单、投资建议、高频或秒级行情。

---

## 2. 运行模式与频率

| 模式 | 触发 | 动作 | 状态 |
|---|---|---|---|
| 每日简报 | 每天定时（开盘前 / 收盘后） | 汇总当日新闻 → AI 结构化分析 → 推送简报 | ✅ |
| 盘中速报 | 美股交易时段每小时 | 拉行情 → 检测暴涨暴跌 → 推送速报（纯规则，可选叠加 AI 归因） | ✅ |

约束：盘中速报仅在美股交易时段运行；任一模式跑一遍均**幂等**，靠去重不重复推送。

---

## 3. 功能需求

### FR-1 新闻采集 ✅（RSS）/ 🚧（RSSHub、新闻 API）
- 支持多源并发拉取；单源失败只记录并跳过，不中断整体。
- 每条新闻标准化为统一结构（见 §6 `NewsItem`）。
- 来源类型：RSS 直订 ✅；RSSHub 中转 🚧；Finnhub / NewsAPI / TianAPI 等 API 🚧。

### FR-2 行情采集 ✅
- 拉取关注标的的最新价、前收价、成交量、10 日均量等（见 §6 `Quote`）。
- 主源 CNBC 报价接口（免 key，含均量）；单标的失败退回 Nasdaq 接口（免 key）。
- 每次拉取写入行情快照，作为小时级异动对比基线。

### FR-3 处理与去重 ✅
- 新闻按回溯窗口 `lookback_hours` 过滤旧闻；无发布时间的条目保留。
- 跨运行去重：以 URL（缺失退回标题）的指纹持久化已推送内容，避免重复推送。
- 去重指纹按保留天数自动清理。

### FR-4 异动检测 ✅
- 按 §7 口径计算涨跌幅与量能异常，产出异动告警（见 §6 `MoverAlert`）。纯规则，无需 LLM。
- 冷却期内同标的同方向同口径不重复告警。

### FR-5 AI 分析 ✅（每日）/ 🚧（速评）
- 一次调用覆盖全部主题，产出结构化结论 + 跨主题综述（见 §6 `Report`）。
- 模型输出要求为 JSON，需稳健解析（容忍代码围栏与前后散文）。
- provider 可在配置中切换：anthropic / openai / deepseek / dashscope ✅。
- 区分两套提示词：每日综述 ✅ / 异动速评 🚧。

### FR-6 推送 ✅（飞书、PushPlus、Server酱）/ 🚧（其他）
- 飞书自定义机器人交互卡片，支持加签校验 ✅。
- 微信中转：PushPlus ✅ / Server酱 ✅。
- 可选渠道：企业微信机器人 / Bark / ntfy / Telegram Bot 🚧。
- 多渠道相互独立，单渠道失败不影响其他；全部失败则不标记已读，留待重试。

### FR-7 调度 ✅
- daemon 模式内置定时器：每日简报 + 盘中每小时速报（交易时段门控）。
- 触发器无关：同一「跑一次」命令可由 Docker / cron / launchd / n8n / GitHub Actions 驱动。
- 推荐 GitHub Actions：自带每日与盘中两个 cron 工作流，零服务器、$0。

### FR-8 配置与密钥 ✅
- 业务配置（数据源、标的、阈值、渠道开关、调度）入库于配置文件。
- 密钥仅来自环境变量，不入库。
- 提供自检命令，列出可用数据源、LLM 是否就绪、启用的推送渠道。

---

## 4. 数据源清单

| 类别 | 源 | 是否需 key | 状态 |
|---|---|---|---|
| 新闻 | 财经媒体 RSS（CNBC / Yahoo / MIT TR / VentureBeat / Tom's HW / SemiEngineering 等） | 否 | ✅ |
| 新闻 | RSSHub 中转（雪球 / 新浪财经 / 华尔街见闻 / SEC 等） | 否（自建） | 🚧 |
| 新闻 | Finnhub / NewsAPI / TianAPI | 是 | 🚧（Finnhub 框架已留） |
| 行情 | Yahoo chart 接口（美股，主） | 否 | ✅ |
| 行情 | Stooq CSV（美股，兜底） | 否 | ✅ |
| 行情 | Finnhub / Alpha Vantage（美股，可选增强） | 是 | 🚧 |

---

## 5. 关注标的（默认 watchlist）

| 分组 | 标的 |
|---|---|
| 科技 | NVDA MSFT GOOGL META AMZN AAPL TSLA PLTR ARM |
| AI | NVDA AMD SMCI AVGO TSM |
| 存储 | MU WDC STX PSTG NTAP |
| CPO / 光模块 | AVGO MRVL COHR LITE POET |

标的列表来自配置，可增删。

---

## 6. 设计契约（数据结构）

> 字段名即接口契约，跨模块稳定。✅ 现有 / 🚧 规划。

**NewsItem** ✅ — 一条标准化资讯
`source` 来源名 · `topic` 主题（ai/us_tech/finance/semiconductor…）· `title` · `url`
· `summary` 摘要 · `published_at` 发布时间 · `fingerprint` 去重指纹（派生）

**Quote** ✅ — 一条行情快照
`symbol` · `price` 最新价 · `prev_close` 前收 · `change_pct` 日内涨跌幅（派生）·
`volume` · `avg_volume` 10 日均量 · `source`

**MoverAlert** ✅ — 一条异动告警
`symbol` · `window`（daily/hourly/volume）· `change_pct` · `price` · `reason` 规则文案（可叠加 AI 归因）
· `direction`/`cooldown_key`（派生，用于冷却去重）

**TopicAnalysis** ✅ — 单主题 AI 结论
`topic` · `headline` 一句话结论 · `bullets` 要点列表 · `sentiment`（bullish/bearish/neutral/mixed）
· `tickers` 相关标的

**Report** ✅ — 一次运行的报告
`title` · `generated_at` · `analyses` 各主题结论 · `overview` 全局综述 · `stats` 各主题条数

---

## 7. 异动判定口径 ✅

- 日内涨跌幅 = (price − prev_close) / prev_close；`|日内涨跌幅| ≥ daily_threshold`（默认 5%）触发。
- 小时涨跌幅 = (price − 上一快照 price) / 上一快照 price；`|小时涨跌幅| ≥ hourly_threshold`（默认 3%）触发。
- 量能异常：volume ≥ avg_volume × `volume_multiple`（默认 3）触发。
- 冷却：同 `symbol` 同方向在 `cooldown_hours`（默认 4h）内只告警一次。

阈值、倍数、冷却期均为配置项。

---

## 8. 配置项（config + 环境变量）

**业务配置**：调度（时区 / 每日时间 / 盘中频率）、LLM（provider / model / 采样参数）、
数据源列表、watchlist、处理参数（回溯窗口 / 每主题上限 / 去重库 / 保留天数）、
异动阈值 🚧、推送渠道开关、报告标题。

**环境变量（密钥）**：各 LLM provider key、数据源 API key（可选）、各推送渠道
token / webhook / secret。详见 `.env.example`。

---

## 9. 验收标准

| 编号 | 标准 | 状态 |
|---|---|---|
| AC-1 | 自检命令能列出可用数据源、LLM 就绪状态、启用渠道 | ✅ |
| AC-2 | 采集命令能从可用源拉到资讯并按源打印条数 | ✅ |
| AC-3 | dry-run 能产出结构化报告且不推送、不写去重库 | ✅ |
| AC-4 | 正式运行能推送到至少一个渠道并标记已读 | ✅ |
| AC-5 | 重复运行不重复推送同一条内容 | ✅ |
| AC-6 | 单个数据源失败不影响整体运行 | ✅ |
| AC-7 | 切换 LLM provider 仅改配置即可生效 | ✅ |
| AC-8 | 行情拉取产出 `Quote` 并写入快照基线 | ✅ |
| AC-9 | 阈值触发时产出 `MoverAlert` 并推送速报，冷却期内不重复 | ✅ |
| AC-10 | 盘中任务仅在交易时段运行（`--force` 可绕过） | ✅ |

---

## 10. 约束与免责

- **非投资建议**：仅做信息采集、摘要与异动提醒，不预测涨跌、不给买卖点，决策自负。
- **行情延迟**：免费源约 15 分钟延迟，不适用于高频 / 秒级交易。
- **只读不写**：不接券商、不下单、不执行交易。
- **合规使用**：遵守各数据源与 API 的调用频率与服务条款。
