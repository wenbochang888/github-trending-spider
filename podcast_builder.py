# -*- coding: utf-8 -*-
"""
每日 AI 播客脚本生成和生成任务编排。
"""

import json
import logging
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from config import (
    AI_API_KEY,
    AI_API_URL,
    AI_APP_NAME,
    AI_REQUEST_PROXIES,
    OUTPUT_ARCHIVE_DIR,
    PODCAST_ENABLED,
    PODCAST_EXCLUDED_SOURCE_IDS,
    PODCAST_MAX_DURATION_MINUTES,
    PODCAST_MIN_DURATION_MINUTES,
    PODCAST_MIN_SCRIPT_CHARS,
    PODCAST_MIN_TURN_COUNT,
    PODCAST_SCRIPT_MAX_RETRIES,
    PODCAST_SCRIPT_MODEL,
    PODCAST_SCRIPT_PROVIDER,
    PODCAST_SCRIPT_RETRY_SECONDS,
    PODCAST_TARGET_DATE_MODE,
)
from content_store import load_history_archive_snapshot
from podcast_store import (
    acquire_podcast_lock,
    build_failed_metadata,
    has_successful_podcast,
    is_valid_podcast_date,
    load_podcast_metadata,
    load_podcast_script,
    podcast_audio_path,
    podcast_dir,
    podcast_metadata_path,
    release_podcast_lock,
    write_podcast_metadata,
    write_podcast_script,
)
from podcast_tts import merge_existing_podcast, synthesize_podcast
from source_registry import SOURCE_DEFINITIONS

logger = logging.getLogger(__name__)

MAX_ITEMS_PER_SOURCE = 8


def resolve_target_content_date(run_at=None, mode=PODCAST_TARGET_DATE_MODE):
    """根据调度时间计算播客内容日期。"""
    if run_at is None:
        run_at = datetime.now()
    if mode != "yesterday":
        raise ValueError("暂不支持的播客目标日期模式: {}".format(mode))
    return (run_at.date() - timedelta(days=1)).isoformat()


def run_podcast_generation(scheduled_time=None, output_dir=OUTPUT_ARCHIVE_DIR):
    """执行一次每日播客生成任务。"""
    if not PODCAST_ENABLED:
        logger.info("[播客] PODCAST_ENABLED=false，跳过播客生成")
        return {"status": "disabled"}

    run_at = scheduled_time if hasattr(scheduled_time, "date") else datetime.now()
    date_text = resolve_target_content_date(run_at)

    if has_successful_podcast(date_text, output_dir):
        logger.info("[播客] %s 已成功生成，跳过", date_text)
        return {"status": "skipped", "reason": "already-success", "date": date_text}

    if not acquire_podcast_lock(date_text, output_dir):
        logger.warning("[播客] %s 已有生成任务运行中，跳过", date_text)
        return {"status": "skipped", "reason": "locked", "date": date_text}

    source_count = 0
    item_count = 0
    try:
        snapshots = load_podcast_source_snapshots(date_text, output_dir)
        source_count = len(snapshots)
        item_count = sum(len(snapshot.get("items", [])) for snapshot in snapshots)
        if item_count == 0:
            raise RuntimeError("{} 没有可用于生成播客的归档内容".format(date_text))

        script = load_reusable_podcast_script(date_text, output_dir)
        if not script:
            script = build_podcast_script(date_text, snapshots)
            retry_script = _retry_script_if_quality_is_low(date_text, snapshots, script)
            if retry_script:
                script = retry_script
            write_podcast_script(date_text, script, output_dir)

        tts_result = synthesize_podcast(script.get("turns", []), podcast_dir(date_text, output_dir))
        duration_seconds = tts_result.get("duration_seconds", 0)
        if duration_seconds and duration_seconds < PODCAST_MIN_DURATION_MINUTES * 60:
            logger.warning(
                "[播客] %s 音频时长低于目标下限 | duration=%ss | min=%sm",
                date_text,
                duration_seconds,
                PODCAST_MIN_DURATION_MINUTES,
            )
        metadata = {
            "date": date_text,
            "title": script.get("title") or "{} AI 音频日报".format(date_text),
            "summary": script.get("summary", ""),
            "audio_url": "/api/podcasts/{}/podcast.mp3".format(date_text),
            "duration_seconds": duration_seconds,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_count": source_count,
            "item_count": item_count,
            "status": "success",
            "error": "",
            "chapters": build_timed_chapters(
                script.get("chapters", []),
                tts_result.get("turn_timeline", []),
                duration_seconds,
            ),
        }
        write_podcast_metadata(metadata, output_dir)
        logger.info("[播客] %s 生成完成", date_text)
        return {"status": "success", "date": date_text, "metadata": metadata}
    except Exception as e:
        logger.exception("[播客] %s 生成失败: %s", date_text, e)
        metadata = build_failed_metadata(
            date_text,
            e,
            source_count=source_count,
            item_count=item_count,
        )
        write_podcast_metadata(metadata, output_dir)
        return {"status": "failed", "date": date_text, "error": str(e)}
    finally:
        release_podcast_lock(date_text, output_dir)


def rebuild_podcast_audio(date_text, output_dir=OUTPUT_ARCHIVE_DIR):
    """复用指定日期已有脚本和语音片段，重新合并音频并回填 metadata。"""
    if not is_valid_podcast_date(date_text):
        return {"status": "failed", "date": date_text, "error": "播客日期无效"}

    existing_metadata = load_podcast_metadata(date_text, output_dir)
    if not existing_metadata:
        return {"status": "failed", "date": date_text, "error": "播客 metadata 不存在"}
    if existing_metadata.get("date") != date_text:
        return {"status": "failed", "date": date_text, "error": "播客 metadata 日期与目标日期不一致"}

    script = load_reusable_podcast_script(date_text, output_dir)
    if not script:
        return {"status": "failed", "date": date_text, "error": "播客脚本不存在或不可复用"}

    if not acquire_podcast_lock(date_text, output_dir):
        logger.warning("[播客] %s 已有任务运行中，跳过音频重合并", date_text)
        return {"status": "skipped", "reason": "locked", "date": date_text}

    snapshots = []
    try:
        snapshot_paths = [
            podcast_audio_path(date_text, output_dir),
            podcast_metadata_path(date_text, output_dir),
        ]
        for path in snapshot_paths:
            snapshots.append(_snapshot_rebuild_file(path))

        tts_result = merge_existing_podcast(
            script.get("turns", []),
            podcast_dir(date_text, output_dir),
        )
        duration_seconds = tts_result.get("duration_seconds", 0)
        metadata = dict(existing_metadata)
        metadata.update(
            {
                "title": existing_metadata.get("title") or script.get("title")
                or "{} AI 音频日报".format(date_text),
                "summary": existing_metadata.get("summary") or script.get("summary", ""),
                "audio_url": "/api/podcasts/{}/podcast.mp3".format(date_text),
                "duration_seconds": duration_seconds,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "status": "success",
                "error": "",
                "chapters": build_timed_chapters(
                    script.get("chapters", []),
                    tts_result.get("turn_timeline", []),
                    duration_seconds,
                ),
            }
        )
        write_podcast_metadata(
            metadata,
            output_dir,
            update_latest=True,
        )
        logger.info("[播客] %s 已复用现有语音片段完成重合并", date_text)
        _discard_rebuild_snapshots(snapshots)
        snapshots = []
        return {"status": "success", "date": date_text, "metadata": metadata}
    except Exception as e:
        _restore_rebuild_snapshots(snapshots)
        snapshots = []
        logger.exception("[播客] %s 音频重合并失败，保留原文件和 metadata: %s", date_text, e)
        return {"status": "failed", "date": date_text, "error": str(e)}
    finally:
        _discard_rebuild_snapshots(snapshots)
        release_podcast_lock(date_text, output_dir)


def _snapshot_rebuild_file(path):
    """为重合并可能改写的正式文件创建同目录临时快照。"""
    target = Path(path)
    snapshot = {"target": target, "backup": None, "existed": target.exists()}
    if not snapshot["existed"]:
        return snapshot

    fd, backup_name = tempfile.mkstemp(
        prefix=".{}-rebuild-".format(target.name),
        suffix=".bak",
        dir=str(target.parent),
    )
    os.close(fd)
    backup_path = Path(backup_name)
    try:
        shutil.copy2(str(target), str(backup_path))
    except Exception:
        try:
            backup_path.unlink()
        except FileNotFoundError:
            pass
        raise
    snapshot["backup"] = backup_path
    return snapshot


def _restore_rebuild_snapshots(snapshots):
    for snapshot in reversed(snapshots):
        target = snapshot["target"]
        backup = snapshot["backup"]
        try:
            if snapshot["existed"] and backup and backup.exists():
                backup.replace(target)
            elif not snapshot["existed"]:
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass
        except Exception as e:
            logger.exception("[播客] 回滚重合并文件失败 | 文件=%s | 错误=%s", target, e)


def _discard_rebuild_snapshots(snapshots):
    for snapshot in snapshots:
        backup = snapshot.get("backup")
        if backup:
            try:
                backup.unlink()
            except FileNotFoundError:
                pass


def load_podcast_source_snapshots(date_text, output_dir=OUTPUT_ARCHIVE_DIR):
    """读取目标日期各来源最新归档。"""
    snapshots = []
    excluded_source_ids = _parse_source_id_list(PODCAST_EXCLUDED_SOURCE_IDS)
    for source in SOURCE_DEFINITIONS:
        source_id = source["id"]
        if source_id in excluded_source_ids:
            logger.info("[播客] 来源=%s | 日期=%s | 已配置排除", source_id, date_text)
            continue
        snapshot, served_from, batch_file = load_history_archive_snapshot(
            source_id,
            date_text,
            output_dir=output_dir,
        )
        if not snapshot:
            logger.info(
                "[播客] 来源=%s | 日期=%s | 读取自=%s | 无归档",
                source_id,
                date_text,
                served_from,
            )
            continue
        podcast_snapshot = dict(snapshot)
        podcast_snapshot["source"] = snapshot.get("source", source)
        podcast_snapshot["batch_file"] = batch_file
        podcast_snapshot["items"] = snapshot.get("items", [])[:MAX_ITEMS_PER_SOURCE]
        snapshots.append(podcast_snapshot)
    return snapshots


def _parse_source_id_list(value):
    if not value:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return {item.strip() for item in str(value).split(",") if item.strip()}


def build_podcast_script(date_text, snapshots):
    """调用 OpenRouter，把归档资讯生成男女对话脚本。"""
    if PODCAST_SCRIPT_PROVIDER != "openrouter":
        raise ValueError("暂不支持的播客脚本 provider: {}".format(PODCAST_SCRIPT_PROVIDER))
    if not AI_API_KEY:
        raise RuntimeError("未配置 AI_API_KEY，无法生成播客脚本")

    prompt = _build_script_prompt(date_text, snapshots)
    payload = _call_script_ai_api(prompt)
    return _normalize_script_payload(date_text, payload)


def load_reusable_podcast_script(date_text, output_dir=OUTPUT_ARCHIVE_DIR):
    """失败重跑时优先复用已生成且合法的脚本，避免重复调用模型。"""
    payload = load_podcast_script(date_text, output_dir)
    if not payload:
        return None

    try:
        script = _normalize_script_payload(date_text, payload)
    except Exception as e:
        logger.warning("[播客] %s 已有脚本不可复用，将重新生成: %s", date_text, e)
        return None

    logger.info("[播客] %s 复用已有播客脚本", date_text)
    return script


def _build_script_prompt(date_text, snapshots):
    lines = []
    for snapshot in snapshots:
        source = snapshot.get("source", {})
        source_label = source.get("label") or source.get("name") or source.get("id", "")
        lines.append("来源: {}".format(source_label))
        for index, item in enumerate(snapshot.get("items", []), 1):
            lines.append(
                "{}. 标题: {}\n   链接: {}\n   摘要: {}\n   后端关注点: {}".format(
                    index,
                    item.get("title", ""),
                    item.get("url", ""),
                    item.get("chinese_summary") or item.get("original_summary", ""),
                    item.get("backend_focus", ""),
                )
            )
        lines.append("")

    return (
        "请把以下 {} 的 AI 技术资讯改写成一段中文双人播客脚本。\n"
        "目标音频时长控制在 {} 到 {} 分钟，脚本文字总量约 1800 到 2600 个中文字符，"
        "turns 总轮数约 35 到 50 轮。\n"
        "整体风格：像两个熟悉 AI 基础设施和后端工程的人在录一段真实节目，"
        "不是新闻播报，也不是把摘要逐条朗读。\n"
        "要求：\n"
        "1. 保留 5 个章节：片头、开源热榜、社区讨论、官方更新、今日行动建议；"
        "章节标题可以更口语，但语义不要偏离。\n"
        "2. 每个 turns 元素只写一个角色的一小轮话，建议 1 到 3 个短句；"
        "多用追问、补充、确认、轻微转折和自然承接，避免一人连续讲很长。\n"
        "3. 不要使用模板化播报腔。尽量少写“值得关注”“从后端角度看”“今天我们看到”"
        "“接下来我们来看”“总的来说”等 AI 常见套话。\n"
        "4. 允许少量口语停顿词，例如“嗯”“对”“你看”“这里有个点”，但不要堆砌，"
        "不要写舞台说明、括号表情或音效说明。\n"
        "5. 遇到英文项目名、模型名、公司名，保留原文；不要朗读 URL，不要逐字符解释链接。\n"
        "6. 只挑最有信息密度的内容聊，允许合并同类项；听众应该能听懂为什么这条和工程实践有关。\n"
        "7. 额外生成 summary：用 50 到 100 个中文词语概括今天的热点，不要写“基于昨天”、"
        "不要写“男女对话”、不要描述生成方式。\n"
        "8. 每个 turns 元素额外包含 chapter 和 pause_after_seconds："
        "chapter 必须等于所属章节标题；pause_after_seconds 是本轮后建议停顿秒数，"
        "普通接话 0.8，话题转换 1.1，章节切换 1.6，收尾 0.7。\n"
        "9. 严格返回 JSON，不要包含 Markdown。\n"
        "JSON 格式：\n"
        "{{\"title\":\"标题\",\"summary\":\"50到100个中文词语的热点总结\","
        "\"chapters\":[{{\"time\":\"00:00\",\"title\":\"今日主线\"}}],"
        "\"turns\":[{{\"role\":\"male\",\"chapter\":\"今日主线\","
        "\"pause_after_seconds\":0.8,\"text\":\"男声台词\"}},"
        "{{\"role\":\"female\",\"chapter\":\"今日主线\","
        "\"pause_after_seconds\":1.1,\"text\":\"女声台词\"}}]}}\n\n"
        "内容列表：\n{}"
    ).format(
        date_text,
        PODCAST_MIN_DURATION_MINUTES,
        PODCAST_MAX_DURATION_MINUTES,
        "\n".join(lines),
    )


def _call_script_ai_api(prompt):
    headers = {
        "Authorization": "Bearer {}".format(AI_API_KEY),
        "Content-Type": "application/json",
    }
    if AI_APP_NAME:
        headers["X-Title"] = AI_APP_NAME
    payload = {
        "model": PODCAST_SCRIPT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一个懂 AI 基础设施和后端工程的中文播客编辑。请始终返回有效 JSON。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 6000,
        "reasoning": {"enabled": False},
        "response_format": {"type": "json_object"},
    }
    url = "{}/chat/completions".format(AI_API_URL)
    max_retries = max(1, PODCAST_SCRIPT_MAX_RETRIES)
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                proxies=AI_REQUEST_PROXIES,
                timeout=90,
            )
            if _is_retryable_status(response.status_code) and attempt < max_retries:
                logger.warning(
                    "[播客] 脚本生成 API 临时失败 | status=%s | attempt=%d/%d",
                    response.status_code,
                    attempt,
                    max_retries,
                )
                retry_after = (
                    response.headers.get("Retry-After")
                    if response.status_code == 429
                    else None
                )
                _sleep_before_retry(attempt, retry_after=retry_after)
                continue

            if response.status_code == 401:
                logger.error("[播客] OpenRouter 鉴权失败，请检查 AI_API_KEY 是否有效")
            elif response.status_code == 402:
                logger.error("[播客] OpenRouter 余额或 Key 额度不足，请检查账户额度")
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return _parse_json_response(content)
        except requests.exceptions.RequestException as e:
            last_error = e
            if not _is_retryable_request_error(e) or attempt >= max_retries:
                raise
            logger.warning(
                "[播客] 脚本生成 API 网络异常，准备重试 | error=%s | attempt=%d/%d",
                e,
                attempt,
                max_retries,
            )
            _sleep_before_retry(attempt)

    raise last_error or RuntimeError("播客脚本生成失败")


def _is_retryable_status(status_code):
    return status_code in (408, 429, 500, 502, 503, 504)


def _is_retryable_request_error(error):
    return isinstance(
        error,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.SSLError,
            requests.exceptions.Timeout,
        ),
    )


def _sleep_before_retry(attempt, retry_after=None):
    seconds = PODCAST_SCRIPT_RETRY_SECONDS * attempt
    if retry_after is not None:
        try:
            seconds = min(120.0, max(0.0, float(retry_after)))
        except (TypeError, ValueError):
            pass
    if seconds > 0:
        time.sleep(seconds)


def _parse_json_response(content):
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _normalize_script_payload(date_text, payload):
    if not isinstance(payload, dict):
        raise ValueError("播客脚本响应不是 JSON 对象")

    turns = []
    for turn in payload.get("turns", []):
        role = turn.get("role")
        text = (turn.get("text") or "").strip()
        if role not in ("male", "female") or not text:
            continue
        normalized_turn = {"role": role, "text": text}
        chapter = _normalize_text(turn.get("chapter"))
        if chapter:
            normalized_turn["chapter"] = chapter
        pause_after_seconds = _parse_optional_float(turn.get("pause_after_seconds"))
        if pause_after_seconds is not None:
            normalized_turn["pause_after_seconds"] = pause_after_seconds
        turns.append(normalized_turn)

    if not turns:
        raise ValueError("播客脚本没有有效台词")

    chapters = payload.get("chapters") or [
        {"time": "00:00", "title": "今日主线"},
        {"time": "01:10", "title": "开源热榜"},
        {"time": "03:20", "title": "社区讨论"},
        {"time": "05:10", "title": "官方更新"},
    ]

    return {
        "date": date_text,
        "title": payload.get("title") or "{} AI 音频日报".format(date_text),
        "summary": _normalize_summary(payload.get("summary")),
        "chapters": [
            {
                "time": str(chapter.get("time", "")),
                "title": str(chapter.get("title", "")),
            }
            for chapter in chapters
            if chapter.get("title")
        ],
        "turns": turns,
    }


def _normalize_summary(value):
    summary = " ".join(str(value or "").split())
    return summary[:220]


def _retry_script_if_quality_is_low(date_text, snapshots, script):
    issues = _script_quality_issues(script)
    if not issues:
        return None

    logger.warning("[播客] %s 脚本质量不足，准备重试一次 | issues=%s", date_text, ",".join(issues))
    retry_script = build_podcast_script(date_text, snapshots)
    retry_issues = _script_quality_issues(retry_script)
    if retry_issues:
        logger.warning(
            "[播客] %s 脚本重试后仍未达到目标，将使用重试结果 | issues=%s",
            date_text,
            ",".join(retry_issues),
        )
    return retry_script


def _script_quality_issues(script):
    turns = script.get("turns", [])
    total_chars = sum(len(turn.get("text", "")) for turn in turns)
    issues = []
    if len(turns) < PODCAST_MIN_TURN_COUNT:
        issues.append("turn_count={}".format(len(turns)))
    if total_chars < PODCAST_MIN_SCRIPT_CHARS:
        issues.append("script_chars={}".format(total_chars))
    return issues


def build_timed_chapters(chapters, turn_timeline, duration_seconds):
    normalized_chapters = _normalize_chapters(chapters)
    if not normalized_chapters:
        normalized_chapters = [{"time": "00:00", "title": "今日主线"}]

    duration_seconds = max(0, int(duration_seconds or 0))
    timeline_by_chapter = {}
    for item in turn_timeline or []:
        chapter = _normalize_text(item.get("chapter"))
        if not chapter or chapter in timeline_by_chapter:
            continue
        timeline_by_chapter[chapter] = max(0, float(item.get("start_seconds") or 0))

    result = []
    previous_second = 0
    chapter_count = len(normalized_chapters)
    for index, chapter in enumerate(normalized_chapters):
        title = chapter["title"]
        matched_second = timeline_by_chapter.get(title)
        if matched_second is None:
            matched_second = _fallback_chapter_second(
                index,
                chapter_count,
                previous_second,
                duration_seconds,
            )
        second = min(duration_seconds, max(previous_second, int(matched_second)))
        result.append({"time": _format_seconds(second), "title": title})
        previous_second = second
    return result


def _normalize_chapters(chapters):
    normalized = []
    for chapter in chapters or []:
        title = _normalize_text(chapter.get("title"))
        if not title:
            continue
        normalized.append({"time": str(chapter.get("time", "")), "title": title})
    return normalized


def _fallback_chapter_second(index, chapter_count, previous_second, duration_seconds):
    if index == 0 or duration_seconds <= 0:
        return 0
    estimated = int(duration_seconds * index / max(1, chapter_count))
    return max(previous_second, estimated)


def _format_seconds(seconds):
    seconds = max(0, int(seconds))
    return "{:02d}:{:02d}".format(seconds // 60, seconds % 60)


def _normalize_text(value):
    return " ".join(str(value or "").split())


def _parse_optional_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
