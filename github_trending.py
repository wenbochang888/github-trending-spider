#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Trending 每日/每周热点爬取 + AI总结 + 邮件推送

功能：
1. 爬取 GitHub Trending 每日/每周热点项目
2. 通过 GitHub Models API (GPT-4o-mini) 进行中文总结
3. 生成 HTML 表格邮件发送到指定邮箱

依赖：requests, beautifulsoup4
Python >= 3.6
"""

import json
import logging
import smtplib
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header


try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("请先安装依赖: pip3 install requests beautifulsoup4")
    sys.exit(1)

from config import (
    GITHUB_TOKEN,
    SMTP_SERVER,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    MAIL_TO,
    MAIL_FROM,
    AI_MODEL,
    AI_API_URL,
    LOG_FILE,
)

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
TRENDING_URL = "https://github.com/trending"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# =========================================================================
# 1. 爬取 GitHub Trending
# =========================================================================
def fetch_trending(since="daily", max_retries=10):
    """
    爬取 GitHub Trending 页面，返回仓库列表。

    Args:
        since: "daily" 或 "weekly"
        max_retries: 最大重试次数

    Returns:
        list[dict]: 每个 dict 包含 repo_name, owner, url, description,
                    language, stars, forks, stars_period
    """
    url = "{}?since={}".format(TRENDING_URL, since)
    repos = []

    for attempt in range(max_retries):
        try:
            logger.info("正在爬取 %s (第 %d 次尝试)", url, attempt + 1)
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            logger.warning("请求失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))
            else:
                logger.error("爬取 %s 失败，已达最大重试次数", url)
                return repos

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = soup.select("article.Box-row")
    logger.info("从 %s 页面解析到 %d 个仓库", since, len(articles))

    for article in articles:
        repo = _parse_article(article, since)
        if repo:
            repos.append(repo)

    # 只保留前 5 个热点仓库
    return repos[:5]




def _parse_article(article, since):
    """解析单个 <article class='Box-row'> 元素。"""
    try:
        # 仓库名 (owner/repo)
        h2 = article.select_one("h2 a")
        if not h2:
            return None
        full_name = h2.get_text(strip=True).replace("\n", "").replace(" ", "")
        # full_name 格式: "owner/repo"
        parts = full_name.split("/")
        owner = parts[0].strip() if len(parts) >= 2 else ""
        repo_name = parts[1].strip() if len(parts) >= 2 else full_name.strip()
        repo_url = "https://github.com" + h2.get("href", "").strip()

        # 描述
        desc_tag = article.select_one("p.col-9")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # 编程语言
        lang_tag = article.select_one("[itemprop='programmingLanguage']")
        language = lang_tag.get_text(strip=True) if lang_tag else ""

        # Stars 总数
        star_link = article.select_one("a[href$='/stargazers']")
        stars = _parse_number(star_link.get_text(strip=True)) if star_link else 0

        # Forks 总数
        fork_link = article.select_one("a[href$='/forks']")
        forks = _parse_number(fork_link.get_text(strip=True)) if fork_link else 0

        # 本期新增 stars
        period_tag = article.select_one("span.d-inline-block.float-sm-right")
        stars_period = ""
        if period_tag:
            stars_period = period_tag.get_text(strip=True)

        return {
            "owner": owner,
            "repo_name": repo_name,
            "full_name": "{}/{}".format(owner, repo_name),
            "url": repo_url,
            "description": description,
            "language": language,
            "stars": stars,
            "forks": forks,
            "stars_period": stars_period,
            "since": since,
        }
    except Exception as e:
        logger.warning("解析 article 失败: %s", e)
        return None


def _parse_number(text):
    """将 '121,933' 这类字符串转为整数。"""
    try:
        return int(text.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0


# =========================================================================
# 2. AI 总结（GitHub Models API）
# =========================================================================
def ai_summarize(repos, since_label):
    """
    调用 GitHub Models API 对一批仓库列表进行中文总结。

    Args:
        repos: 仓库列表
        since_label: "每日热点" 或 "每周热点"

    Returns:
        list[dict]: 每个 dict 在原有基础上增加 "ai_summary" 字段
    """
    if not repos:
        return repos

    if not GITHUB_TOKEN:
        logger.warning("未配置 GITHUB_TOKEN，跳过 AI 总结")
        for r in repos:
            r["ai_summary"] = "（未配置 AI Token，无法生成总结）"
        return repos

    # 将所有仓库信息一次性发给 AI，减少 API 调用次数
    repo_text_lines = []
    for i, r in enumerate(repos, 1):
        repo_text_lines.append(
            "{}. {} [{}] - Stars: {:,} | Forks: {:,} | 语言: {} | {}\n   描述: {}".format(
                i,
                r["full_name"],
                r["url"],
                r["stars"],
                r["forks"],
                r["language"] or "N/A",
                r["stars_period"],
                r["description"] or "无描述",
            )
        )
    repos_text = "\n".join(repo_text_lines)

    prompt = (
        "你是一个技术专家。以下是 GitHub {} 的热门开源项目列表。\n"
        "请为每个项目提供一段简短的中文总结（2-3句话），说明：\n"
        "1. 这个项目是做什么的\n"
        "2. 它的主要特点或亮点\n"
        "3. 适合哪些开发者或使用场景\n\n"
        "请严格按照以下 JSON 格式返回，不要包含任何多余内容：\n"
        '{{"summaries": [{{"index": 1, "summary": "中文总结"}}, ...]}}\n\n'
        "项目列表：\n{}"
    ).format(since_label, repos_text)

    try:
        summaries = _call_ai_api(prompt)
        if summaries:
            for item in summaries:
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(repos):
                    repos[idx]["ai_summary"] = item.get("summary", "")
    except Exception as e:
        logger.error("AI 总结失败: %s", e)

    # 确保每个 repo 都有 ai_summary 字段
    for r in repos:
        if "ai_summary" not in r:
            r["ai_summary"] = "（AI 总结生成失败）"

    return repos


def _call_ai_api(prompt, max_retries=10):
    """
    调用 GitHub Models API (OpenAI 兼容格式)。

    Returns:
        list[dict] | None: 解析后的 summaries 列表
    """
    headers = {
        "Authorization": "Bearer {}".format(GITHUB_TOKEN),
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一个专业的技术分析助手，擅长用简洁的中文总结开源项目。"
                           "请始终返回有效的 JSON 格式。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4000,
    }

    for attempt in range(max_retries):
        try:
            logger.info("调用 AI API (第 %d 次尝试)...", attempt + 1)
            resp = requests.post(
                "{}/chat/completions".format(AI_API_URL),
                headers=headers,
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"]
            logger.info("AI 响应长度: %d 字符", len(content))

            # 尝试解析 JSON（处理可能的 markdown 代码块包裹）
            content = content.strip()
            if content.startswith("```"):
                # 移除 ```json ... ``` 包裹
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])
            parsed = json.loads(content)
            return parsed.get("summaries", [])

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status == 429:
                wait = 60 * (attempt + 1)
                logger.warning("API 限流，等待 %d 秒后重试...", wait)
                time.sleep(wait)
            else:
                logger.error("AI API HTTP 错误 %d: %s", status, e)
                if attempt < max_retries - 1:
                    time.sleep(10)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error("解析 AI 响应失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5)
        except Exception as e:
            logger.error("AI API 调用异常: %s", e)
            if attempt < max_retries - 1:
                time.sleep(10)

    return None


# =========================================================================
# 3. 生成 HTML 邮件
# =========================================================================
def build_email_html(daily_repos, weekly_repos):
    """
    将每日和每周热点构建成 HTML 邮件内容。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    html_parts = [
        "<!DOCTYPE html>",
        '<html><head><meta charset="utf-8">',
        "<style>",
        "  body { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; "
        "         color: #24292e; padding: 20px; max-width: 1000px; margin: 0 auto; }",
        "  h1 { color: #0366d6; border-bottom: 2px solid #e1e4e8; padding-bottom: 10px; }",
        "  h2 { color: #24292e; margin-top: 30px; }",
        "  table { border-collapse: collapse; width: 100%; margin: 15px 0; }",
        "  th { background-color: #0366d6; color: white; padding: 10px 12px; "
        "       text-align: left; font-size: 13px; }",
        "  td { padding: 10px 12px; border-bottom: 1px solid #e1e4e8; "
        "       font-size: 13px; vertical-align: top; }",
        "  tr:nth-child(even) { background-color: #f6f8fa; }",
        "  tr:hover { background-color: #f0f4f8; }",
        "  a { color: #0366d6; text-decoration: none; }",
        "  a:hover { text-decoration: underline; }",
        "  .lang { display: inline-block; padding: 2px 8px; border-radius: 12px; "
        "          background: #eff3f6; font-size: 12px; }",
        "  .stars { color: #e3b341; font-weight: bold; }",
        "  .period { color: #22863a; font-size: 12px; }",
        "  .summary { color: #586069; line-height: 1.5; }",
        "  .footer { margin-top: 30px; padding-top: 15px; border-top: 1px solid #e1e4e8; "
        "            color: #6a737d; font-size: 12px; }",
        "</style>",
        "</head><body>",
        "<h1>🔥 GitHub Trending 热点报告 - {}</h1>".format(today),
    ]

    if daily_repos:
        html_parts.append("<h2>📅 每日热点 (Daily)</h2>")
        html_parts.append(_build_table(daily_repos))

    if weekly_repos:
        html_parts.append("<h2>📆 每周热点 (Weekly)</h2>")
        html_parts.append(_build_table(weekly_repos))

    if not daily_repos and not weekly_repos:
        html_parts.append("<p>今日未能获取到热点数据，请检查网络或日志。</p>")

    html_parts.extend([
        '<div class="footer">',
        "<p>此邮件由 GitHub Trending Spider 自动生成并发送。</p>",
        "<p>数据来源：<a href='https://github.com/trending'>GitHub Trending</a> "
        "| AI 总结：GitHub Models ({}) </p>".format(AI_MODEL),
        "</div>",
        "</body></html>",
    ])

    return "\n".join(html_parts)


def _build_table(repos):
    """构建单个表格的 HTML。"""
    rows = [
        "<table>",
        "<tr>"
        "<th>#</th>"
        "<th>项目</th>"
        "<th>⭐ Stars</th>"
        "<th>📝 AI 总结</th>"
        "</tr>",
    ]

    for i, r in enumerate(repos, 1):
        rows.append(
            "<tr>"
            "<td>{}</td>"
            '<td><a href="{}">{}</a></td>'
            '<td class="stars">{:,}</td>'
            '<td class="summary">{}</td>'
            "</tr>".format(
                i,
                r["url"],
                r["full_name"],
                r["stars"],
                _escape_html(r.get("ai_summary", "")),
            )
        )

    rows.append("</table>")
    return "\n".join(rows)


def _escape_html(text):
    """简单的 HTML 转义。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# =========================================================================
# 4. 发送邮件
# =========================================================================
def send_email(html_content):
    """通过 SMTP 发送 HTML 邮件。"""
    today = datetime.now().strftime("%Y-%m-%d")
    subject = "GitHub Trending 热点报告 - {}".format(today)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = MAIL_FROM
    msg["To"] = MAIL_TO
    text_part = MIMEText("请使用支持 HTML 的邮件客户端查看此邮件。", "plain", "utf-8")
    html_part = MIMEText(html_content, "html", "utf-8")
    msg.attach(text_part)
    msg.attach(html_part)


    try:
        logger.info("正在连接 SMTP 服务器 %s:%d ...", SMTP_SERVER, SMTP_PORT)
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(MAIL_FROM, [MAIL_TO], msg.as_string())
        logger.info("邮件发送成功！收件人: %s", MAIL_TO)
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP 认证失败，请检查邮箱账号和授权码")
    except smtplib.SMTPException as e:
        logger.error("SMTP 错误: %s", e)
    except Exception as e:
        logger.error("邮件发送异常: %s", e)

    return False


# =========================================================================
# 5. 主流程
# =========================================================================
def send_failure_notify(error_msg):
    """当主流程失败时，发送一封简单的失败通知邮件。"""
    try:
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = MIMEText(
            "GitHub Trending Spider 运行失败\n\n"
            "时间: {}\n"
            "错误: {}\n\n"
            "请检查服务器日志: /root/logs/github-python/trending.log".format(today, error_msg),
            "plain", "utf-8"
        )
        msg["Subject"] = Header("[FAIL] GitHub Trending Spider - {}".format(today), "utf-8")
        msg["From"] = MAIL_FROM
        msg["To"] = MAIL_TO



        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(MAIL_FROM, [MAIL_TO], msg.as_string())
        logger.info("失败通知邮件已发送")
    except Exception as e:
        logger.error("发送失败通知邮件也失败了: %s", e)


def main():
    logger.info("=" * 60)
    logger.info("GitHub Trending Spider 启动 - %s", datetime.now().isoformat())
    logger.info("=" * 60)

    errors = []
    # 爬取每日热点
    logger.info("--- 开始爬取每日热点 ---")
    daily_repos = fetch_trending(since="daily")
    logger.info("每日热点: 获取到 %d 个仓库", len(daily_repos))
    if not daily_repos:
        errors.append("爬取每日热点失败")

    time.sleep(3)
    # 爬取每周热点
    logger.info("--- 开始爬取每周热点 ---")
    weekly_repos = fetch_trending(since="weekly")
    logger.info("每周热点: 获取到 %d 个仓库", len(weekly_repos))
    if not weekly_repos:
        errors.append("爬取每周热点失败")
    if not daily_repos and not weekly_repos:
        logger.error("未获取到任何数据")
        send_failure_notify("爬取每日和每周热点均失败（已重试 10 次）")
        sys.exit(1)

    # AI 总结
    logger.info("--- 开始 AI 总结 ---")
    daily_repos = ai_summarize(daily_repos, "每日热点")
    time.sleep(5)
    weekly_repos = ai_summarize(weekly_repos, "每周热点")
    logger.info("--- 生成邮件内容 ---")
    html = build_email_html(daily_repos, weekly_repos)
    # 发送邮件
    logger.info("--- 发送邮件 ---")
    success = send_email(html)
    if success:
        logger.info("✅ 全部完成！")
    else:
        logger.error("❌ 邮件发送失败")
        send_failure_notify("邮件发送失败")
        sys.exit(1)


if __name__ == "__main__":
    main()