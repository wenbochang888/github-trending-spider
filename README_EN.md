<h1 align="center">AI Daily Frontier</h1>

<p align="center">
  <em>Multi-source AI news aggregation · Auto-collected daily · AI-powered summaries</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-3572A5" alt="Python" />
  <img src="https://img.shields.io/badge/Vue-3-41b883" alt="Vue 3" />
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688" alt="FastAPI" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License" />
</p>

<p align="center">
  <a href="README.md">中文</a> | English
</p>

---

**AI Daily Frontier** automatically crawls GitHub Trending, Hacker News, TLDR AI, OpenAI, Anthropic, and InfoQ AI Development daily. It generates Chinese summaries with DeepSeek V4 Flash through OpenRouter and serves content through a FastAPI read-only API and Vue frontend news feed.

Live demo: **https://www.gdufe888.top/ai/?lang=en**

## Screenshots

<p align="center">
  <img src="scripts/img/day.png" width="800" alt="Day mode" />
</p>

<p align="center">
  <img src="scripts/img/open.png" width="800" alt="Content view" />
</p>

## Features

- **6 Sources** — GitHub Trending (daily/weekly), Hacker News, TLDR AI, OpenAI, Anthropic, InfoQ AI
- **AI Summaries** — DeepSeek V4 Flash generates Chinese summaries focused on backend engineering
- **Bilingual UI** — Switch via `?lang=en` / `?lang=zh`; English users see original summaries
- **Unified JSON** — All sources output consistent field structure at `output/latest.json`
- **Archival** — Permanent disk archives + Redis 3-day hot cache
- **Fault Tolerant** — Each source fails independently without blocking others
- **Built-in Scheduler** — In-process scheduler, 3 collections per day by default
- **Daily AI Podcast** — Optional audio digest generated from selected sources in the previous day's archive
- **Vue Frontend** — Card-based news feed with skeleton loading and responsive design

## Quick Start

```bash
# Clone & install
git clone https://github.com/wenbochang888/github-trending-spider.git
cd github-trending-spider
pip3 install -r requirements.txt

# Configure (required; never commit a real key)
export AI_API_KEY="your_openrouter_key"

# Test collection
python3 main.py

# Start API server
python3 -m uvicorn api:app --host 0.0.0.0 --port 8000

# Start frontend (dev)
cd frontend && npm install && npm run serve
```

## API

```bash
curl http://localhost:8000/api/health              # Health check
curl http://localhost:8000/api/sources             # Source list
curl http://localhost:8000/api/sources/github-daily/latest  # Single source data
curl http://localhost:8000/api/podcast/latest      # Latest podcast metadata
curl http://localhost:8000/api/podcast/dates/2026-07-18  # Podcast metadata by date
```

## Architecture

```
Collection: main.py → github_trending / hacker_news / tldr_ai / official_ai_sources
Data:       content_items.py → content_store.py → Redis + Disk archive
Service:    api.py (FastAPI) + scheduler.py (scheduled collection)
Frontend:   frontend/ (Vue 3) → Nginx static hosting
```

## Configuration

All config via environment variables with sensible defaults:

| Variable | Default | Description |
| --- | --- | --- |
| `AI_PROVIDER` | openrouter | AI provider; OpenRouter is currently supported |
| `AI_API_URL` | https://openrouter.ai/api/v1 | OpenRouter API base URL |
| `AI_MODEL` | deepseek/deepseek-v4-flash-0731 | Fixed summary model |
| `AI_API_KEY` | - | OpenRouter API key (required; never falls back to a GitHub token) |
| `AI_APP_NAME` | 每日AI前沿信息 | OpenRouter `X-Title` application label |
| `GITHUB_TRENDING_TOP_COUNT` | 10 | Top N repos per GitHub chart |
| `HN_TOP_COUNT` | 10 | Top N HN stories |
| `TLDR_AI_TOP_COUNT` | 10 | Top N TLDR AI items |
| `REDIS_URL` | redis://localhost:6379/0 | Redis connection URL |
| `SPIDER_SCHEDULE_TIMES` | 07:50,15:50,23:50 | Daily collection times |
| `SEND_EMAIL_ENABLED` | false | Enable email sending |
| `PODCAST_ENABLED` | false | Enable daily AI podcast generation |
| `PODCAST_SCHEDULE_TIME` | 02:30 | Daily podcast generation time |
| `PODCAST_TARGET_DATE_MODE` | yesterday | Generate the previous day's podcast |
| `PODCAST_EXCLUDED_SOURCE_IDS` | tldr-ai,infoq | Comma-separated source IDs excluded from podcast generation |
| `PODCAST_SCRIPT_PROVIDER` | openrouter | Podcast script AI provider |
| `PODCAST_SCRIPT_MODEL` | deepseek/deepseek-v4-flash-0731 | Fixed podcast script model |
| `PODCAST_SCRIPT_MAX_RETRIES` | 5 | Max retries for transient podcast script API failures |
| `PODCAST_SCRIPT_RETRY_SECONDS` | 5 | Base retry interval in seconds for podcast script API calls |
| `PODCAST_TTS_PROVIDER` | edge_tts | TTS provider for the first version |
| `PODCAST_VOICE_MALE` | zh-CN-YunxiNeural | Male voice |
| `PODCAST_VOICE_FEMALE` | zh-CN-XiaoxiaoNeural | Female voice |
| `PODCAST_VOICE_MALE_RATE` | -4% | Male voice rate passed to edge-tts |
| `PODCAST_VOICE_FEMALE_RATE` | +0% | Female voice rate passed to edge-tts |
| `PODCAST_VOICE_MALE_PITCH` | -2Hz | Male voice pitch passed to edge-tts |
| `PODCAST_VOICE_FEMALE_PITCH` | +0Hz | Female voice pitch passed to edge-tts |
| `PODCAST_VOICE_MALE_VOLUME` | +0% | Male voice volume passed to edge-tts |
| `PODCAST_VOICE_FEMALE_VOLUME` | +0% | Female voice volume passed to edge-tts |
| `PODCAST_TURN_PAUSE_SECONDS` | 0.8 | Default pause between ordinary dialogue turns |
| `PODCAST_TOPIC_PAUSE_SECONDS` | 1.1 | Default pause for topic transitions within a chapter |
| `PODCAST_CHAPTER_PAUSE_SECONDS` | 1.6 | Default pause when switching chapters |
| `PODCAST_TTS_MAX_RETRIES` | 3 | Max retries for a transient single-segment TTS failure |
| `PODCAST_TTS_RETRY_SECONDS` | 3 | Base retry interval in seconds for single-segment TTS |
| `PODCAST_MIN_DURATION_MINUTES` | 4 | Target minimum podcast duration; shorter audio is logged as a warning |
| `PODCAST_MAX_DURATION_MINUTES` | 8 | Target maximum podcast duration |
| `PODCAST_MIN_TURN_COUNT` | 30 | Minimum turn count for a newly generated script before one retry |
| `PODCAST_MIN_SCRIPT_CHARS` | 1600 | Minimum script text characters before one retry |

Daily podcast generation also requires the system command `ffmpeg` (including `ffprobe`) and the Python package `edge-tts`. Script generation reuses the same `AI_API_KEY` as summaries and does not require a separate model key.

If the script and speech segments already exist, rebuild only the merged audio for a date with:

```bash
python3 scripts/rebuild_podcast_audio.py --date 2026-07-21
```

This command does not call OpenRouter or edge-tts again. It validates every speech segment, recreates silence with the matching audio format, validates the merged duration, and updates metadata only after a successful rebuild.
Podcast environment variables are read when the backend process starts. Restart the backend after changing `PODCAST_ENABLED` or other podcast settings.

> Full configuration options in `config.py`

## Deployment

```bash
# Start backend (background)
bash scripts/start_backend.sh

# Build frontend
cd frontend && npm run build

# Access flow
# https://your-domain.com/ai/     → Nginx serves frontend/dist/
# https://your-domain.com/api/... → Nginx reverse proxy → FastAPI :8000
```

## Friendly Links

<!-- Linux.do digest source is paused while the upstream digest is no longer updated. Original link: https://linux.do -->

## License

[MIT](LICENSE)
