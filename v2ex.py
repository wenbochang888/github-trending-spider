# -*- coding: utf-8 -*-
"""
V2EX 数据获取 + AI 总结模块

通过 V2EX 公开 API 获取全站热帖，节点白名单过滤技术内容，
获取帖子回复，调用 AI 生成中文总结。
"""

import json
import logging
import re
import time

import requests

from config import (
    AI_API_KEY,
    AI_APP_NAME,
    AI_API_URL,
    AI_MODEL,
    AI_REQUEST_PROXIES,
    SPIDER_REQUEST_PROXIES,
    V2EX_API_BASE,
    V2EX_MAX_RETRIES,
    V2EX_REPLIES_PER_TOPIC,
    V2EX_REQUEST_INTERVAL,
    V2EX_TOP_COUNT,
)

logger = logging.getLogger(__name__)

# 技术相关节点白名单，用于排序优先级（白名单节点排前面，其余排后面）
V2EX_TECH_NODES = {
    # 编程语言
    "programmer", "python", "java", "nodejs", "golang", "rust",
    # 系统/平台
    "linux", "apple", "android", "macos", "docker", "kubernetes",
    # 开发领域
    "devops", "cloud", "frontend", "backend", "serverless",
    # AI 相关
    "ai", "openai", "claude", "cursor",
    # 数据库
    "database", "redis", "mysql", "mongodb",
    # 工具/社区
    "git", "github", "open-source", "create", "share",
    # 安全/区块链
    "security", "crypto",
    # 职业/创业
    "career", "remote", "startups", "ideas",
    # 产品/设计
    "productdesign", "react", "vue",
}


# =========================================================================
# 1. 数据获取
# =========================================================================
def fetch_v2ex_hot_topics(count=None, max_retries=None):
    """
    获取 V2EX 全站热帖，按技术相关性排序（技术帖优先，非技术帖靠后）。

    Args:
        count: 最多取前 N 条，默认使用 V2EX_TOP_COUNT 配置
        max_retries: 最大重试次数，默认使用 V2EX_MAX_RETRIES 配置

    Returns:
        list[dict]: 排序后的热帖列表（技术帖在前），每个 dict 含
            id, title, content, url, created, node, member
    """
    if count is None:
        count = V2EX_TOP_COUNT
    if max_retries is None:
        max_retries = V2EX_MAX_RETRIES

    url = "{}/topics/hot.json".format(V2EX_API_BASE)

    for attempt in range(max_retries):
        try:
            logger.info("正在获取 V2EX 全站热帖 (第 %d 次尝试)", attempt + 1)
            resp = requests.get(url, timeout=30, proxies=SPIDER_REQUEST_PROXIES)
            resp.raise_for_status()
            topics = resp.json()

            if not isinstance(topics, list):
                logger.warning("V2EX API 返回非列表数据: %s", type(topics))
                continue

            # 按技术相关性排序：白名单节点排前面，其他排后面
            tech_topics = [
                t for t in topics
                if t.get("node", {}).get("name", "").lower() in V2EX_TECH_NODES
            ]
            non_tech_topics = [
                t for t in topics
                if t.get("node", {}).get("name", "").lower() not in V2EX_TECH_NODES
            ]
            sorted_topics = tech_topics + non_tech_topics
            logger.info(
                "V2EX 热帖: 共 %d 条，技术节点 %d 条在前，非技术 %d 条在后",
                len(topics), len(tech_topics), len(non_tech_topics),
            )

            return sorted_topics[:count]

        except requests.RequestException as e:
            logger.warning("获取 V2EX 热帖失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))

    logger.error("获取 V2EX 热帖失败，已达最大重试次数 %d", max_retries)
    return []


def fetch_topic_replies(topics, replies_per_topic=None):
    """
    为每个帖子获取回复。

    Args:
        topics: 帖子列表
        replies_per_topic: 每帖获取回复数，默认使用 V2EX_REPLIES_PER_TOPIC 配置

    Returns:
        list[dict]: 增强后的帖子列表（每个帖子新增 "replies" 字段）
    """
    if replies_per_topic is None:
        replies_per_topic = V2EX_REPLIES_PER_TOPIC

    for idx, topic in enumerate(topics):
        topic_id = topic.get("id")
        if not topic_id:
            topic["replies"] = []
            continue

        url = "{}/replies/show.json?topic_id={}".format(V2EX_API_BASE, topic_id)
        try:
            time.sleep(V2EX_REQUEST_INTERVAL)
            resp = requests.get(url, timeout=15, proxies=SPIDER_REQUEST_PROXIES)

            if resp.status_code == 403:
                logger.warning("V2EX 限流(403)，跳过剩余帖子回复获取")
                topic["replies"] = []
                # 后续帖子也标记为空回复
                for t in topics[idx + 1:]:
                    t["replies"] = []
                break

            resp.raise_for_status()
            all_replies = resp.json()

            if isinstance(all_replies, list):
                # 取前 N 条回复
                replies = []
                for r in all_replies[:replies_per_topic]:
                    content = r.get("content", "").strip()
                    if content:
                        replies.append({
                            "id": r.get("id"),
                            "member": r.get("member", {}).get("username", "anonymous"),
                            "content": content[:500],  # 截断超长回复
                        })
                topic["replies"] = replies
            else:
                topic["replies"] = []

        except requests.RequestException as e:
            logger.debug("获取帖子 %s 回复失败: %s", topic_id, e)
            topic["replies"] = []

    total_replies = sum(len(t.get("replies", [])) for t in topics)
    logger.info("V2EX 回复获取完成: 共 %d 条回复", total_replies)
    return topics


# =========================================================================
# 2. AI 总结
# =========================================================================
def ai_summarize_v2ex(topics):
    """
    调用 AI 对 V2EX 帖子和回复进行中文总结。

    Args:
        topics: 帖子列表（已含 replies 字段）

    Returns:
        list[dict]: 每个帖子新增 "ai_summary" 字段
    """
    if not topics:
        return topics

    if not AI_API_KEY:
        logger.warning("未配置 AI_API_KEY，跳过 V2EX AI 总结")
        for t in topics:
            t["ai_summary"] = "（未配置 AI Token，无法生成总结）"
        return topics

    # 构建 prompt
    topic_text_lines = []
    for i, t in enumerate(topics, 1):
        node_name = t.get("node", {}).get("title", "")
        member_name = t.get("member", {}).get("username", "")
        content = t.get("content", "")
        if len(content) > 300:
            content = content[:300] + "..."

        line = "{}. [{}] {} (作者: {})\n   正文: {}".format(
            i,
            node_name,
            t.get("title", ""),
            member_name,
            content or "(无正文)",
        )

        # 添加回复
        replies = t.get("replies", [])
        if replies:
            line += "\n   热门回复:"
            for j, r in enumerate(replies, 1):
                reply_content = r.get("content", "")
                if len(reply_content) > 200:
                    reply_content = reply_content[:200] + "..."
                line += "\n     回复{} [{}]: {}".format(
                    j, r.get("member", "?"), reply_content
                )

        topic_text_lines.append(line)

    topics_text = "\n\n".join(topic_text_lines)

    prompt = (
        "以下是 V2EX 今日 Top {} 热帖及其热门回复。\n\n"
        "请为每个帖子写中文总结（80-120 字），结构如下：\n"
        "1.【话题】一句话说清这个帖子在讨论什么（15 字以内）\n"
        "2.【社区声音】挑 2-3 条最有代表性的回复观点，每条独占一行，格式：\n"
        "   用户 xxx：具体观点\n"
        "   用户 yyy：具体观点\n\n"
        "要求：\n"
        "- 每个用户观点必须用换行符(\\n)分隔，绝对不要用分号连在一起\n"
        "- 回复引用要具体到观点内容，不要\"大家讨论了xxx\"这种废话\n"
        "- 语气像在茶水间跟同事八卦\"V站最近在吵什么\"\n"
        "- 禁止使用：\"引发热议\"\"大家纷纷表示\"\"网友认为\"等新闻体\n"
        "- 如果帖子是求助帖，直接说清问题和最有用的回复建议\n\n"
        "范例：\n"
        '{{\"index\": 1, \"summary\": \"【远程工作时薪谈崩了】楼主远程岗开价 800/天被甲方砍到 500。\\n'
        '用户 zhangsan：500 的话不如去美团送外卖，时薪更高\\n'
        '用户 lisi：看技术栈，如果是 CRUD 确实不值 800\\n'
        '意外发现好几个人推荐了 Toptal 平台接海外单。\"}}\n\n'
        "请严格按照以下 JSON 格式返回，不要包含任何多余内容：\n"
        '{{"summaries": [{{"index": 1, "summary": "中文总结"}}, ...]}}\n\n'
        "帖子列表：\n{}"
    ).format(len(topics), topics_text)

    try:
        summaries = _call_v2ex_ai_api(prompt)
        if summaries:
            for item in summaries:
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(topics):
                    topics[idx]["ai_summary"] = item.get("summary", "")
    except Exception as e:
        logger.error("V2EX AI 总结失败: %s", e)

    # 确保每个 topic 都有 ai_summary 字段
    for t in topics:
        if "ai_summary" not in t:
            t["ai_summary"] = "（AI 总结生成失败）"

    return topics


def _call_v2ex_ai_api(prompt, max_retries=10):
    """
    调用 OpenRouter API 进行 V2EX 内容总结。

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
                "content": "你是一个关注中文技术社区动态的观察员。你的读者是忙碌的后端工程师，"
                           "他们想用 30 秒了解 V2EX 今天在讨论什么有意思的话题、谁说了什么有价值的话。"
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
            logger.info("调用 AI API 进行 V2EX 总结 (第 %d 次尝试)...", attempt + 1)
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
            logger.info("V2EX AI 响应长度: %d 字符", len(content))

            # 尝试解析 JSON（处理可能的 markdown 代码块包裹）
            content = content.strip()
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            parsed = json.loads(content)
            return parsed.get("summaries", [])

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            logger.error("V2EX AI API HTTP 错误 %d: %s", status, e)
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
                logger.warning("V2EX AI API 临时失败，等待 %.1f 秒后重试...", wait)
                time.sleep(wait)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error("解析 V2EX AI 响应失败: %s", e)
            if attempt < max_retries - 1:
                time.sleep(5)
        except requests.exceptions.RequestException as e:
            logger.error("V2EX AI API 调用异常: %s", e)
            if attempt < max_retries - 1:
                time.sleep(10)
        except Exception as e:
            logger.error("V2EX AI API 非预期异常: %s", e)
            break

    return None
