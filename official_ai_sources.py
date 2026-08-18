# -*- coding: utf-8 -*-
"""
OpenAI、Anthropic 和 InfoQ AI Development 信息源抓取。
"""

import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import (
    ANTHROPIC_NEWS_COUNT,
    ANTHROPIC_NEWS_URL,
    INFOQ_AI_NEWS_COUNT,
    INFOQ_AI_PAGE_URL,
    INFOQ_AI_RSS_URLS,
    OFFICIAL_AI_MAX_RETRIES,
    OPENAI_NEWS_COUNT,
    OPENAI_NEWS_RSS_URL,
    OPENAI_NEWS_URL,
    SPIDER_REQUEST_PROXIES,
)
from content_items import (
    CATEGORY_AI_ENGINEERING,
    CATEGORY_OFFICIAL_AI,
    SOURCE_ANTHROPIC,
    SOURCE_INFOQ_AI,
    SOURCE_OPENAI,
    make_content_item,
)

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

MONTH_PATTERN = (
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|"
    r"January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4}"
)


def fetch_openai_news(count=None, max_retries=None):
    """抓取 OpenAI News 最近内容。"""
    if count is None:
        count = OPENAI_NEWS_COUNT
    if max_retries is None:
        max_retries = OFFICIAL_AI_MAX_RETRIES

    rss_text = _fetch_text(OPENAI_NEWS_RSS_URL, max_retries)
    if rss_text:
        items = _parse_rss_items(rss_text, SOURCE_OPENAI, CATEGORY_OFFICIAL_AI)
        logger.info("OpenAI News: RSS 解析到 %d 条内容", len(items))
        if items:
            return items[:count]

    html_text = _fetch_text(OPENAI_NEWS_URL, max_retries)
    if not html_text:
        return []
    items = _parse_news_page(html_text, OPENAI_NEWS_URL, SOURCE_OPENAI, CATEGORY_OFFICIAL_AI)
    logger.info("OpenAI News: 解析到 %d 条候选内容", len(items))
    return items[:count]


def fetch_anthropic_news(count=None, max_retries=None):
    """抓取 Anthropic Newsroom 最近内容。"""
    if count is None:
        count = ANTHROPIC_NEWS_COUNT
    if max_retries is None:
        max_retries = OFFICIAL_AI_MAX_RETRIES

    html_text = _fetch_text(ANTHROPIC_NEWS_URL, max_retries)
    if not html_text:
        return []
    items = _parse_news_page(html_text, ANTHROPIC_NEWS_URL, SOURCE_ANTHROPIC, CATEGORY_OFFICIAL_AI)
    logger.info("Anthropic News: 解析到 %d 条候选内容", len(items))
    return items[:count]


def fetch_infoq_ai_development(count=None, max_retries=None):
    """聚合 InfoQ AI Development 及相关 AI 主题 RSS 内容。"""
    if count is None:
        count = INFOQ_AI_NEWS_COUNT
    if max_retries is None:
        max_retries = OFFICIAL_AI_MAX_RETRIES

    items = []
    for rss_url in _split_urls(INFOQ_AI_RSS_URLS):
        rss_text = _fetch_text(rss_url, max_retries)
        if not rss_text:
            continue
        feed_items = _parse_infoq_rss(rss_text, rss_url)
        logger.info("InfoQ feed %s: 解析到 %d 条内容", rss_url, len(feed_items))
        items.extend(feed_items)

    items = _dedupe_items(items)
    logger.info("InfoQ AI Development: 聚合解析到 %d 条内容", len(items))
    return items[:count]


def _fetch_text(url, max_retries):
    """请求文本内容，失败时重试。"""
    for attempt in range(max_retries):
        try:
            logger.info("正在获取官方 AI 信息源 %s (第 %d 次尝试)", url, attempt + 1)
            resp = requests.get(url, headers=HEADERS, timeout=30, proxies=SPIDER_REQUEST_PROXIES)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.warning("获取官方 AI 信息源失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))

    logger.error("获取官方 AI 信息源失败，已达最大重试次数: %s", url)
    return ""


def _extract_content_type(text):
    """从页面文本中提取 OpenAI/Anthropic 文章分类关键词。"""
    match = re.search(r"\b(Product|Announcements|Research|Company|Safety)\b", text)
    return match.group(1) if match else ""


def _parse_news_page(html_text, base_url, source, category):
    """解析官方新闻页链接，适配 OpenAI 和 Anthropic 页面。"""
    soup = BeautifulSoup(html_text, "html.parser")
    items = []
    seen = set()

    for link in soup.find_all("a"):
        href = link.get("href", "").strip()
        url = urljoin(base_url, href)
        if not _is_news_article_url(url, base_url):
            continue

        text = _clean_text(link.get_text(" ", strip=True))
        parent_text = _clean_text(link.find_parent().get_text(" ", strip=True)) if link.find_parent() else text
        title = _extract_title(text, parent_text)
        if not title or title in seen:
            continue

        seen.add(title)
        summary = _extract_summary(parent_text, title)
        content_type = _extract_content_type(parent_text)
        meta = {"content_type": content_type} if content_type else {}
        items.append(make_content_item(
            source=source,
            category=category,
            title=title,
            url=url,
            published_at=_extract_date(parent_text),
            original_summary=summary,
            meta=meta,
        ))

    return items


def _parse_infoq_rss(rss_text, rss_url):
    """解析 InfoQ RSS item。"""
    default_category = _infoq_category_from_url(rss_url)
    return _parse_rss_items(rss_text, SOURCE_INFOQ_AI, default_category)


def _parse_rss_items(rss_text, source, default_category):
    """解析 RSS item。"""
    try:
        root = ET.fromstring(rss_text)
    except ET.ParseError as e:
        logger.error("解析 RSS 失败: %s", e)
        return []

    items = []
    for node in root.findall(".//item"):
        title = _clean_text(_node_text(node, "title"))
        link = _clean_text(_node_text(node, "link"))
        pub_date = _clean_text(_node_text(node, "pubDate"))
        description = _clean_html(_node_text(node, "description"))
        rss_category = _clean_text(_node_text(node, "category"))
        source_category = rss_category or default_category
        # 若 RSS category 恰好是内容分类关键词（如 Safety / Research），存入 meta
        content_type = rss_category if rss_category in (
            "Product", "Announcements", "Research", "Company", "Safety"
        ) else ""
        meta = {"content_type": content_type} if content_type else {}
        if title and link:
            items.append(make_content_item(
                source=source,
                category=source_category,
                title=title,
                url=link,
                published_at=pub_date,
                original_summary=description,
                meta=meta,
            ))
    return items


def _node_text(node, child_name):
    child = node.find(child_name)
    return child.text if child is not None and child.text else ""


def _split_urls(urls_text):
    """解析逗号分隔 URL。"""
    return [url.strip() for url in urls_text.split(",") if url.strip()]


def _dedupe_items(items):
    """按 URL 和标题去重。"""
    deduped = []
    seen = set()
    for item in items:
        key = item.get("url") or item.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        if not item.get("original_summary"):
            item["original_summary"] = "来自 InfoQ 页面: {}".format(INFOQ_AI_PAGE_URL)
        deduped.append(item)
    return deduped


def _infoq_category_from_url(url):
    if "artificial_intelligence" in url:
        return "InfoQ Artificial Intelligence"
    if "generative-ai" in url:
        return "InfoQ Generative AI"
    return CATEGORY_AI_ENGINEERING


def _is_news_article_url(url, base_url):
    parsed = urlparse(url)
    base = urlparse(base_url)
    if parsed.netloc and parsed.netloc != base.netloc:
        return False

    path = parsed.path.rstrip("/")
    base_path = base.path.rstrip("/")
    if not path or path == base_path:
        return False

    if "openai.com" in base.netloc:
        return path.startswith("/news/")
    if "anthropic.com" in base.netloc:
        return path.startswith("/news/")
    return False


def _extract_title(text, parent_text):
    title = text or parent_text
    category_date_match = re.search(
        r"\s+(Product|Announcements|Research|Company|Safety)\s+" + MONTH_PATTERN,
        title,
    )
    if category_date_match:
        title = title[:category_date_match.start()].strip()
    title = re.sub(MONTH_PATTERN, "", title).strip()
    title = re.sub(r"^(Product|Announcements|Research|Company|Safety)\s+", "", title).strip()
    title = re.sub(r"\s+", " ", title)
    if len(title) > 160:
        title = title[:160].strip()
    if len(title) < 8:
        return ""
    if title.lower() in {"news", "research", "product", "announcements"}:
        return ""
    return title


def _extract_date(text):
    match = re.search(MONTH_PATTERN, text)
    return match.group(0) if match else ""


def _extract_summary(parent_text, title):
    summary = parent_text.replace(title, "", 1).strip()
    summary = re.sub(MONTH_PATTERN, "", summary).strip()
    summary = re.sub(r"^(Product|Announcements|Research|Company|Safety)\s+", "", summary).strip()
    return _limit_text(summary or title, 500)


def _clean_html(raw_html):
    text = html.unescape(raw_html or "")
    soup = BeautifulSoup(text, "html.parser")
    return _limit_text(_clean_text(soup.get_text(" ", strip=True)), 800)


def _clean_text(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def _limit_text(text, max_len):
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."
