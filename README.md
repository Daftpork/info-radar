# 信息雷达 info-radar

个人 AI 信息雷达。四款 tracker 跑在 GitHub Actions 上，把带观点的中文情报邮件送到你收件箱。灵感来自即刻上 Vanessa 的三款 Tracker，做成自己的、独立的、云端常驻版本。

## 四款 tracker

| tracker | 频率（北京时间） | 抓什么 |
|---|---|---|
| **Thinker** | 每天 07:50 | AI 大佬的观点：X 推文(follow-builders feed) + 深度长文(博客RSS) + 视频(YouTube字幕) + 播客(Whisper转录) |
| **Trend** | 每周一三五 10:15 | 热门项目两半区：通用(Product Hunt / Hugging Face / GitHub / arXiv) + GitHub 设计精选 |
| **Feature** | 每周五 09:10 | 御三家(OpenAI / Anthropic / Google) 产品更新 |
| **DeepDive 行业深潜** | 每周日 09:05 | 从本周热点里挑一个赛道，Exa 深挖，写一篇带第一人称判断的长文 |

处理逻辑：curated 低量源（Thinker/Feature）只去重 + LLM 带观点提炼；firehose 高量源（Trend）LLM 打分选 Top-N。全部输出 Vanessa 风格的中文日报。

## 架构

```
core/     llm(yuyu→liaobots→anthropic fallback) · notify(SMTP邮件) · models · state(JSON持久化) · scorer · digest · prompts
fetchers/ followbuilders · rss · youtube · podcast · github · huggingface · arxiv · producthunt · htmlnews · exa
trackers/ thinker · trend · feature · deepdive
prompts/  各 tracker 的提炼/深潜 prompt（外置，方便调优）
state/    去重、趋势历史（CI 每次运行 commit 回仓，实现跨运行持久化）
output/   日报归档
```

- **LLM**：复刻 Lumio 的 provider 链，主 yuyu(yylx) → 备 liaobots → 兜底 anthropic。yuyu 走裸 httpx 绕它的 content-type bug。
- **状态持久化**：GitHub Actions 无状态，所以去重/趋势历史存 JSON，每次运行结尾 commit 回仓。

## 本地运行

```bash
python3.12 -m venv .venv && ./.venv/bin/pip install -e .
cp .env.example .env   # 填入密钥
./.venv/bin/python run.py thinker --dry-run   # 抓取+生成打印，不发邮件
./.venv/bin/python run.py trend               # 真跑（需配好 EMAIL_*）
```

播客转录需要本地装 ffmpeg（`brew install ffmpeg`）。

## GitHub Secrets 清单

在 repo 的 Settings → Secrets and variables → Actions 里配：

**必填**
- `YUYU_API_KEY`、`LIAOBOTS_API_KEY` — LLM（可从 Lumio 的 .env 取，或重新签发）
- `EMAIL_FROM` — 发信 Gmail 地址
- `EMAIL_PASSWORD` — Gmail **应用专用密码**（不是登录密码，在 Google 账号安全设置里生成）
- `EMAIL_TO` — 收件邮箱（QQ 也行，Gmail→QQ 送达率好）

**建议填**
- `WHISPER_API_KEY` + `WHISPER_BASE_URL` + `WHISPER_MODEL` — 播客转录（推荐 Groq `whisper-large-v3-turbo`，有免费额度；或 OpenAI `whisper-1`）

> Product Hunt 走公开 RSS，**无需 token**（官方 API 已限制申请）。

**可选**
- `ANTHROPIC_API_KEY` — LLM 兜底
- `EXA_API_KEY` — 行业深潜的深挖检索
- `YUYU_BASE_URL` / `LIAOBOTS_BASE_URL` / `ANTHROPIC_BASE_URL` — 仅当端点非默认时才填

`GITHUB_TOKEN` 由 Actions 自动注入，无需手配。

## 调整

- 追踪名单：改 `config.py`（博客 RSS、YouTube 频道、播客、设计 topic 等）。
- 各 tracker 时间：改对应 `.github/workflows/*.yml` 的 cron。
- 提炼口味：改 `prompts/*.md`。
