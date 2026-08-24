# -*- coding: utf-8 -*-
"""
GitHub Trending Spider + Hacker News 配置文件

使用说明：
1. 复制此文件并根据实际情况修改配置
2. 确保不要将含有真实密钥的配置文件提交到版本控制

环境变量优先级高于默认值，推荐通过环境变量配置敏感信息。
"""

import os


def _get_bool_env(name, default=False):
    """读取布尔环境变量。"""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _get_http_header_env(name, default=""):
    """读取可安全用于 requests 请求头的 Latin-1 环境变量。"""
    value = os.environ.get(name, default)
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        return default
    return value


# =========================================================================
# AI API 配置（OpenRouter，OpenAI 兼容接口）
# =========================================================================

# AI 供应商标识。当前代码仅支持 OpenRouter。
AI_PROVIDER = os.environ.get("AI_PROVIDER", "openrouter")

# OpenRouter API Key。必须与 GitHub Token 分开，禁止回退读取 GITHUB_TOKEN。
AI_API_KEY = os.environ.get("AI_API_KEY", "")

# OpenRouter 可选应用标题请求头，用于控制台归因。
AI_APP_NAME = _get_http_header_env("AI_APP_NAME", "AI Daily Frontier")

# 默认仅让 OpenRouter 请求绕过系统代理，避免失效代理阻断全部 AI 摘要。
AI_BYPASS_PROXY = _get_bool_env("AI_BYPASS_PROXY", True)
AI_REQUEST_PROXIES = (
    {"http": "", "https": "", "all": ""} if AI_BYPASS_PROXY else None
)

# OpenRouter API 基础地址（OpenAI 兼容接口）
AI_API_URL = os.environ.get(
    "AI_API_URL", "https://openrouter.ai/api/v1"
)

# 固定模型 ID，避免 latest 别名静默切换版本。
AI_MODEL = os.environ.get("AI_MODEL", "deepseek/deepseek-v4-flash-0731")

# =========================================================================
# 各信息源抓取代理配置
# =========================================================================
# 服务器出口网络访问境外站点（github/hn/v2ex/tldr/openai/anthropic/infoq 等）
# 偶发不稳定，可通过本地 mihomo/clash 等代理软件转发。默认关闭，需显式开启。
SPIDER_USE_PROXY = _get_bool_env("SPIDER_USE_PROXY", False)
SPIDER_PROXY_URL = os.environ.get("SPIDER_PROXY_URL", "http://127.0.0.1:7890")
SPIDER_REQUEST_PROXIES = (
    {"http": SPIDER_PROXY_URL, "https": SPIDER_PROXY_URL} if SPIDER_USE_PROXY else None
)

# =========================================================================
# GitHub Trending 配置
# =========================================================================

# GitHub Trending 每日/每周分别获取前 N 个仓库
GITHUB_TRENDING_TOP_COUNT = int(os.environ.get("GITHUB_TRENDING_TOP_COUNT", "10"))

# =========================================================================
# 邮件配置 (163 邮箱 SMTP)
# =========================================================================

# 163 邮箱 SMTP 服务器
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.163.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
# 163 邮箱账号（发件人邮箱）
SMTP_USER = os.environ.get("SMTP_USER", "")
# 163 邮箱 SMTP 授权码（不是邮箱密码！）
# 获取方式：163邮箱 → 设置 → POP3/SMTP/IMAP → 开启 → 获取授权码
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# 发件人邮箱地址（通常与 SMTP_USER 相同）
MAIL_FROM = os.environ.get("MAIL_FROM", SMTP_USER)

# 收件人邮箱地址
MAIL_TO = os.environ.get("MAIL_TO", "727987105@qq.com, wenbo.chang@huolala.cn")

# 按调度时间指定收件人，JSON 对象格式：
# {"07:50":"a@example.com,b@example.com","15:50":["c@example.com"]}
MAIL_TO_BY_TIME = os.environ.get("MAIL_TO_BY_TIME", "")

# =========================================================================
# 日志配置
# =========================================================================

# 日志文件路径
LOG_FILE = os.environ.get(
    "LOG_FILE",
    "/root/logs/github-python/trending.log",
)

# =========================================================================
# Hacker News 配置
# =========================================================================

# HN 官方 Firebase API 基础地址
HN_API_BASE = os.environ.get(
    "HN_API_BASE", "https://hacker-news.firebaseio.com/v0"
)

# 获取前 N 个热门帖子
HN_TOP_COUNT = int(os.environ.get("HN_TOP_COUNT", "10"))

# 每个帖子获取前 N 条顶级评论
HN_COMMENTS_PER_STORY = int(os.environ.get("HN_COMMENTS_PER_STORY", "10"))

# HN 请求最大重试次数
HN_MAX_RETRIES = int(os.environ.get("HN_MAX_RETRIES", "5"))

# 并发请求线程数
HN_CONCURRENT_WORKERS = int(os.environ.get("HN_CONCURRENT_WORKERS", "10"))

# =========================================================================
# TLDR AI 配置
# =========================================================================

# TLDR AI 官方归档页
TLDR_AI_HOME_URL = os.environ.get(
    "TLDR_AI_HOME_URL", "https://ai.tldr.tech/"
)

# 获取前 N 条 TLDR AI 精选内容
TLDR_AI_TOP_COUNT = int(os.environ.get("TLDR_AI_TOP_COUNT", "10"))

# TLDR AI 请求最大重试次数
TLDR_AI_MAX_RETRIES = int(os.environ.get("TLDR_AI_MAX_RETRIES", "5"))

# =========================================================================
# V2EX 配置
# =========================================================================

# V2EX API 基础地址
V2EX_API_BASE = os.environ.get("V2EX_API_BASE", "https://www.v2ex.com/api")

# 获取前 N 个技术热帖
V2EX_TOP_COUNT = int(os.environ.get("V2EX_TOP_COUNT", "10"))

# 每个帖子获取前 N 条回复
V2EX_REPLIES_PER_TOPIC = int(os.environ.get("V2EX_REPLIES_PER_TOPIC", "10"))

# V2EX 请求最大重试次数
V2EX_MAX_RETRIES = int(os.environ.get("V2EX_MAX_RETRIES", "5"))

# V2EX 请求间隔（秒），避免触发限流
V2EX_REQUEST_INTERVAL = float(os.environ.get("V2EX_REQUEST_INTERVAL", "0.5"))

# ==============================================================ƒ===========
# Linux.do 技术日报配置
# =========================================================================

# Linux.do 技术聚合日报页面。只读取该页面摘要和原帖索引，不抓取原帖正文。
LINUX_DO_NEWS_URL = os.environ.get(
    "LINUX_DO_NEWS_URL", "https://news.linuxe.top/"
)

# Linux.do 原帖卡片最多展示 N 条；0 表示全部解析到的条目。
LINUX_DO_MAX_ITEMS = int(os.environ.get("LINUX_DO_MAX_ITEMS", "0"))

# Linux.do 请求最大重试次数
LINUX_DO_MAX_RETRIES = int(os.environ.get("LINUX_DO_MAX_RETRIES", "5"))

# =========================================================================
# 官方 AI / AI 工程实践信息源配置
# =========================================================================

# OpenAI 官方新闻页
OPENAI_NEWS_URL = os.environ.get(
    "OPENAI_NEWS_URL", "https://openai.com/news/"
)

# OpenAI 官方新闻 RSS
OPENAI_NEWS_RSS_URL = os.environ.get(
    "OPENAI_NEWS_RSS_URL", "https://openai.com/news/rss.xml"
)

# OpenAI 获取前 N 条内容
OPENAI_NEWS_COUNT = int(os.environ.get("OPENAI_NEWS_COUNT", "10"))

# Anthropic 官方新闻页
ANTHROPIC_NEWS_URL = os.environ.get(
    "ANTHROPIC_NEWS_URL", "https://www.anthropic.com/news"
)

# Anthropic 获取前 N 条内容
ANTHROPIC_NEWS_COUNT = int(os.environ.get("ANTHROPIC_NEWS_COUNT", "10"))

# InfoQ AI Development RSS
INFOQ_AI_RSS_URL = os.environ.get(
    "INFOQ_AI_RSS_URL", "https://feed.infoq.com/ai-development/news"
)

# InfoQ AI Development 页面
INFOQ_AI_PAGE_URL = os.environ.get(
    "INFOQ_AI_PAGE_URL", "https://www.infoq.com/ai-development/"
)

# InfoQ 相关 RSS 列表。InfoQ AI Development 单个 news feed 当前条目较少，
# 所以默认聚合 AI Development / Artificial Intelligence / Generative AI。
INFOQ_AI_RSS_URLS = os.environ.get(
    "INFOQ_AI_RSS_URLS",
    "https://feed.infoq.com/ai-development/news,"
    "https://feed.infoq.com/ai-development/articles,"
    "https://feed.infoq.com/artificial_intelligence/news,"
    "https://feed.infoq.com/artificial_intelligence/articles,"
    "https://feed.infoq.com/generative-ai/news,"
    "https://feed.infoq.com/generative-ai/articles",
)

# InfoQ AI Development 获取前 N 条内容
INFOQ_AI_NEWS_COUNT = int(os.environ.get("INFOQ_AI_NEWS_COUNT", "10"))

# 官方 AI 信息源请求最大重试次数
OFFICIAL_AI_MAX_RETRIES = int(os.environ.get("OFFICIAL_AI_MAX_RETRIES", "5"))

# 统一 JSON 输出路径，后续可由后端读取后写入 Redis
OUTPUT_JSON_PATH = os.environ.get("OUTPUT_JSON_PATH", "output/latest.json")

# 按来源归档输出目录。归档结构：
# output/<source>/<YYYY-MM-DD>/<batch>.json
OUTPUT_ARCHIVE_DIR = os.environ.get("OUTPUT_ARCHIVE_DIR", "output")

# =========================================================================
# 每日 AI 播客配置
# =========================================================================

# 是否启用每日播客生成。默认关闭，避免未安装 edge-tts / ffmpeg 的环境启动后报错。
PODCAST_ENABLED = _get_bool_env("PODCAST_ENABLED", False)

# 每天生成播客的时间，24 小时制。播客任务只生成一次前一天内容。
PODCAST_SCHEDULE_TIME = os.environ.get("PODCAST_SCHEDULE_TIME", "02:30")

# 目标内容日期。当前仅支持 yesterday：凌晨生成前一天的完整音频日报。
PODCAST_TARGET_DATE_MODE = os.environ.get("PODCAST_TARGET_DATE_MODE", "yesterday")

# 播客历史 API 返回最近 N 天；前端当前不单独展示最近几期。
PODCAST_HISTORY_DAYS = int(os.environ.get("PODCAST_HISTORY_DAYS", "7"))

# 播客脚本生成使用 OpenRouter，默认复用本项目既有 AI 模型。
PODCAST_SCRIPT_PROVIDER = os.environ.get("PODCAST_SCRIPT_PROVIDER", AI_PROVIDER)
PODCAST_SCRIPT_MODEL = os.environ.get("PODCAST_SCRIPT_MODEL", AI_MODEL)
PODCAST_SCRIPT_MAX_RETRIES = int(os.environ.get("PODCAST_SCRIPT_MAX_RETRIES", "5"))
PODCAST_SCRIPT_RETRY_SECONDS = float(os.environ.get("PODCAST_SCRIPT_RETRY_SECONDS", "5"))

# 播客生成时排除的来源 ID，逗号分隔。只影响播客，不影响普通资讯展示和归档。
PODCAST_EXCLUDED_SOURCE_IDS = os.environ.get(
    "PODCAST_EXCLUDED_SOURCE_IDS", "tldr-ai,infoq"
)

# 第一版 TTS 使用 edge-tts，不依赖 OpenAI API Key。
PODCAST_TTS_PROVIDER = os.environ.get("PODCAST_TTS_PROVIDER", "edge_tts")
PODCAST_VOICE_MALE = os.environ.get("PODCAST_VOICE_MALE", "zh-CN-YunxiNeural")
PODCAST_VOICE_FEMALE = os.environ.get("PODCAST_VOICE_FEMALE", "zh-CN-XiaoxiaoNeural")
PODCAST_VOICE_MALE_RATE = os.environ.get("PODCAST_VOICE_MALE_RATE", "-4%")
PODCAST_VOICE_FEMALE_RATE = os.environ.get("PODCAST_VOICE_FEMALE_RATE", "+0%")
PODCAST_VOICE_MALE_PITCH = os.environ.get("PODCAST_VOICE_MALE_PITCH", "-2Hz")
PODCAST_VOICE_FEMALE_PITCH = os.environ.get("PODCAST_VOICE_FEMALE_PITCH", "+0Hz")
PODCAST_VOICE_MALE_VOLUME = os.environ.get("PODCAST_VOICE_MALE_VOLUME", "+0%")
PODCAST_VOICE_FEMALE_VOLUME = os.environ.get("PODCAST_VOICE_FEMALE_VOLUME", "+0%")
PODCAST_TURN_PAUSE_SECONDS = float(os.environ.get("PODCAST_TURN_PAUSE_SECONDS", "0.8"))
PODCAST_TOPIC_PAUSE_SECONDS = float(os.environ.get("PODCAST_TOPIC_PAUSE_SECONDS", "1.1"))
PODCAST_CHAPTER_PAUSE_SECONDS = float(os.environ.get("PODCAST_CHAPTER_PAUSE_SECONDS", "1.6"))
PODCAST_TTS_MAX_RETRIES = int(os.environ.get("PODCAST_TTS_MAX_RETRIES", "5"))
PODCAST_TTS_RETRY_SECONDS = float(os.environ.get("PODCAST_TTS_RETRY_SECONDS", "3"))
# edge-tts 单段语音合成超时时间，防止网络异常导致 WebSocket 连接挂起不返回、调度线程永久阻塞。
PODCAST_TTS_TIMEOUT_SECONDS = float(os.environ.get("PODCAST_TTS_TIMEOUT_SECONDS", "45"))
# ffprobe / ffmpeg 等本地子进程超时时间，防止本地工具挂起阻塞任务。
PODCAST_SUBPROCESS_TIMEOUT_SECONDS = float(
    os.environ.get("PODCAST_SUBPROCESS_TIMEOUT_SECONDS", "120")
)
# TTS 阶段整体重试：单个片段多次重试仍失败时，等待一段时间后重跑整个 TTS 流程。
# 已合成片段会被复用，重试只补缺失片段。
PODCAST_RUN_MAX_ATTEMPTS = int(os.environ.get("PODCAST_RUN_MAX_ATTEMPTS", "3"))
PODCAST_RUN_RETRY_SECONDS = float(os.environ.get("PODCAST_RUN_RETRY_SECONDS", "300"))
# 播客任务运行超过该时长仍未结束，调度器打 ERROR 告警（无法安全强杀线程，只告警）。
PODCAST_RUN_STALE_WARN_SECONDS = float(
    os.environ.get("PODCAST_RUN_STALE_WARN_SECONDS", "7200")
)

# 控制脚本长度，目标生成 5-8 分钟音频。
PODCAST_MIN_DURATION_MINUTES = int(os.environ.get("PODCAST_MIN_DURATION_MINUTES", "4"))
PODCAST_MAX_DURATION_MINUTES = int(os.environ.get("PODCAST_MAX_DURATION_MINUTES", "8"))
PODCAST_MIN_TURN_COUNT = int(os.environ.get("PODCAST_MIN_TURN_COUNT", "30"))
PODCAST_MIN_SCRIPT_CHARS = int(os.environ.get("PODCAST_MIN_SCRIPT_CHARS", "1600"))

# =========================================================================
# Redis / API 配置
# =========================================================================

# Redis 作为 3 天热数据缓存；磁盘归档是长期事实源。
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_KEY_PREFIX = os.environ.get(
    "REDIS_KEY_PREFIX", "github-trending-spider"
)
REDIS_SNAPSHOT_TTL_SECONDS = int(
    os.environ.get("REDIS_SNAPSHOT_TTL_SECONDS", str(3 * 24 * 60 * 60))
)
REDIS_SOCKET_TIMEOUT_SECONDS = float(
    os.environ.get("REDIS_SOCKET_TIMEOUT_SECONDS", "2")
)

# API 单来源最多返回条数，避免公开只读接口返回过大。
API_MAX_ITEMS_PER_SOURCE = int(os.environ.get("API_MAX_ITEMS_PER_SOURCE", "100"))
API_CORS_ORIGINS = os.environ.get("API_CORS_ORIGINS", "")

# =========================================================================
# 内置采集调度配置
# =========================================================================

# 启动 API 后是否启用进程内定时采集。
SPIDER_SCHEDULER_ENABLED = _get_bool_env("SPIDER_SCHEDULER_ENABLED", True)

# 每天运行时间，24 小时制，逗号分隔。
SPIDER_SCHEDULE_TIMES = os.environ.get(
    "SPIDER_SCHEDULE_TIMES", "07:50,15:50,23:50"
)

# API 启动时是否立即跑一次采集。
SPIDER_RUN_ON_STARTUP = _get_bool_env("SPIDER_RUN_ON_STARTUP", False)

# =========================================================================
# 邮件发送开关
# =========================================================================

# 默认不发送邮件；开启后仅在 EMAIL_SEND_TIMES 指定的调度时间发送。
SEND_EMAIL_ENABLED = _get_bool_env("SEND_EMAIL_ENABLED", False)

# 允许发送邮件的每日调度时间，24 小时制，逗号分隔。
# 采集仍按 SPIDER_SCHEDULE_TIMES 执行；未配置 MAIL_TO_BY_TIME 时用这里控制哪些调度批次发邮件。
EMAIL_SEND_TIMES = os.environ.get("EMAIL_SEND_TIMES", "07:50")
