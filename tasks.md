# Tasks: 新增 Hacker News Top 10 + 评论总结功能

- Spec 审批: 2026-05-03
- YOLO Mode: Off

---

## Task 1: 更新 config.py — 新增 HN 配置项 [DONE]
- 涉及文件: `config.py`
- [x] 在文件末尾新增 HN 配置区块
- [x] 新增配置项:
  - `HN_API_BASE = "https://hacker-news.firebaseio.com/v0"`
  - `HN_TOP_COUNT = 10`
  - `HN_COMMENTS_PER_STORY = 10`
  - `HN_MAX_RETRIES = 5`
  - `HN_CONCURRENT_WORKERS = 10`
- 验证: PASSED

---

## Task 2: 抽出 email_sender.py — 邮件发送模块 [DONE]
- 涉及文件: 新建 `email_sender.py`
- [x] 从 `github_trending.py` 提取 `_parse_recipients`, `send_email`, `send_failure_notify`
- [x] `send_email` 新增 `subject` 参数
- 验证: PASSED

---

## Task 3: 抽出 email_builder.py — HTML 邮件生成模块 [DONE]
- 涉及文件: 新建 `email_builder.py`
- [x] 提取 `_escape_html`, 重命名 `_build_github_table`
- [x] 新增 `_build_hn_table` (# | 标题/链接 | 分数 | 评论数 | AI 总结)
- [x] 扩展 `build_email_html(daily_repos, weekly_repos, hn_stories)`
- [x] 并列板块布局 + section-divider + 独立容错
- 验证: PASSED

---

## Task 4: 新建 hacker_news.py — HN 数据获取 + AI 总结 [DONE]
- 涉及文件: 新建 `hacker_news.py`
- [x] `fetch_hn_top_stories` - Firebase API + ThreadPoolExecutor 并发
- [x] `fetch_all_comments` - 每帖 Top 10 顶级评论
- [x] `ai_summarize_hn` - 一次性 AI 总结
- [x] `_html_to_text` - HTML 转纯文本 + 截断
- [x] `_call_hn_ai_api` - 独立 AI 调用（max_tokens=8000）
- 验证: PASSED (实际 API 调用成功获取数据)

---

## Task 5: 重构 github_trending.py — 仅保留 GitHub 爬虫 + AI 总结 [DONE]
- 涉及文件: `github_trending.py`
- [x] 删除 HTML 生成、邮件发送、main 函数
- [x] 保留 fetch_trending, ai_summarize, _call_ai_api
- [x] 清理无用 import
- [x] 日志配置移至 main.py
- 验证: PASSED

---

## Task 6: 新建 main.py — 主入口协调全流程 [DONE]
- 涉及文件: 新建 `main.py`
- [x] 全局日志配置
- [x] GitHub 阶段: 爬取 daily/weekly + AI 总结
- [x] HN 阶段: fetch_hn_top_stories + fetch_all_comments + ai_summarize_hn
- [x] 独立容错: 任一成功即发邮件，全部失败发通知
- [x] 邮件标题: "GitHub + HN 热点报告 - {date}"
- 验证: PASSED

---

## Task 7: 更新 .env.example 和 README.md [DONE]
- [x] `.env.example`: 新增 HN 可选配置注释
- [x] `README.md`: 更新功能说明、文件结构、运行方式、可选配置表
- 验证: PASSED

---

## Task 8: 端到端测试验证 [DONE]
- [x] 所有 6 个模块 import 成功，无循环依赖
- [x] HN API 实际调用成功（获取 3 个帖子 + 8 条评论）
- [x] HTML 生成正确（含 GitHub section + HN section）
- 验证: ALL PASSED

---

## Commit Message 草稿

```
feat: 新增 Hacker News Top 10 热点 + 评论总结功能

- 新增 hacker_news.py: 通过 Firebase API 获取 HN Top Stories 和评论
- 新增 email_builder.py: HTML 邮件模板生成（GitHub + HN 并列板块）
- 新增 email_sender.py: SMTP 邮件发送模块
- 新增 main.py: 主入口，协调 GitHub + HN + AI + 邮件全流程
- 重构 github_trending.py: 仅保留 GitHub 爬虫和 AI 总结
- 更新 config.py: 新增 HN 相关配置项
- 独立容错机制: GitHub 和 HN 任一成功即发邮件
- 使用 ThreadPoolExecutor 并发获取 HN 数据
```
