# 曲美产品部 AI晨报生成器

本项目已内置 `qumei_daily_report.py`，用于把 AI Daily Frontier 的聚合数据整理成面向曲美产品部的中文晨报。它不会写入固定报告文件，默认直接输出到屏幕，方便复制到微信、飞书或自动化消息。

## 一键生成

先正常采集 AI Daily Frontier 数据：

```bash
python main.py
```

再生成曲美产品部晨报：

```bash
python qumei_daily_report.py
```

如果希望生成前自动刷新采集：

```bash
python qumei_daily_report.py --refresh
```

如果需要保存一份 Markdown 预览：

```bash
python qumei_daily_report.py --output output/qumei_daily_report.md
```

`output/` 已被忽略，不会提交到 GitHub。

## 输出内容

晨报固定包含：

- 今日重点：3-5 条，每条都有判断和建议动作。
- 硬件消费和软件动态。
- 大模型动态。
- 开源平台动态。
- 今日建议动作。
- AI Daily Frontier 摘要。
- 数据源说明。

生成逻辑会优先使用本地 `output/latest.json`，并综合 GitHub Trending、Hacker News、TLDR AI、OpenAI、Anthropic、InfoQ、Linux.do、V2EX、Hugging Face、DeepMind 等来源。

## 密钥配置

不要把任何真实密钥提交到 GitHub。

正确做法：

- 本机运行：复制 `.env.example` 为 `.env`，只在 `.env` 里填写真实 token。
- GitHub Actions 或服务器运行：把真实 token 配到 Secrets/环境变量。
- 仓库里只保留 `.env.example` 这种空模板。

常用环境变量：

```bash
export GITHUB_TOKEN=""
export REDIS_URL="redis://localhost:6379/0"
```

如果没有配置 `GITHUB_TOKEN`，主采集程序仍会保留标题、链接和原始摘要；AI 中文摘要会降级，晨报仍可生成。

## 给其他设备使用

在其他设备上：

```bash
git clone https://github.com/wenbochang888/github-trending-spider.git
cd github-trending-spider
pip install -r requirements.txt
cp .env.example .env
python main.py
python qumei_daily_report.py
```

如果不方便配置 token，也可以先直接运行 `python qumei_daily_report.py`，它会读取最近一次生成的 `output/latest.json`；没有缓存时会输出一版带数据源说明的空晨报。
