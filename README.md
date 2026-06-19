# notify — 每日 AI · 美股 · 财经资讯简报机器人

每天定时拉取 AI / 美股科技 / 存储 / CPO（光模块）/ 半导体 / 宏观财经的新闻资讯，
经 AI 分析提炼成结构化结论，推送到**微信**（PushPlus / Server酱）和**飞书**机器人。

```
[定时触发] → 并发采集多源 → 过滤窗口+去重 → 按主题分组
           → LLM 分析(结构化) → 渲染卡片 → 推送 微信/飞书 → 标记已读
```

整条管道是**一次运行即幂等**的：谁来触发都安全，靠 SQLite 去重保证不重复推送。

## 特性

- **多数据源**：RSS（零配置、无需 key）+ Finnhub 等 API 源（可选，缺 key 自动跳过）。单源失败不影响整体。
- **可切换 LLM**：`anthropic` / `openai` / `deepseek` / `dashscope`，改 `config.yaml` 两行即可切换。
- **多推送渠道**：飞书自定义机器人（支持加签）、PushPlus、Server酱，按开关启用。
- **去重持久化**：跨运行记忆已推送内容，不重复轰炸。
- **触发器无关**：Docker 常驻定时 / 宿主 cron / launchd / n8n Schedule 节点都能驱动。

## 文档

- [SPEC.md](SPEC.md) — 规格说明：功能需求、数据源、异动判定、设计契约、验收标准（✅已实现 / 🚧规划）
- [docs/PLAN.md](docs/PLAN.md) — 技术方案：三方方案对比、自建目标架构、落地路线图
- [CLAUDE.md](CLAUDE.md) — 项目级开发指引：架构导航、设计不变量、扩展点、规范

## 目录结构

```
app/
  collectors/   采集层：rss / finnhub + registry（按 key 可用性筛选）
  llm/          LLM 抽象：anthropic_client / openai_compat + factory（按 provider 构造）
  notifiers/    推送层：feishu / pushplus / serverchan + render（渲染卡片）
  analyzer.py   构造 prompt、调用 LLM、解析结构化结论
  dedup.py      SQLite 已推送指纹存储
  pipeline.py   编排：采集→去重→分析→推送
  scheduler.py  daemon 模式定时器（APScheduler）
  __main__.py   CLI 入口
config.yaml     业务配置（数据源、标的、LLM、推送、调度）
.env            密钥（不入库，见 .env.example）
```

## 快速开始（本地）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 填入你启用的 LLM key 与推送渠道 key

python -m app check                 # 自检：数据源 / LLM / 行情 / 推送渠道是否就绪
python -m app collect               # 只采集新闻、打印各源条数（排查数据源）
python -m app quotes                # 只拉美股行情、打印（排查行情源）
python -m app brief NVDA            # 即时查询单只票：行情+新闻+8-K公告+AI 点评
python -m app brief NVDA --push     # 同上并推送到飞书/微信
python -m app run --dry-run         # 每日简报跑一遍但不推送、不写去重库
python -m app run                   # 每日简报正式跑：采集→AI 分析→推送
python -m app movers --dry-run --force  # 盘中异动检测预览（不推送、绕过交易时段门控）
python -m app movers                # 盘中异动速报：拉行情→检测→推送（仅交易时段）
python -m app events                # 重大事件速报：SEC 8-K 命中即推（--dry-run 预览）
python -m app crypto                # 币圈暴涨暴跌速报：主流币行情→检测→推送（24/7）
python -m app schedule              # 常驻：每日简报 + 盘中速报 + 重大事件 + 币圈
```

> **异动速报无需 LLM**：暴涨暴跌检测是纯规则的，没有任何 API key 也能跑通推送。
> 配置了 LLM（如 Groq/Gemini 免费档）则额外：给每日简报做分析、并给异动个股关联近期
> 新闻做一句话「为什么涨/跌」AI 归因。行情源（CNBC/Nasdaq）免 key。

## 配置

### 密钥（`.env`）
只需填你**实际启用**的项，详见 `.env.example`：
- LLM：按 `config.yaml` 的 `llm.provider` 填对应 key（如 `ANTHROPIC_API_KEY`）。
- 微信：`PUSHPLUS_TOKEN` 或 `SERVERCHAN_SENDKEY`。
- 飞书：`FEISHU_WEBHOOK_URL`（开启加签则再填 `FEISHU_WEBHOOK_SECRET`）。
- 数据源：`FINNHUB_API_KEY` 等可选；不填则只用免费 RSS。

### 业务（`config.yaml`）
- `sources`：数据源列表，`type: rss` 无需 key；新增源加一条即可。
- `watchlist`：关注标的（科技/AI/存储/CPO），作为 AI 判断影响的上下文。
- `processing`：回溯窗口 `lookback_hours`、每主题上限 `max_items_per_topic`、去重库路径与保留天数。
- `notifiers`：各渠道 `enabled` 开关。
- `schedule`：daemon 模式的时区与每日触发时间。

### 切换 LLM（含免费白嫖档）
改 `config.yaml` 的 provider/model 两行，并在 `.env` 填对应 key：
```yaml
llm:
  provider: "groq"          # groq | gemini | deepseek | anthropic | openai | dashscope
  model: "llama-3.3-70b-versatile"
```
- **白嫖推荐**：`groq`（免费、快）或 `gemini`（免费，Flash 系列够用）。
- 要质量好又便宜：`deepseek`。
- 这些都通过 OpenAI 兼容端点接入，切换零代码。

## 部署

### GitHub Actions（最省事的免费白嫖，推荐）

仓库自带两个工作流，零服务器、$0：

- [.github/workflows/daily.yml](.github/workflows/daily.yml) — 每日简报（北京时间 07:00 前后）
- [.github/workflows/intraday.yml](.github/workflows/intraday.yml) — 盘中每小时异动速报（交易时段由代码门控）
- [.github/workflows/events.yml](.github/workflows/events.yml) — 每小时 SEC 8-K 重大事件速报（不限时段）

用法：fork / push 到 GitHub → 仓库 **Settings → Secrets and variables → Actions** 里填密钥
（`FEISHU_WEBHOOK_URL`、`PUSHPLUS_TOKEN`、`ANTHROPIC_API_KEY` 等，按需）→ 工作流自动按 cron 跑。
去重库/行情快照用 `actions/cache` 跨运行保留（长期可靠去重建议换 Turso / Cloudflare D1）。

LLM 也能白嫖：每日简报可用 Gemini / Groq 免费档或 DeepSeek 低价；异动速报纯规则，无需 LLM。

### Docker（推荐）
```bash
cp .env.example .env   # 填好密钥
docker compose up -d   # 默认 daemon：容器内每天定时触发
docker compose logs -f notify
```
去重库挂载在 `./data`，重建容器不丢去重记忆。

### 宿主 crontab / macOS launchd
让脚本跑一次即退出，交给系统定时：
```bash
# crontab -e ，每天 07:00（容器版同理用 docker compose run --rm）
0 7 * * *  cd /path/to/notify && .venv/bin/python -m app run >> run.log 2>&1
```

### n8n
用 n8n 只做**触发**，业务逻辑仍在本项目：
- **Schedule** 节点（每天 07:00）→ **Execute Command** 节点：`docker compose run --rm notify python -m app run`。
- 或把容器以方式 B（`run` 一次即退）暴露，由 n8n 定时拉起。

> 不建议把采集/去重/分析逻辑搬进 n8n 的 Function 节点——本项目这些逻辑放在代码里更易测试与维护。

## 微信推送说明

个人微信没有官方 webhook，本项目通过 **PushPlus** 或 **Server酱** 中转到个人微信：
注册拿 token/SendKey 填进 `.env`，在 `config.yaml` 把对应渠道 `enabled: true` 即可。

## 测试

```bash
python -m pytest -q     # 离线核心逻辑：去重 / JSON 解析 / 渲染
```

## 扩展

- **加数据源**：实现一个 `Collector` 子类（参考 `collectors/rss.py`），在 `collectors/registry.py` 注册类型；RSS 源则直接往 `config.yaml` 加一行。
- **加 LLM provider**：OpenAI 兼容的在 `llm/factory.py` 的 `_PROVIDERS` 加一行即可。
- **加推送渠道**：实现 `Notifier` 子类，在 `notifiers/registry.py` 注册。
