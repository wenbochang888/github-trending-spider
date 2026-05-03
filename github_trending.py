#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Trending 爬虫 + AI 总结模块

负责爬取 GitHub Trending 每日/每周热点项目，
调用 AI 生成中文总结。
"""

import json
import logging
import re
import sys
import time

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("请先安装依赖: pip3 install requests beautifulsoup4")
    sys.exit(1)

from config import (
    GITHUB_TOKEN,
    AI_MODEL,
    AI_API_URL,
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
            # 用正则提取 JSON 对象，兼容 ```json ... ``` 和多余空行
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
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
