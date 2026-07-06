"""数据源名单配置 —— 随手可改。所有列表都是「起步集」，按需增删。

Thinker 四种源：X（follow-builders feed，名单在上游）+ 博客RSS + YouTube + 播客。
Trend / Feature 的配置在文件下半部。
"""

# ===========================================================================
# Thinker —— 深度长文（博客 / Substack 的 RSS）
# 这些是我确认可用的 AI 思想者 feed，按需增删。
# ===========================================================================
THINKER_BLOGS = [
    {"name": "Simon Willison", "bio": "独立开发者", "rss": "https://simonwillison.net/atom/everything/"},
    {"name": "Ethan Mollick", "bio": "沃顿教授", "rss": "https://www.oneusefulthing.org/feed"},
    {"name": "Azeem Azhar", "bio": "Exponential View 创始人", "rss": "https://www.exponentialview.co/feed"},
    {"name": "Nathan Lambert", "bio": "Interconnects / AI2", "rss": "https://www.interconnects.ai/feed"},
    {"name": "Jack Clark", "bio": "Anthropic 联创 / Import AI", "rss": "https://jack-clark.net/feed/"},
    {"name": "Ben Thompson", "bio": "Stratechery", "rss": "https://stratechery.com/feed/"},
    {"name": "Gergely Orosz", "bio": "The Pragmatic Engineer", "rss": "https://blog.pragmaticengineer.com/rss/"},
    {"name": "Lenny Rachitsky", "bio": "产品专家", "rss": "https://www.lennysnewsletter.com/feed"},
    {"name": "Marty Cagan", "bio": "SVPG / 产品", "rss": "https://www.svpg.com/feed/"},
    {"name": "Teresa Torres", "bio": "Product Talk / 产品发现", "rss": "https://www.producttalk.org/feed/"},
    {"name": "Derek Sivers", "bio": "CD Baby 创始人 / 作家", "rss": "https://sivers.org/en.atom"},
]

# ===========================================================================
# Thinker —— YouTube 频道（视频 / 视频播客）
# 用 @handle，fetcher 会自动解析成 channelId（更稳，handle 不易变）。
# 注意：与下面播客列表不重复，避免同一节目被抓两遍。
# ===========================================================================
THINKER_YOUTUBE = [
    {"name": "Latent Space", "bio": "AI 工程播客", "handle": "@LatentSpacePod"},
]

# ===========================================================================
# Thinker —— 纯音频播客（RSS，走 Whisper 转录）。feedUrl 来自 Apple 播客接口。
# ===========================================================================
THINKER_PODCASTS = [
    {"name": "No Priors", "bio": "Sarah Guo & Elad Gil / AI 投资", "rss": "https://feeds.megaphone.fm/nopriors"},
    {"name": "Dwarkesh Podcast", "bio": "Dwarkesh Patel", "rss": "https://apple.dwarkesh-podcast.workers.dev/feed.rss"},
    {"name": "Lenny's Podcast", "bio": "Lenny Rachitsky / 产品", "rss": "https://api.substack.com/feed/podcast/10845.rss"},
    {"name": "Behind the Craft", "bio": "Peter Yang / 产品", "rss": "https://anchor.fm/s/f38497cc/podcast/rss"},
    {"name": "20VC", "bio": "Harry Stebbings / 风投", "rss": "https://rss.libsyn.com/shows/61840/destinations/240976.xml"},
    {"name": "Y Combinator Podcast", "bio": "YC", "rss": "https://anchor.fm/s/8c1524bc/podcast/rss"},
    {"name": "The Naval Podcast", "bio": "Naval Ravikant", "rss": "https://rss.libsyn.com/shows/166112/destinations/1103966.xml"},
    {"name": "How I Built This", "bio": "Guy Raz / 创业故事", "rss": "https://rss.art19.com/how-i-built-this"},
    {"name": "Forward Thinking Founders", "bio": "创业者访谈", "rss": "https://feeds.transistor.fm/forward-thinking-founder"},
    # 中文播客（feed.xyzfm.space 即小宇宙的 RSS）
    {"name": "晚点聊 LateTalk", "bio": "晚点团队 / 科技访谈", "rss": "https://feeds.fireside.fm/latetalk/rss"},
    {"name": "42章经", "bio": "曲凯 / 科技投资", "rss": "https://feed.xyzfm.space/evgg6xle9rdc"},
    {"name": "张小珺商业访谈录", "bio": "张小珺 / 商业深访", "rss": "https://feed.xyzfm.space/dk4yh3pkpjp3"},
    {"name": "十字路口Crossing", "bio": "AI 创业播客", "rss": "https://feed.xyzfm.space/68fyjknth9hj"},
]

# 是否把 follow-builders 已转录的 6 档播客也纳入（免费兜底，当自建 Whisper 拉空时有用）
THINKER_USE_FOLLOWBUILDERS_PODCASTS = True

# Thinker 单次日报最多展示多少条
THINKER_KEEP = 12
# 各源回看窗口（小时）
THINKER_LOOKBACK_HOURS = 30


# ===========================================================================
# Trend —— 通用热门 + GitHub 设计精选（每周一三五）
# ===========================================================================
# 通用半区：各源各取多少送进打分
TREND_GITHUB_TOPICS_GENERAL = None      # None = 用 GitHub Trending（AI 相关过滤）
TREND_KEEP_GENERAL = 12                  # 通用半区最终保留条数
TREND_KEEP_DESIGN = 5                    # 设计半区最终保留条数
TREND_LOOKBACK_HOURS = 72

# 设计半区：GitHub 上按这些 topic 搜设计类仓库（每个 topic 一次请求，故精简数量）
TREND_DESIGN_TOPICS = [
    "design-system", "design-tools", "ui", "figma",
    "icons", "animation", "tailwindcss", "shaders",
]
# arXiv 抓取的分类
TREND_ARXIV_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG", "cs.HC", "cs.RO"]
# Product Hunt 抓取的 topic
TREND_PH_TOPICS = ["artificial-intelligence", "developer-tools", "design-tools"]


# ===========================================================================
# Feature —— 御三家产品更新（每周五）
# OpenAI/Anthropic 无干净 RSS，用 HTML 索引解析；Google 有 RSS。
# ===========================================================================
FEATURE_SOURCES = [
    {"company": "OpenAI", "type": "rss", "url": "https://openai.com/news/rss.xml"},
    {"company": "Anthropic", "type": "html", "url": "https://www.anthropic.com/news"},
    {"company": "Google DeepMind", "type": "rss", "url": "https://blog.google/technology/google-deepmind/rss/"},
    {"company": "Google AI", "type": "rss", "url": "https://blog.google/technology/ai/rss/"},
]
FEATURE_LOOKBACK_HOURS = 24 * 8  # 一周多一点，容忍偶尔漏跑
FEATURE_KEEP = 12


# ===========================================================================
# 行业深潜 —— 每周挑一个最热主题深挖
# ===========================================================================
DEEPDIVE_ENABLED = True
DEEPDIVE_EXA_QUERIES_PER_TOPIC = 6
