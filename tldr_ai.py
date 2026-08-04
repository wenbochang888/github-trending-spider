# -*- coding: utf-8 -*-
"""
TLDR AI 数据获取 + 中文整理模块

从 TLDR AI 官方归档页获取最新一期内容，解析条目后调用 AI 生成中文摘要。
"""

import json
import logging
import re
import time
import html as html_lib
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import (
    AI_API_KEY,
    AI_APP_NAME,
    AI_API_URL,
    AI_MODEL,
    TLDR_AI_HOME_URL,
    TLDR_AI_MAX_RETRIES,
    TLDR_AI_TOP_COUNT,
)

logger = logging.getLogger(__name__)

TLDR_AI_LATEST_URL = "https://tldr.tech/api/latest/ai"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

SKIP_LINK_TEXTS = {
    "subscribe",
    "read more",
    "free trial",
    "grab time with the team to get set up",
    "privacy policy",
    "terms of use",
    "report abuse",
    "powered by beehiiv",
    "advertise",
    "careers",
}


def fetch_latest_tldr_ai_issue(count=None, max_retries=None):
    """
    获取 TLDR AI 最新一期的精选条目。

    Args:
        count: 保留前 N 条，默认使用 TLDR_AI_TOP_COUNT 配置
        max_retries: 最大重试次数，默认使用 TLDR_AI_MAX_RETRIES 配置

    Returns:
        list[dict]: 每个 dict 包含 title, url, summary, category, ai_summary
    """
    if count is None:
        count = TLDR_AI_TOP_COUNT
    if max_retries is None:
        max_retries = TLDR_AI_MAX_RETRIES

    home_html = _fetch_html(TLDR_AI_HOME_URL, max_retries)
    if not home_html:
        return []

    issue_url = _extract_latest_issue_url(home_html, TLDR_AI_HOME_URL)
    if not issue_url:
        logger.warning("未能从 TLDR AI 归档页解析最新 issue 链接，尝试官方 latest 入口")
        issue_url = TLDR_AI_LATEST_URL

    logger.info("TLDR AI 最新 issue: %s", issue_url)
    issue_html = _fetch_html(issue_url, max_retries)
    if not issue_html:
        return []

    items = _parse_issue_items(issue_html, issue_url)
    logger.info("TLDR AI issue 解析到 %d 条候选内容", len(items))
    return items[:count]


def _fetch_html(url, max_retries):
    """请求 HTML 页面，失败时按重试策略降级。"""
    for attempt in range(max_retries):
        try:
            logger.info("正在获取 TLDR AI 页面 %s (第 %d 次尝试)", url, attempt + 1)
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.warning("获取 TLDR AI 页面失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))

    logger.error("获取 TLDR AI 页面失败，已达最大重试次数: %s", url)
    return ""


def _extract_latest_issue_url(html, base_url):
    """从 TLDR AI 首页/归档页提取最新一期 issue URL。"""
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a"):
        href = link.get("href", "").strip()
        text = _clean_text(link.get_text(" ", strip=True))
        if not href:
            continue

        absolute_url = urljoin(base_url, href)
        path = urlparse(absolute_url).path
        if "/p/" in path:
            return absolute_url

        if "read more" in text.lower() and _is_tldr_ai_url(absolute_url):
            return absolute_url

    return ""


def _parse_issue_items(html, issue_url):
    """解析 TLDR AI issue 页面中的内容条目。"""
    flight_text = _extract_next_flight_text(html)
    items = _parse_items_from_flight(flight_text, issue_url)
    if items:
        return _dedupe_items(items)

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    container = soup.find("article") or soup.find("main") or soup.body or soup
    items = _parse_items_from_headings(container, issue_url)
    if not items:
        items = _parse_items_from_links(container, issue_url)

    return _dedupe_items(items)


def _extract_next_flight_text(html):
    """提取 Next.js flight 数据中的文本内容。"""
    parts = []

    for match in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", html, re.DOTALL):
        try:
            data = json.loads(match.group(1))
            _collect_json_strings(data, parts)
        except (json.JSONDecodeError, TypeError):
            continue

    return "\n".join(parts)


def _collect_json_strings(value, parts):
    """递归收集 JSON 结构中的字符串。"""
    if isinstance(value, str):
        parts.append(value)
    elif isinstance(value, list):
        for item in value:
            _collect_json_strings(item, parts)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_json_strings(item, parts)


def _parse_items_from_flight(flight_text, issue_url):
    """解析 TLDR 官方 Next.js 页面中的文章数据。"""
    if not flight_text:
        return []

    items = []
    article_pattern = re.compile(
        r'\["\$","article","(?P<url>https?://[^"]+)".*?'
        r'\["\$","h3",null,\{"children":"(?P<title>.*?)"\}\].*?'
        r'"__html":"(?P<summary>.*?)"\}\}',
        re.DOTALL,
    )

    for match in article_pattern.finditer(flight_text):
        url = urljoin(issue_url, html_lib.unescape(match.group("url")))
        title = _clean_text(html_lib.unescape(match.group("title")))
        summary = _clean_html_summary(match.group("summary"))
        category = _find_flight_category(flight_text[:match.start()])

        if _is_valid_item(title, url, summary):
            items.append({
                "title": title,
                "url": url,
                "summary": summary,
                "category": category,
                "ai_summary": "",
            })

    return items


def _find_flight_category(prefix):
    """查找 Next.js flight 文本中最近的分类标题。"""
    matches = re.findall(
        r'className":"text-center font-bold","children":"([^"]*)"',
        prefix,
    )
    for title in reversed(matches):
        title = _clean_text(html_lib.unescape(title))
        if title and not title.lower().startswith("tldr ai"):
            return title
    return ""


def _clean_html_summary(raw_html):
    """清理 HTML 摘要文本。"""
    text = html_lib.unescape(raw_html or "")
    soup = BeautifulSoup(text, "html.parser")
    return _limit_text(_clean_text(soup.get_text(" ", strip=True)), 800)


def _parse_items_from_headings(container, issue_url):
    """优先按 newsletter 语义标题解析内容。"""
    items = []
    current_category = ""

    for tag in container.find_all(["h2", "h3", "h4"]):
        title = _clean_text(tag.get_text(" ", strip=True))
        if not title or _is_noise_title(title):
            continue

        if _looks_like_category(title):
            current_category = title
            continue

        link = tag.find("a")
        url = urljoin(issue_url, link.get("href", "")) if link else ""
        summary = _collect_following_summary(tag)
        if _is_valid_item(title, url, summary):
            items.append({
                "title": title,
                "url": url,
                "summary": summary,
                "category": current_category,
                "ai_summary": "",
            })

    return items


def _parse_items_from_links(container, issue_url):
    """在页面缺少标题语义时，按外链条目做兜底解析。"""
    items = []
    for link in container.find_all("a"):
        title = _clean_text(link.get_text(" ", strip=True))
        href = link.get("href", "").strip()
        url = urljoin(issue_url, href)
        summary = _collect_link_summary(link, title)

        if _is_valid_item(title, url, summary):
            items.append({
                "title": title,
                "url": url,
                "summary": summary,
                "category": _find_previous_category(link),
                "ai_summary": "",
            })

    return items


def _collect_following_summary(tag):
    """收集标题之后、下一个标题之前的摘要文本。"""
    parts = []
    for sibling in tag.find_next_siblings():
        if sibling.name in ["h2", "h3", "h4"]:
            break
        text = _clean_text(sibling.get_text(" ", strip=True))
        if text:
            parts.append(text)
        if len(" ".join(parts)) >= 80:
            break

    return _limit_text(" ".join(parts), 800)


def _collect_link_summary(link, title):
    """从链接所在段落或后续段落中提取摘要。"""
    parent = link.find_parent(["p", "li", "div"])
    if parent:
        text = _clean_text(parent.get_text(" ", strip=True))
        if len(text) > len(title) + 30:
            return _limit_text(text.replace(title, "", 1).strip(), 800)

    parts = []
    for sibling in link.find_next_siblings():
        text = _clean_text(sibling.get_text(" ", strip=True))
        if text:
            parts.append(text)
        if len(" ".join(parts)) >= 80:
            break

    return _limit_text(" ".join(parts), 800)


def _find_previous_category(tag):
    """查找条目前最近的分类标题。"""
    heading = tag.find_previous(["h2", "h3"])
    if not heading:
        return ""

    title = _clean_text(heading.get_text(" ", strip=True))
    return title if _looks_like_category(title) else ""


def _dedupe_items(items):
    """按 URL 和标题去重。"""
    deduped = []
    seen = set()
    for item in items:
        key = item.get("url") or item.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _is_valid_item(title, url, summary):
    """判断候选内容是否像 TLDR AI 正文条目。"""
    combined_text = "{} {}".format(title, summary).lower()
    if "sponsor" in combined_text:
        return False
    if "tldr subscribers" in combined_text:
        return False
    if len(title) < 5 or title.lower() in SKIP_LINK_TEXTS:
        return False
    if not summary or len(summary) < 30:
        return False
    if not url or not urlparse(url).scheme:
        return False
    return not _is_internal_or_noise_url(url)


def _is_internal_or_noise_url(url):
    """过滤 TLDR/Beehiiv 自身导航和邮箱链接。"""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if parsed.scheme in ["mailto", "tel"]:
        return True
    if "beehiiv.com" in host:
        return True
    if "cal.com" in host:
        return True
    if "tldr.tech" in host and "/p/" not in path:
        return True
    if "unsubscribe" in path or "privacy" in path or "terms" in path:
        return True
    return False


def _is_tldr_ai_url(url):
    """判断 URL 是否属于 TLDR AI 站点。"""
    host = urlparse(url).netloc.lower()
    return "ai.tldr.tech" in host or "tldr.tech" in host


def _looks_like_category(text):
    """判断文本是否像 newsletter 分类标题。"""
    if len(text) > 40:
        return False
    normalized = re.sub(r"[^A-Za-z ]", "", text).strip()
    return bool(normalized) and normalized.upper() == normalized


def _is_noise_title(title):
    """过滤页面导航、期刊标题等非内容条目。"""
    lower = title.lower()
    if lower in SKIP_LINK_TEXTS:
        return True
    return lower.startswith("tldr ai ") or lower.startswith("keep up with ai")


def _clean_text(text):
    """清理多余空白。"""
    return re.sub(r"\s+", " ", text or "").strip()


def _limit_text(text, max_len):
    """限制文本长度，避免 prompt 过长。"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def ai_translate_tldr_ai(items):
    """
    调用 AI 将 TLDR AI 英文内容整理成中文。

    Args:
        items: TLDR AI 条目列表

    Returns:
        list[dict]: 每个条目新增 ai_summary 字段
    """
    if not items:
        return items

    if not AI_API_KEY:
        logger.warning("未配置 AI_API_KEY，跳过 TLDR AI 中文整理")
        for item in items:
            item["ai_summary"] = "（未配置 AI Token，无法生成中文整理）{}".format(
                item.get("summary", "")
            )
        return items

    item_lines = []
    for i, item in enumerate(items, 1):
        item_lines.append(
            "{}. 标题: {}\n   分类: {}\n   链接: {}\n   英文摘要: {}".format(
                i,
                item.get("title", ""),
                item.get("category", "") or "N/A",
                item.get("url", ""),
                item.get("summary", ""),
            )
        )

    prompt = (
        "以下是 TLDR AI 最新一期的英文条目。请把每条改写为面向后端工程师的中文快报。\n\n"
        "每条 60-100 字，结构：\n"
        "1. 发生了什么（一句话事实）\n"
        "2. 跟你有什么关系（对后端/AI 工程的实际影响）\n"
        "3. 你明天能试的一件事（具体可操作的行动，没有就省略）\n\n"
        "禁止事项：\n"
        "- 不要逐字翻译英文原文\n"
        "- 不要说\"值得关注\"\"建议持续跟进\"这种正确的废话\n"
        "- 如果影响不大就直说\"了解即可\"\n\n"
        "范例：\n"
        '{{\"index\": 1, \"summary\": \"Google 开源了 Gemma 3 的 4B 参数版本，支持 128K 上下文。'
        '实测在 A10G 单卡上推理速度比 Llama 3 8B 快 40%。'
        '如果你在做 RAG 摘要服务，可以拿它替换 Llama 试试推理成本能降多少。\"}}\n\n'
        "请严格按照以下 JSON 格式返回，不要包含任何多余内容：\n"
        '{{"summaries": [{{"index": 1, "summary": "中文快报"}}, ...]}}\n\n'
        "TLDR AI 条目：\n{}"
    ).format("\n\n".join(item_lines))

    try:
        summaries = _call_tldr_ai_api(prompt)
        if summaries:
            for summary_item in summaries:
                idx = summary_item.get("index", 0) - 1
                if 0 <= idx < len(items):
                    items[idx]["ai_summary"] = summary_item.get("summary", "")
    except Exception as e:
        logger.error("TLDR AI 中文整理失败: %s", e)

    for item in items:
        if "ai_summary" not in item or not item["ai_summary"]:
            item["ai_summary"] = "（AI 中文整理生成失败）{}".format(item.get("summary", ""))

    return items


def _call_tldr_ai_api(prompt, max_retries=10):
    """
    调用 OpenRouter API 进行 TLDR AI 中文整理。

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
                "content": "你是一个 AI 工程团队的技术 leader，每天早上给后端团队做 5 分钟 AI 快报。"
                           "语气简洁有力，关注工程落地而非论文理论。请始终返回有效 JSON。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 5000,
        "reasoning": {"enabled": False},
        "response_format": {"type": "json_object"},
    }

    for attempt in range(max_retries):
        try:
            logger.info("调用 AI API 进行 TLDR AI 中文整理 (第 %d 次尝试)...", attempt + 1)
            resp = requests.post(
                "{}/chat/completions".format(AI_API_URL),
                headers=headers,
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"].strip()
            logger.info("TLDR AI 中文整理响应长度: %d 字符", len(content))
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            parsed = json.loads(content)
            return parsed.get("summaries", [])

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            logger.error("TLDR AI 中文整理 API HTTP 错误 %d: %s", status, e)
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
                logger.warning("TLDR AI API 临时失败，等待 %.1f 秒后重试...", wait)
                time.sleep(wait)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error("解析 TLDR AI 中文整理响应失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5)
        except requests.exceptions.RequestException as e:
            logger.error("TLDR AI 中文整理 API 调用异常: %s", e)
            if attempt < max_retries - 1:
                time.sleep(10)
        except Exception as e:
            logger.error("TLDR AI 中文整理 API 非预期异常: %s", e)
            break

    return None
