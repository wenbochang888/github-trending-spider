# -*- coding: utf-8 -*-
"""
Hacker News 数据获取 + AI 总结模块

通过 HN 官方 Firebase API 获取 Top Stories 和评论，
调用 AI 生成中文总结。
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from config import (
    AI_API_KEY,
    AI_APP_NAME,
    AI_API_URL,
    AI_MODEL,
    AI_REQUEST_PROXIES,
    HN_API_BASE,
    HN_COMMENTS_PER_STORY,
    HN_CONCURRENT_WORKERS,
    HN_MAX_RETRIES,
    HN_TOP_COUNT,
    SPIDER_REQUEST_PROXIES,
)

logger = logging.getLogger(__name__)

HN_AI_SUMMARY_FAILED_TEXT = "（AI 总结生成失败）"


# =========================================================================
# 1. 数据获取
# =========================================================================
def fetch_hn_top_stories(count=None, max_retries=None):
    """
    获取 Hacker News 热门帖子列表。

    Args:
        count: 获取前 N 个帖子，默认使用 HN_TOP_COUNT 配置
        max_retries: 最大重试次数，默认使用 HN_MAX_RETRIES 配置

    Returns:
        list[dict]: 帖子详情列表，每个 dict 含
            id, title, url, score, by, time, descendants, kids
    """
    if count is None:
        count = HN_TOP_COUNT
    if max_retries is None:
        max_retries = HN_MAX_RETRIES

    # 获取 Top Stories ID 列表
    top_ids = _fetch_top_story_ids(max_retries)
    if not top_ids:
        return []

    top_ids = top_ids[:count]
    logger.info("获取到 %d 个 HN Top Story ID，开始获取详情...", len(top_ids))

    # 并发获取每个帖子的详情
    stories = _fetch_items_concurrent(top_ids)

    # 过滤无效帖子（deleted/dead/非 story 类型）
    valid_stories = []
    for s in stories:
        if s and s.get("type") == "story" and not s.get("deleted") and not s.get("dead"):
            valid_stories.append(s)

    logger.info("HN Top Stories: 有效帖子 %d 个", len(valid_stories))
    return valid_stories[:count]


def fetch_all_comments(stories, comments_per_story=None):
    """
    为每个帖子获取顶级评论。

    Args:
        stories: 帖子列表
        comments_per_story: 每帖获取评论数，默认使用 HN_COMMENTS_PER_STORY 配置

    Returns:
        list[dict]: 增强后的帖子列表（每个帖子新增 "comments" 字段）
    """
    if comments_per_story is None:
        comments_per_story = HN_COMMENTS_PER_STORY

    for story in stories:
        kids = story.get("kids", [])
        if not kids:
            story["comments"] = []
            continue

        comment_ids = kids[:comments_per_story]
        comments_raw = _fetch_items_concurrent(comment_ids)

        # 过滤并转换评论
        comments = []
        for c in comments_raw:
            if c and not c.get("deleted") and not c.get("dead") and c.get("text"):
                comments.append({
                    "id": c.get("id"),
                    "by": c.get("by", "anonymous"),
                    "text": _html_to_text(c["text"]),
                })
        story["comments"] = comments

    total_comments = sum(len(s.get("comments", [])) for s in stories)
    logger.info("HN 评论获取完成: 共 %d 条评论", total_comments)
    return stories


def _fetch_top_story_ids(max_retries):
    """获取 Top Stories 的 ID 列表。"""
    url = "{}/topstories.json".format(HN_API_BASE)

    for attempt in range(max_retries):
        try:
            logger.info("正在获取 HN Top Stories (第 %d 次尝试)", attempt + 1)
            resp = requests.get(url, timeout=30, proxies=SPIDER_REQUEST_PROXIES)
            resp.raise_for_status()
            ids = resp.json()
            if isinstance(ids, list):
                return ids
            logger.warning("HN API 返回非列表数据: %s", type(ids))
        except requests.RequestException as e:
            logger.warning("获取 HN Top Stories 失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))

    logger.error("获取 HN Top Stories 失败，已达最大重试次数 %d", max_retries)
    return []


def _fetch_item(item_id):
    """获取单个 HN item（story 或 comment）。"""
    url = "{}/item/{}.json".format(HN_API_BASE, item_id)
    try:
        resp = requests.get(url, timeout=15, proxies=SPIDER_REQUEST_PROXIES)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.debug("获取 HN item %s 失败: %s", item_id, e)
        return None


def _fetch_items_concurrent(item_ids):
    """并发获取多个 HN item。"""
    results = [None] * len(item_ids)

    with ThreadPoolExecutor(max_workers=HN_CONCURRENT_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_fetch_item, item_id): idx
            for idx, item_id in enumerate(item_ids)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logger.debug("并发获取 item 异常: %s", e)

    return results


# =========================================================================
# 2. 文本处理
# =========================================================================
def _html_to_text(html_str):
    """
    将 HN 评论中的 HTML 转为纯文本。

    Args:
        html_str: HTML 格式的评论内容

    Returns:
        str: 纯文本，超过 500 字符会截断
    """
    if not html_str:
        return ""

    soup = BeautifulSoup(html_str, "html.parser")

    # 将 <p> 和 <br> 转为换行
    for tag in soup.find_all("p"):
        tag.insert_before("\n")
    for tag in soup.find_all("br"):
        tag.replace_with("\n")

    text = soup.get_text()
    # 清理多余空白
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # 截断超长评论
    max_len = 800
    if len(text) > max_len:
        text = text[:max_len] + "..."

    return text


# =========================================================================
# 3. AI 总结
# =========================================================================
def ai_summarize_hn(stories):
    """
    调用 AI 对 HN 帖子和评论进行中文总结。

    Args:
        stories: 帖子列表（已含 comments 字段）

    Returns:
        list[dict]: 每个帖子新增 "ai_summary" 字段
    """
    if not stories:
        return stories

    if not AI_API_KEY:
        logger.warning("未配置 AI_API_KEY，跳过 HN AI 总结")
        for s in stories:
            s["ai_summary"] = "（未配置 AI Token，无法生成总结）"
        return stories

    try:
        summaries = _call_hn_ai_api(_build_hn_summary_prompt(stories))
        missing_indexes = _apply_hn_summaries(stories, summaries)
        if summaries is not None and missing_indexes:
            _log_missing_hn_summaries(stories, missing_indexes, "首次")
            retry_prompt = _build_hn_retry_prompt(stories, missing_indexes)
            retry_summaries = _call_hn_ai_api(retry_prompt, max_retries=3)
            missing_indexes = _apply_hn_summaries(stories, retry_summaries)
            if missing_indexes:
                _log_missing_hn_summaries(stories, missing_indexes, "补偿")
    except Exception as e:
        logger.error("HN AI 总结失败: %s", e)

    # 确保每个 story 都有 ai_summary 字段
    for s in stories:
        if not s.get("ai_summary"):
            s["ai_summary"] = HN_AI_SUMMARY_FAILED_TEXT

    return stories


def _format_hn_story_for_prompt(story, index):
    """格式化单个 HN 帖子及评论，供 AI prompt 使用。"""
    line = "{}. {} [{}]\n   分数: {} | 评论数: {} | 作者: {}".format(
        index,
        story.get("title", ""),
        story.get("url", "https://news.ycombinator.com/item?id={}".format(story.get("id", ""))),
        story.get("score", 0),
        story.get("descendants", 0),
        story.get("by", ""),
    )

    comments = story.get("comments", [])
    if comments:
        line += "\n   热门评论（按社区热度排序，排在前面的是最受认可的观点）:"
        for comment_index, comment in enumerate(comments, 1):
            comment_text = comment.get("text", "")
            if comment_text:
                if len(comment_text) > 300:
                    comment_text = comment_text[:300] + "..."
                line += "\n     热评{} [{}]: {}".format(
                    comment_index,
                    comment.get("by", "?"),
                    comment_text,
                )

    return line


def _build_hn_summary_prompt(stories):
    """构建 HN 全量摘要 prompt。"""
    stories_text = "\n\n".join(
        _format_hn_story_for_prompt(story, index)
        for index, story in enumerate(stories, 1)
    )
    return _build_hn_prompt(
        "以下是 Hacker News 今日 Top {} 热门帖子及其热门评论。".format(len(stories)),
        stories_text,
    )


def _build_hn_retry_prompt(stories, missing_indexes):
    """构建 HN 摘要缺失条目的补偿 prompt。"""
    stories_text = "\n\n".join(
        _format_hn_story_for_prompt(stories[index], index + 1)
        for index in missing_indexes
    )
    return _build_hn_prompt(
        "以下是 Hacker News 摘要中遗漏的帖子。请只补充这些原始 index 的摘要。",
        stories_text,
    )


def _build_hn_prompt(intro, stories_text):
    """构建 HN 摘要 prompt。"""
    return (
        "{}\n"
        "评论已按社区投票排序，排在前面的观点最受认可。\n\n"
        "请为每个帖子写中文总结（100-150 字），结构如下：\n"
        "1.【主题】一句话说清这个帖子在讨论什么（15 字以内）\n"
        "2.【社区精华】挑 2-3 条最有料的评论，每条独占一行，格式：\n"
        "   用户 xxx：具体观点\n"
        "   用户 yyy：具体观点\n"
        "3.【争议/亮点】如果社区有明显分歧或反直觉的见解，点出来\n\n"
        "要求：\n"
        "- 每个用户观点必须用换行符(\\n)分隔，绝对不要用分号连在一起\n"
        "- 评论引用要具体到观点内容，不要\"大家讨论了性能问题\"这种废话\n"
        "- 让读者看完就知道\"社区对这个事怎么看\"\n"
        "- 如果帖子本身是 Show HN，先说清楚作者做了什么\n"
        "- index 必须使用帖子列表中的原始序号，禁止重新从 1 编号\n\n"
        "范例：\n"
        '{{\"index\": 1, \"summary\": \"【SQLite 作者宣布不再接受外部 PR】Hacker News 社区对此反应两极。\\n'
        '用户 jsmith：单人维护反而保证了代码一致性，Linux 初期也是 Linus 一个人\\n'
        '用户 devguy：2024 年了还拒绝协作是傲慢\\n'
        '用户 dbexpert：SQLite 测试覆盖率 100% MC/DC，极为罕见，可能正是封闭开发的副产品\"}}\n\n'
        "请严格按照以下 JSON 格式返回，不要包含任何多余内容：\n"
        '{{"summaries": [{{"index": 1, "summary": "中文总结"}}, ...]}}\n\n'
        "帖子列表：\n{}"
    ).format(intro, stories_text)


def _apply_hn_summaries(stories, summaries):
    """把 AI 返回摘要写回 stories，并返回仍缺失摘要的 story 下标。"""
    for item in summaries or []:
        story_index = item.get("index", 0) - 1
        summary = (item.get("summary") or "").strip()
        if 0 <= story_index < len(stories) and summary:
            stories[story_index]["ai_summary"] = summary
        else:
            logger.warning("忽略无效 HN AI 摘要项: %s", item)

    return [
        index
        for index, story in enumerate(stories)
        if not story.get("ai_summary")
    ]


def _log_missing_hn_summaries(stories, missing_indexes, phase):
    """记录 HN 摘要缺失条目，便于远端日志定位。"""
    missing_titles = [
        "{}:{}".format(index + 1, stories[index].get("title", ""))
        for index in missing_indexes
    ]
    logger.warning(
        "HN AI %s摘要缺失 %d 条: %s",
        phase,
        len(missing_indexes),
        " | ".join(missing_titles),
    )


def _call_hn_ai_api(prompt, max_retries=10):
    """
    调用 OpenRouter API 进行 HN 内容总结。

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
                "content": "你是一个擅长提炼技术社区讨论精华的分析师。你的读者是忙碌的后端工程师，"
                           "他们想用 30 秒了解社区在争论什么、谁说了什么有价值的话。"
                           "请始终返回有效的 JSON 格式。",
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
            logger.info("调用 AI API 进行 HN 总结 (第 %d 次尝试)...", attempt + 1)
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
            logger.info("HN AI 响应长度: %d 字符", len(content))

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
            logger.error("HN AI API HTTP 错误 %d: %s", status, e)
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
                logger.warning("HN AI API 临时失败，等待 %.1f 秒后重试...", wait)
                time.sleep(wait)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error("解析 HN AI 响应失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5)
        except requests.exceptions.RequestException as e:
            logger.error("HN AI API 调用异常: %s", e)
            if attempt < max_retries - 1:
                time.sleep(10)
        except Exception as e:
            logger.error("HN AI API 非预期异常: %s", e)
            break

    return None
