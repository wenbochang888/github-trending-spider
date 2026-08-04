# -*- coding: utf-8 -*-
"""
Linux.do 技术日报抓取 + AI 总结模块。

只读取 news.linuxe.top 已整理出的日报摘要和原帖索引，不抓取 linux.do 原帖正文或回复。
"""

import json
import logging
import re
import time
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

from config import (
    AI_API_KEY,
    AI_APP_NAME,
    AI_API_URL,
    AI_MODEL,
    LINUX_DO_MAX_ITEMS,
    LINUX_DO_MAX_RETRIES,
    LINUX_DO_NEWS_URL,
)

logger = logging.getLogger(__name__)


def fetch_linux_do_daily_items(count=None, max_retries=None):
    """获取 Linux.do 技术日报中的原帖索引。"""
    if count is None:
        count = LINUX_DO_MAX_ITEMS
    if max_retries is None:
        max_retries = LINUX_DO_MAX_RETRIES

    headers = {
        "User-Agent": "github-trending-spider/1.0 (+https://github.com/wenbochang888/github-trending-spider)",
    }
    for attempt in range(max_retries):
        try:
            logger.info("正在获取 Linux.do 技术日报 (第 %d 次尝试)", attempt + 1)
            resp = requests.get(LINUX_DO_NEWS_URL, headers=headers, timeout=30)
            resp.raise_for_status()
            report = parse_linux_do_daily_html(resp.text, LINUX_DO_NEWS_URL)
            items = report.get("items", [])
            if count and count > 0:
                items = items[:count]
            logger.info("Linux.do 技术日报: 解析到 %d 条原帖", len(items))
            return items
        except requests.RequestException as e:
            logger.warning("获取 Linux.do 技术日报失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))
        except ValueError as e:
            logger.error("解析 Linux.do 技术日报失败: %s", e)
            return []

    logger.error("获取 Linux.do 技术日报失败，已达最大重试次数 %d", max_retries)
    return []


def parse_linux_do_daily_html(html_text, page_url=LINUX_DO_NEWS_URL):
    """解析 news.linuxe.top 首页 HTML。"""
    parser = _LinuxDoDailyParser(page_url)
    parser.feed(html_text or "")
    parser.close()
    report = parser.to_report()
    if not report.get("items"):
        raise ValueError("未解析到 Linux.do 原帖条目")
    return report


def ai_summarize_linux_do_items(items):
    """
    调用 AI 对 Linux.do 日报条目进行二次改写。

    AI 输入只包含 news.linuxe.top 的日报摘要、标题、链接和回复数。
    """
    if not items:
        return items

    if not AI_API_KEY:
        logger.warning("未配置 AI_API_KEY，跳过 Linux.do AI 总结")
        for item in items:
            item["ai_summary"] = _fallback_summary(item)
        return items

    lines = []
    for i, item in enumerate(items, 1):
        lines.append(
            "{}. 分组: {}\n   标题: {}\n   链接: {}\n   回复数: {}\n   日报标题: {}\n   日报摘要: {}".format(
                i,
                item.get("section_title", ""),
                item.get("title", ""),
                item.get("url", ""),
                item.get("reply_count", 0),
                item.get("daily_headline", ""),
                item.get("section_summary", ""),
            )
        )

    prompt = (
        "以下是 news.linuxe.top 已整理出的 Linux.do 技术聚合日报条目。"
        "请只基于这些摘要信息，为每条原帖写中文摘要（60-100 字）。\n\n"
        "要求：\n"
        "- 说清这个讨论为什么值得技术读者点进去看\n"
        "- 不要声称看过原帖正文或回复全文\n"
        "- 对账号风控、模型能力、工程工具、成本策略等话题要直接点出实际影响\n"
        "- 语气像技术日报编辑，不要用营销腔\n\n"
        "请严格按照以下 JSON 格式返回，不要包含任何多余内容：\n"
        '{{"summaries": [{{"index": 1, "summary": "中文摘要"}}, ...]}}\n\n'
        "条目列表：\n{}"
    ).format("\n\n".join(lines))

    try:
        summaries = _call_linux_do_ai_api(prompt)
        if summaries:
            for summary in summaries:
                idx = summary.get("index", 0) - 1
                if 0 <= idx < len(items):
                    items[idx]["ai_summary"] = summary.get("summary", "")
    except Exception as e:
        logger.error("Linux.do AI 总结失败: %s", e)

    for item in items:
        if not item.get("ai_summary"):
            item["ai_summary"] = _fallback_summary(item)
    return items


def _fallback_summary(item):
    section_title = item.get("section_title", "")
    section_summary = item.get("section_summary", "")
    if section_title and section_summary:
        return "{}：{}".format(section_title, section_summary)
    return section_summary or "（AI 总结生成失败）"


def _call_linux_do_ai_api(prompt, max_retries=10):
    """调用 OpenRouter API 进行 Linux.do 摘要。"""
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
                "content": "你是一个关注中文技术社区和 AI 工具链动态的技术日报编辑。"
                           "你只基于用户提供的日报摘要做判断，不补充未提供的事实。"
                           "请始终返回有效 JSON。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 8000,
        "reasoning": {"enabled": False},
        "response_format": {"type": "json_object"},
    }

    for attempt in range(max_retries):
        try:
            logger.info("调用 AI API 进行 Linux.do 总结 (第 %d 次尝试)...", attempt + 1)
            resp = requests.post(
                "{}/chat/completions".format(AI_API_URL),
                headers=headers,
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            return json.loads(content).get("summaries", [])
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            logger.error("Linux.do AI API HTTP 错误 %d: %s", status, e)
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
                logger.warning("Linux.do AI API 临时失败，等待 %.1f 秒后重试...", wait)
                time.sleep(wait)
        except requests.exceptions.RequestException as e:
            logger.error("Linux.do AI 总结调用失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))
        except Exception as e:
            logger.error("Linux.do AI 总结非预期异常: %s", e)
            break

    return None


class _LinuxDoDailyParser(HTMLParser):
    """面向 news.linuxe.top 当前 Next.js HTML 的轻量结构解析器。"""

    def __init__(self, page_url):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.page_url = page_url
        self.title = ""
        self.meta_text = ""
        self.daily_headline = ""
        self.overview = ""
        self.note = ""
        self.highlights = []
        self.sections = []

        self._captures = []
        self._in_highlights = False
        self._current_section = None
        self._in_article_links = False
        self._current_link = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        class_value = attrs_dict.get("class", "")

        if tag == "title":
            self._start_capture("page_title", tag)
        elif _class_has_fragment(class_value, "metaBar"):
            self._start_capture("meta_text", tag)
        elif _class_has_fragment(class_value, "dailyHeadline"):
            self._start_capture("daily_headline", tag)
        elif _class_has_fragment(class_value, "overview"):
            self._start_capture("overview", tag)
        elif _class_has_fragment(class_value, "note"):
            self._start_capture("note", tag)
        elif tag == "ul" and _class_has_fragment(class_value, "highlightList"):
            self._in_highlights = True
        elif self._in_highlights and tag == "li":
            self._start_capture("highlight", tag)
        elif tag == "section" and _class_has_fragment(class_value, "articleSection"):
            self._current_section = {
                "title": "",
                "summary": "",
                "links": [],
            }
        elif self._current_section is not None:
            if tag == "h4" and not self._current_section.get("title"):
                self._start_capture("section_title", tag)
            elif tag == "p" and not self._current_section.get("summary"):
                self._start_capture("section_summary", tag)
            elif tag == "ul" and _class_has_fragment(class_value, "articleLinks"):
                self._in_article_links = True
            elif self._in_article_links and tag == "li":
                self._current_link = {
                    "title": "",
                    "url": "",
                    "reply_count": 0,
                }
            elif self._current_link is not None and tag == "a":
                self._current_link["url"] = _normalize_topic_url(attrs_dict.get("href", ""), self.page_url)
                self._start_capture("link_title", tag)
            elif self._current_link is not None and _class_has_fragment(class_value, "linkMeta"):
                self._start_capture("link_meta", tag)

    def handle_endtag(self, tag):
        while self._captures and self._captures[-1]["end_tag"] == tag:
            capture = self._captures.pop()
            self._finish_capture(capture["name"], _clean_text("".join(capture["parts"])))

        if self._current_link is not None and tag == "li":
            if self._current_link.get("title") and self._current_link.get("url"):
                self._current_section["links"].append(self._current_link)
            self._current_link = None
        elif self._in_article_links and tag == "ul":
            self._in_article_links = False
        elif self._current_section is not None and tag == "section":
            if self._current_section.get("title") or self._current_section.get("links"):
                self.sections.append(self._current_section)
            self._current_section = None
            self._in_article_links = False
        elif self._in_highlights and tag == "ul":
            self._in_highlights = False

    def handle_data(self, data):
        if not data:
            return
        for capture in self._captures:
            capture["parts"].append(data)

    def to_report(self):
        published_at = _extract_chinese_date(self.meta_text)
        items = []
        for section in self.sections:
            section_title = section.get("title", "")
            section_summary = section.get("summary", "")
            for link in section.get("links", []):
                items.append({
                    "title": link.get("title", ""),
                    "url": link.get("url", ""),
                    "reply_count": link.get("reply_count", 0),
                    "section_title": section_title,
                    "section_summary": section_summary,
                    "published_at": published_at,
                    "daily_url": self.page_url,
                    "daily_title": self.title or "linux.do 技术聚合日报",
                    "daily_headline": self.daily_headline,
                    "daily_overview": self.overview,
                })
        return {
            "daily_url": self.page_url,
            "daily_title": self.title or "linux.do 技术聚合日报",
            "published_at": published_at,
            "meta_text": self.meta_text,
            "daily_headline": self.daily_headline,
            "overview": self.overview,
            "note": self.note,
            "highlights": self.highlights,
            "sections": self.sections,
            "items": items,
        }

    def _start_capture(self, name, end_tag):
        self._captures.append({
            "name": name,
            "end_tag": end_tag,
            "parts": [],
        })

    def _finish_capture(self, name, text):
        if not text:
            return
        if name == "page_title":
            self.title = text
        elif name == "meta_text":
            self.meta_text = text
        elif name == "daily_headline":
            self.daily_headline = text
        elif name == "overview":
            self.overview = text
        elif name == "note":
            self.note = text
        elif name == "highlight":
            self.highlights.append(text)
        elif name == "section_title" and self._current_section is not None:
            self._current_section["title"] = re.sub(r"^\d+\s*\.\s*", "", text).strip()
        elif name == "section_summary" and self._current_section is not None:
            self._current_section["summary"] = text
        elif name == "link_title" and self._current_link is not None:
            self._current_link["title"] = text
        elif name == "link_meta" and self._current_link is not None:
            self._current_link["reply_count"] = _extract_reply_count(text)


def _class_has_fragment(class_value, fragment):
    return fragment in (class_value or "")


def _normalize_topic_url(href, page_url):
    href = href or ""
    if href.startswith("/t/"):
        return urljoin("https://linux.do", href)
    return urljoin(page_url, href)


def _clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _extract_reply_count(text):
    match = re.search(r"(\d+)\s*回复", text or "")
    if not match:
        return 0
    return int(match.group(1))


def _extract_chinese_date(text):
    match = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", text or "")
    if not match:
        return ""
    year, month, day = match.groups()
    return "{}-{:02d}-{:02d}".format(int(year), int(month), int(day))
