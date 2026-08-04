# -*- coding: utf-8 -*-
"""
统一信息项模型、AI 摘要和 JSON 输出。
"""

import json
import logging
import os
import re
import time
from datetime import datetime

import requests

from config import (
    AI_API_KEY,
    AI_API_URL,
    AI_APP_NAME,
    AI_MODEL,
    AI_REQUEST_PROXIES,
)

logger = logging.getLogger(__name__)

SOURCE_GITHUB_DAILY = "GitHub Trending Daily"
SOURCE_GITHUB_WEEKLY = "GitHub Trending Weekly"
SOURCE_HACKER_NEWS = "Hacker News"
SOURCE_LINUX_DO = "Linux.do"
SOURCE_V2EX = "V2EX"
SOURCE_TLDR_AI = "TLDR AI"
SOURCE_OPENAI = "OpenAI"
SOURCE_ANTHROPIC = "Anthropic"
SOURCE_INFOQ_AI = "InfoQ AI Development"

CATEGORY_OPEN_SOURCE = "开源趋势"
CATEGORY_COMMUNITY = "社区讨论"
CATEGORY_AI_NEWS = "AI 快讯"
CATEGORY_OFFICIAL_AI = "AI 官方更新"
CATEGORY_AI_ENGINEERING = "AI 工程实践"


def make_content_item(source, category, title, url, published_at="", original_summary="",
                      chinese_summary="", backend_focus="", meta=None):
    """创建统一信息项。"""
    return {
        "source": source or "",
        "category": category or "",
        "title": title or "",
        "url": url or "",
        "published_at": published_at or "",
        "original_summary": original_summary or "",
        "chinese_summary": chinese_summary or "",
        "backend_focus": backend_focus or "",
        "meta": meta if meta is not None else {},
    }


def summarize_content_items(items, section_label):
    """
    为统一信息项生成中文摘要和后端关注点。

    Args:
        items: 统一信息项列表
        section_label: 摘要场景说明

    Returns:
        list[dict]: 增强后的统一信息项
    """
    if not items:
        return items

    if not AI_API_KEY:
        logger.warning("未配置 AI_API_KEY，跳过 %s AI 摘要", section_label)
        for item in items:
            item["chinese_summary"] = "（未配置 AI Token，无法生成中文摘要）{}".format(
                item.get("original_summary", "")
            )
            item["backend_focus"] = "（未配置 AI Token，无法生成后端关注点）"
        return items

    item_lines = []
    for i, item in enumerate(items, 1):
        item_lines.append(
            "{}. 来源: {}\n   分类: {}\n   标题: {}\n   链接: {}\n   发布时间: {}\n   原文摘要: {}".format(
                i,
                item.get("source", ""),
                item.get("category", ""),
                item.get("title", ""),
                item.get("url", ""),
                item.get("published_at", ""),
                item.get("original_summary", ""),
            )
        )

    prompt = (
        "以下是{}的最新内容。请为每条生成：\n"
        "- chinese_summary（60-100 字）：说清楚发生了什么 + 为什么后端工程师应该在意\n"
        "- backend_focus（30-50 字）：对现有后端系统的具体影响或可以立即行动的事\n\n"
        "写作要求：\n"
        "- 区分\"真正重要的更新\"和\"营销包装的旧功能\"，后者直说\"包装大于实质\"\n"
        "- chinese_summary 要让人 5 秒内判断\"要不要点进去看原文\"\n"
        "- backend_focus 越具体越好，最好到 API/SDK/配置级别\n\n"
        "范例：\n"
        '{{\"index\": 1, \"chinese_summary\": \"OpenAI 正式发布 Structured Outputs，API 现在能保证返回严格符合 JSON Schema 的响应。'
        '之前用 function calling 还是会偶尔格式跑偏，这次彻底解决了。\", '
        '\"backend_focus\": \"如果你的服务在调 OpenAI 后还有一层 JSON 解析容错逻辑，现在可以移除。'
        '升级方式：请求体加 response_format 字段即可。\"}}\n\n'
        "请严格按照以下 JSON 格式返回，不要包含任何多余内容：\n"
        '{{"summaries": [{{"index": 1, "chinese_summary": "中文摘要", "backend_focus": "后端行动点"}}, ...]}}\n\n'
        "内容列表：\n{}"
    ).format(section_label, "\n\n".join(item_lines))

    summaries = _call_content_ai_api(prompt)
    if summaries:
        for summary in summaries:
            idx = summary.get("index", 0) - 1
            if 0 <= idx < len(items):
                items[idx]["chinese_summary"] = summary.get("chinese_summary", "")
                items[idx]["backend_focus"] = summary.get("backend_focus", "")

    for item in items:
        if not item.get("chinese_summary"):
            item["chinese_summary"] = "（AI 摘要生成失败）{}".format(
                item.get("original_summary", "")
            )
        if not item.get("backend_focus"):
            item["backend_focus"] = "（AI 后端关注点生成失败）"

    return items


def build_all_content_items(daily_repos, weekly_repos, hn_stories, v2ex_topics, tldr_items, ai_source_items, linux_do_items=None):
    """将多个来源数据适配为统一 JSON 信息项。"""
    items = []
    items.extend(_github_to_items(daily_repos, SOURCE_GITHUB_DAILY, "每日热点"))
    items.extend(_github_to_items(weekly_repos, SOURCE_GITHUB_WEEKLY, "每周热点"))
    items.extend(_hn_to_items(hn_stories))
    # 上游日报停止更新，暂时停用；保留适配器和参数供未来恢复。
    # items.extend(_linux_do_to_items(linux_do_items))
    items.extend(_v2ex_to_items(v2ex_topics))
    items.extend(_tldr_to_items(tldr_items))
    items.extend(ai_source_items or [])
    return items


def write_content_json(items, output_path):
    """写出统一 JSON 文件。"""
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "item_count": len(items),
        "items": items,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("统一 JSON 已写出: %s (%d items)", output_path, len(items))


def _github_to_items(repos, source, category_suffix):
    items = []
    for repo in repos or []:
        summary = repo.get("ai_summary", "")
        original_summary = "{} | 语言: {} | Stars: {:,} | Forks: {:,} | {}".format(
            repo.get("description", ""),
            repo.get("language") or "N/A",
            repo.get("stars", 0),
            repo.get("forks", 0),
            repo.get("stars_period", ""),
        )
        meta = {
            "language": repo.get("language") or "",
            "stars": repo.get("stars", 0),
            "forks": repo.get("forks", 0),
            "stars_period": repo.get("stars_period", ""),
        }
        items.append(make_content_item(
            source=source,
            category="{}-{}".format(CATEGORY_OPEN_SOURCE, category_suffix),
            title=repo.get("full_name", ""),
            url=repo.get("url", ""),
            original_summary=original_summary,
            chinese_summary=summary,
            backend_focus=summary,
            meta=meta,
        ))
    return items


def _hn_to_items(stories):
    items = []
    for story in stories or []:
        hn_url = "https://news.ycombinator.com/item?id={}".format(story.get("id", ""))
        url = story.get("url") or hn_url
        original_summary = "分数: {} | 评论数: {} | 作者: {}".format(
            story.get("score", 0),
            story.get("descendants", 0),
            story.get("by", ""),
        )
        summary = story.get("ai_summary", "")
        meta = {
            "score": story.get("score", 0),
            "comments": story.get("descendants", 0),
            "hn_url": hn_url,
        }
        items.append(make_content_item(
            source=SOURCE_HACKER_NEWS,
            category=CATEGORY_COMMUNITY,
            title=story.get("title", ""),
            url=url,
            published_at=str(story.get("time", "")),
            original_summary=original_summary,
            chinese_summary=summary,
            backend_focus=summary,
            meta=meta,
        ))
    return items


def _linux_do_to_items(linux_do_items):
    items = []
    for item in linux_do_items or []:
        section_title = item.get("section_title", "")
        section_summary = item.get("section_summary", "")
        reply_count = item.get("reply_count", 0)
        original_summary = "分组: {} | 回复数: {} | {}".format(
            section_title,
            reply_count,
            section_summary,
        )
        summary = item.get("ai_summary") or section_summary
        meta = {
            "reply_count": reply_count,
            "section_title": section_title,
            "daily_url": item.get("daily_url", ""),
            "daily_title": item.get("daily_title", ""),
            "daily_headline": item.get("daily_headline", ""),
        }
        items.append(make_content_item(
            source=SOURCE_LINUX_DO,
            category=CATEGORY_COMMUNITY,
            title=item.get("title", ""),
            url=item.get("url", ""),
            published_at=item.get("published_at", ""),
            original_summary=original_summary,
            chinese_summary=summary,
            backend_focus=summary,
            meta=meta,
        ))
    return items


def _v2ex_to_items(topics):
    items = []
    for topic in topics or []:
        url = topic.get("url") or "https://www.v2ex.com/t/{}".format(topic.get("id", ""))
        node_title = topic.get("node", {}).get("title", "")
        member = topic.get("member", {}).get("username", "")
        original_summary = "节点: {} | 作者: {}".format(node_title, member)
        summary = topic.get("ai_summary", "")
        meta = {
            "node": topic.get("node", {}).get("name", ""),
            "node_title": node_title,
            "replies_count": len(topic.get("replies", [])),
            "v2ex_url": url,
        }
        items.append(make_content_item(
            source=SOURCE_V2EX,
            category=CATEGORY_COMMUNITY,
            title=topic.get("title", ""),
            url=url,
            published_at=str(topic.get("created", "")),
            original_summary=original_summary,
            chinese_summary=summary,
            backend_focus=summary,
            meta=meta,
        ))
    return items


def _tldr_to_items(tldr_items):
    items = []
    for item in tldr_items or []:
        summary = item.get("ai_summary") or item.get("summary", "")
        items.append(make_content_item(
            source=SOURCE_TLDR_AI,
            category=item.get("category") or CATEGORY_AI_NEWS,
            title=item.get("title", ""),
            url=item.get("url", ""),
            original_summary=item.get("summary", ""),
            chinese_summary=summary,
            backend_focus=summary,
        ))
    return items


def _call_content_ai_api(prompt, max_retries=10):
    """调用 OpenRouter API 进行统一内容摘要。"""
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
                "content": "你是一个关注 AI 基础设施动态的后端架构师。"
                           "你帮团队判断哪些官方更新会影响现有系统，哪些是营销噪音。"
                           "请始终返回有效 JSON。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 6000,
        "reasoning": {"enabled": False},
        "response_format": {"type": "json_object"},
    }

    for attempt in range(max_retries):
        try:
            logger.info("调用 AI API 进行统一内容摘要 (第 %d 次尝试)...", attempt + 1)
            resp = requests.post(
                "{}/chat/completions".format(AI_API_URL),
                headers=headers,
                json=payload,
                proxies=AI_REQUEST_PROXIES,
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
            logger.error("统一摘要 AI API HTTP 错误 %d: %s", status, e)
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
                logger.warning("统一摘要 AI API 临时失败，等待 %.1f 秒后重试...", wait)
                time.sleep(wait)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error("解析统一摘要 AI 响应失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5)
        except requests.exceptions.RequestException as e:
            logger.error("统一摘要 AI API 调用异常: %s", e)
            if attempt < max_retries - 1:
                time.sleep(10)
        except Exception as e:
            logger.error("统一摘要 AI API 非预期异常: %s", e)
            break

    return []
