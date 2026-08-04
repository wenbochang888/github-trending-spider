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
    AI_API_KEY,
    AI_APP_NAME,
    AI_MODEL,
    AI_REQUEST_PROXIES,
    AI_API_URL,
    GITHUB_TRENDING_TOP_COUNT,
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
def fetch_trending(since="daily", max_retries=10, count=None):
    """
    爬取 GitHub Trending 页面，返回仓库列表。

    Args:
        since: "daily" 或 "weekly"
        max_retries: 最大重试次数
        count: 获取前 N 个仓库，默认使用 GITHUB_TRENDING_TOP_COUNT 配置

    Returns:
        list[dict]: 每个 dict 包含 repo_name, owner, url, description,
                    language, stars, forks, stars_period
    """
    if count is None:
        count = GITHUB_TRENDING_TOP_COUNT

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

    # 只保留前 N 个热点仓库；如果页面实际不足 N 个，则返回实际数量
    return repos[:count]


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
# 2. AI 总结（OpenRouter API）
# =========================================================================
def ai_summarize(repos, since_label):
    """
    调用 OpenRouter API 对一批仓库列表进行中文总结。

    Args:
        repos: 仓库列表
        since_label: "每日热点" 或 "每周热点"

    Returns:
        list[dict]: 每个 dict 在原有基础上增加 "ai_summary" 字段
    """
    if not repos:
        return repos

    if not AI_API_KEY:
        logger.warning("未配置 AI_API_KEY，跳过 AI 总结")
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
        "以下是 GitHub {} 的热门开源项目。\n"
        "请为每个项目写一段中文推荐（60-100 字），必须包含：\n"
        "1. 一句话说清这东西解决什么痛点\n"
        "2. 跟同类方案比它牛在哪（性能数字、架构特点、部署优势等）\n"
        "3. 后端工程师能怎么用上\n\n"
        "禁止事项：\n"
        "- 不要用\"该项目旨在\"\"本工具致力于\"\"适合广大开发者\"这类官腔\n"
        "- 不要泛泛说\"高性能\"，要有对比或数据\n"
        "- 不要重复项目描述里已有的信息\n\n"
        "范例：\n"
        '{{\"index\": 1, \"summary\": \"Rust 写的嵌入式向量数据库，单二进制部署，百万级 embedding 检索延迟 <5ms。'
        '比 Milvus 轻量 10 倍，适合不想搞分布式但又需要语义搜索的后端场景。\"}}\n\n'
        "请严格按照以下 JSON 格式返回，不要包含任何多余内容：\n"
        '{{"summaries": [{{"index": 1, "summary": "中文推荐"}}, ...]}}\n\n'
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
    调用 OpenRouter API (OpenAI 兼容格式)。

    Returns:
        list[dict] | None: 解析后的 summaries 列表
    """
    headers = {
        "Authorization": "Bearer {}".format(AI_API_KEY),
        "Content-Type": "application/json",
    }
    if AI_APP_NAME:
        headers["X-Title"] = AI_APP_NAME
    payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一个资深后端工程师，正在给团队同事推荐值得关注的开源项目。"
                           "语气务实、直白，像技术群里聊天。请始终返回有效的 JSON 格式。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4000,
        "reasoning": {"enabled": False},
        "response_format": {"type": "json_object"},
    }

    for attempt in range(max_retries):
        try:
            logger.info("调用 AI API (第 %d 次尝试)...", attempt + 1)
            resp = requests.post(
                "{}/chat/completions".format(AI_API_URL),
                headers=headers,
                json=payload,
                proxies=AI_REQUEST_PROXIES,
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
            logger.error("AI API HTTP 错误 %d: %s", status, e)
            if status == 401:
                logger.error("OpenRouter 鉴权失败，请检查 AI_API_KEY 是否有效")
            elif status == 402:
                logger.error("OpenRouter 余额或 Key 额度不足，请检查账户额度")
            if status not in (408, 429, 500, 502, 503, 504):
                break
            if attempt < max_retries - 1:
                wait = min(60.0, 5.0 * (attempt + 1))
                if status == 429 and e.response is not None:
                    try:
                        wait = min(120.0, max(0.0, float(e.response.headers.get("Retry-After", wait))))
                    except (TypeError, ValueError):
                        pass
                logger.warning("AI API 临时失败，等待 %.1f 秒后重试...", wait)
                time.sleep(wait)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error("解析 AI 响应失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5)
        except requests.exceptions.RequestException as e:
            logger.error("AI API 调用异常: %s", e)
            if attempt < max_retries - 1:
                time.sleep(10)
        except Exception as e:
            logger.error("AI API 非预期异常: %s", e)
            break

    return None
