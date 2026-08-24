# -*- coding: utf-8 -*-
"""
每日 AI 播客 TTS 合成。
"""

import asyncio
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

from config import (
    PODCAST_CHAPTER_PAUSE_SECONDS,
    PODCAST_TOPIC_PAUSE_SECONDS,
    PODCAST_TURN_PAUSE_SECONDS,
    PODCAST_TTS_MAX_RETRIES,
    PODCAST_TTS_PROVIDER,
    PODCAST_TTS_RETRY_SECONDS,
    PODCAST_TTS_TIMEOUT_SECONDS,
    PODCAST_SUBPROCESS_TIMEOUT_SECONDS,
    PODCAST_VOICE_FEMALE_PITCH,
    PODCAST_VOICE_FEMALE_RATE,
    PODCAST_VOICE_FEMALE_VOLUME,
    PODCAST_VOICE_FEMALE,
    PODCAST_VOICE_MALE_PITCH,
    PODCAST_VOICE_MALE_RATE,
    PODCAST_VOICE_MALE_VOLUME,
    PODCAST_VOICE_MALE,
)

logger = logging.getLogger(__name__)

MIN_MODEL_PAUSE_SECONDS = 0.6
MAX_MODEL_PAUSE_SECONDS = 2.0
ENDING_TURN_PAUSE_SECONDS = 0.7
PODCAST_AUDIO_SAMPLE_RATE = 24000
PODCAST_AUDIO_CHANNELS = 1
PODCAST_SILENCE_BITRATE = "48k"
PODCAST_OUTPUT_BITRATE = "128k"
MERGED_DURATION_TOLERANCE_RATIO = 0.02
MERGED_DURATION_TOLERANCE_MIN_SECONDS = 1.0
TTS_RETRY_BACKOFF_MAX_SECONDS = 60.0


def synthesize_podcast(turns, target_dir):
    """按男女角色生成音频片段，并合并成 podcast.mp3。"""
    if PODCAST_TTS_PROVIDER != "edge_tts":
        raise ValueError("暂不支持的 TTS provider: {}".format(PODCAST_TTS_PROVIDER))
    if not turns:
        raise ValueError("播客脚本为空，无法生成音频")

    target_dir = Path(target_dir)
    segments_dir = target_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    segment_infos = _collect_segment_infos(turns, segments_dir, synthesize=True)
    return _merge_podcast_segments(segment_infos, target_dir)


def merge_existing_podcast(turns, target_dir):
    """复用已有语音片段重新生成停顿、最终音频和时间线。"""
    if not turns:
        raise ValueError("播客脚本为空，无法重新合并音频")

    target_dir = Path(target_dir)
    segments_dir = target_dir / "segments"
    segment_infos = _collect_segment_infos(turns, segments_dir, synthesize=False)
    return _merge_podcast_segments(segment_infos, target_dir)


def _collect_segment_infos(turns, segments_dir, synthesize):
    segment_infos = []
    segments_dir = Path(segments_dir)
    if synthesize:
        segments_dir.mkdir(parents=True, exist_ok=True)

    for index, turn in enumerate(turns, 1):
        role = turn.get("role", "")
        text = (turn.get("text") or "").strip()
        if not text:
            continue
        text = _prepare_tts_text(text)
        if not text:
            continue
        segment_path = segments_dir / "{:03d}-{}.mp3".format(index, role or "speaker")
        if synthesize:
            if _is_reusable_segment(segment_path):
                logger.info("复用已有播客语音片段: %s", segment_path)
            else:
                voice = _voice_for_role(role)
                voice_options = _voice_options_for_role(role)
                _synthesize_edge_segment(text, voice, segment_path, **voice_options)
        elif not segment_path.exists() or segment_path.stat().st_size == 0:
            raise FileNotFoundError("播客语音片段不存在或为空: {}".format(segment_path))

        duration_seconds = _probe_duration_seconds_float(segment_path)
        if duration_seconds <= 0:
            raise RuntimeError("无法读取播客语音片段时长: {}".format(segment_path))
        segment_infos.append(
            {
                "index": index,
                "path": segment_path,
                "role": role,
                "text": text,
                "chapter": _normalize_optional_text(turn.get("chapter")),
                "pause_after_seconds": turn.get("pause_after_seconds"),
                "duration_seconds": duration_seconds,
            }
        )

    if not segment_infos:
        raise ValueError("播客脚本没有可合成文本")
    return segment_infos


def _merge_podcast_segments(segment_infos, target_dir):
    output_path = target_dir / "podcast.mp3"
    timeline, duration_seconds = _merge_segments(segment_infos, output_path)
    return {
        "audio_path": str(output_path),
        "duration_seconds": int(duration_seconds),
        "turn_timeline": timeline,
    }


def _is_reusable_segment(segment_path):
    """判断已有片段是否可直接复用：文件存在、非空且能读出有效时长。

    失败片段会被 _remove_empty_or_partial_file 清理，损坏片段读不出时长，
    二者都会被重新合成，因此复用判定是安全的。
    """
    try:
        if not segment_path.exists() or segment_path.stat().st_size == 0:
            return False
        return _probe_duration_seconds_float(segment_path) > 0
    except OSError:
        return False


def _voice_for_role(role):
    if role == "female":
        return PODCAST_VOICE_FEMALE
    return PODCAST_VOICE_MALE


def _voice_options_for_role(role):
    if role == "female":
        return {
            "rate": PODCAST_VOICE_FEMALE_RATE,
            "pitch": PODCAST_VOICE_FEMALE_PITCH,
            "volume": PODCAST_VOICE_FEMALE_VOLUME,
        }
    return {
        "rate": PODCAST_VOICE_MALE_RATE,
        "pitch": PODCAST_VOICE_MALE_PITCH,
        "volume": PODCAST_VOICE_MALE_VOLUME,
    }


def _prepare_tts_text(text):
    """清理不适合朗读的内容，并用标点制造更自然的短停顿。"""
    original = " ".join(str(text or "").split())
    if not original:
        return ""

    cleaned = original
    cleaned = re.sub(r"\[[^\]]+\]\([^)]+\)", lambda m: m.group(0).split("]")[0][1:], cleaned)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = cleaned.replace("；", "，").replace(";", "，")
    cleaned = re.sub(r"[。！？!?]{2,}", lambda m: m.group(0)[0], cleaned)
    cleaned = re.sub(r"([。！？!?])(?=\S)", r"\1 ", cleaned)
    cleaned = re.sub(r"(?<![，。！？!?])(不过|但是|所以|另外|这里|换句话说|也就是说)", r"，\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，")
    return cleaned or original


def _synthesize_edge_segment(text, voice, output_path, rate="+0%", pitch="+0Hz", volume="+0%"):
    rate = _normalize_edge_tts_signed_value(rate, "%")
    pitch = _normalize_edge_tts_signed_value(pitch, "Hz")
    volume = _normalize_edge_tts_signed_value(volume, "%")
    max_retries = max(1, PODCAST_TTS_MAX_RETRIES)
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            _synthesize_edge_segment_once(text, voice, output_path, rate, pitch, volume)
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise RuntimeError("TTS 生成了空音频文件")
            return
        except Exception as e:
            last_error = e
            _remove_empty_or_partial_file(output_path)
            if attempt >= max_retries:
                logger.error(
                    "播客语音片段生成失败 | voice=%s | text=%s | error=%s",
                    voice,
                    text[:40],
                    e,
                )
                raise
            logger.warning(
                "播客语音片段生成失败，准备重试 | voice=%s | attempt=%d/%d | text=%s | error=%s",
                voice,
                attempt,
                max_retries,
                text[:40],
                e,
            )
            _sleep_before_tts_retry(attempt)

    raise last_error


def _normalize_edge_tts_signed_value(value, suffix):
    """edge-tts 的 rate/pitch/volume 需要显式正负号，0 也要写成 +0。"""
    text = str(value or "").strip()
    if not text:
        return "+0{}".format(suffix)
    if text.startswith("+") or text.startswith("-"):
        return text
    if text.endswith(suffix):
        return "+{}".format(text)
    return text


def _synthesize_edge_segment_once(text, voice, output_path, rate, pitch, volume):
    async def _run():
        import edge_tts

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch,
            volume=volume,
        )
        try:
            await asyncio.wait_for(
                communicate.save(str(output_path)),
                timeout=PODCAST_TTS_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(
                "edge-tts 合成超时（超过 {:.0f} 秒未返回）".format(PODCAST_TTS_TIMEOUT_SECONDS)
            )

    logger.info("生成播客语音片段: %s", output_path)
    asyncio.run(_run())


def _remove_empty_or_partial_file(path):
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass


def _sleep_before_tts_retry(attempt):
    """单段 TTS 重试前的指数退避：3s/6s/12s/24s/48s...，上限 60s。

    线性短间隔（原 3s/6s/9s）容易整体落在同一个故障窗口内，导致连续重试全部失败。
    """
    seconds = min(
        PODCAST_TTS_RETRY_SECONDS * (2 ** max(0, attempt - 1)),
        TTS_RETRY_BACKOFF_MAX_SECONDS,
    )
    if seconds > 0:
        time.sleep(seconds)


def _merge_segments(segment_infos, output_path):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("未找到 ffmpeg，无法合并播客音频")
    if not shutil.which("ffprobe"):
        raise RuntimeError("未找到 ffprobe，无法校验播客音频")

    merge_paths, timeline, expected_duration = _merge_paths_and_timeline(
        segment_infos,
        output_path.parent,
    )
    list_path = output_path.parent / "segments.txt"
    with list_path.open("w", encoding="utf-8") as f:
        for segment_path in merge_paths:
            escaped = str(segment_path.resolve()).replace("'", "'\\''")
            f.write("file '{}'\n".format(escaped))

    raw_output_path = output_path.with_name("{}-raw{}".format(output_path.stem, output_path.suffix))
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar",
        str(PODCAST_AUDIO_SAMPLE_RATE),
        "-ac",
        str(PODCAST_AUDIO_CHANNELS),
        "-acodec",
        "libmp3lame",
        "-b:a",
        PODCAST_OUTPUT_BITRATE,
        str(raw_output_path),
    ]
    logger.info("合并播客音频: %s", output_path)
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=PODCAST_SUBPROCESS_TIMEOUT_SECONDS,
        )
        actual_duration = _probe_duration_seconds_float(raw_output_path)
        _validate_merged_duration(expected_duration, actual_duration)
        raw_output_path.replace(output_path)
    except Exception:
        _remove_empty_or_partial_file(raw_output_path)
        raise
    return timeline, actual_duration


def _validate_merged_duration(expected_duration, actual_duration):
    tolerance = max(
        MERGED_DURATION_TOLERANCE_MIN_SECONDS,
        expected_duration * MERGED_DURATION_TOLERANCE_RATIO,
    )
    if actual_duration <= 0 or abs(actual_duration - expected_duration) > tolerance:
        raise RuntimeError(
            "播客音频时长校验失败: expected={:.3f}s, actual={:.3f}s, tolerance={:.3f}s".format(
                expected_duration,
                actual_duration,
                tolerance,
            )
        )


def _segment_paths_with_turn_pause(segment_paths, target_dir):
    if PODCAST_TURN_PAUSE_SECONDS <= 0 or len(segment_paths) <= 1:
        return segment_paths

    silence_path = Path(target_dir) / "turn-pause.mp3"
    _ensure_silence_segment(silence_path, PODCAST_TURN_PAUSE_SECONDS)

    merge_paths = []
    for index, segment_path in enumerate(segment_paths):
        merge_paths.append(segment_path)
        if index < len(segment_paths) - 1:
            merge_paths.append(silence_path)
    return merge_paths


def _merge_paths_and_timeline(segment_infos, target_dir):
    if not segment_infos:
        return [], [], 0.0

    merge_paths = []
    timeline = []
    cursor = 0.0
    for index, info in enumerate(segment_infos):
        segment_path = info["path"]
        duration = max(0.0, float(info.get("duration_seconds") or 0))
        start_seconds = cursor
        merge_paths.append(segment_path)
        cursor += duration
        timeline.append(
            {
                "index": info.get("index", index + 1),
                "role": info.get("role", ""),
                "chapter": info.get("chapter", ""),
                "start_seconds": round(start_seconds, 3),
                "duration_seconds": round(duration, 3),
                "end_seconds": round(cursor, 3),
            }
        )

        if index >= len(segment_infos) - 1:
            continue

        pause_seconds = _pause_after_turn(info, segment_infos[index + 1])
        if pause_seconds <= 0:
            continue

        silence_path = _silence_segment_path(target_dir, pause_seconds)
        _ensure_silence_segment(silence_path, pause_seconds)
        merge_paths.append(silence_path)
        cursor += pause_seconds

    return merge_paths, timeline, round(cursor, 3)


def _pause_after_turn(current, next_info):
    requested = _coerce_pause_seconds(current.get("pause_after_seconds"))
    pause_seconds = requested if requested is not None else PODCAST_TURN_PAUSE_SECONDS

    current_chapter = _normalize_optional_text(current.get("chapter"))
    next_chapter = _normalize_optional_text(next_info.get("chapter"))
    if current_chapter and next_chapter and current_chapter != next_chapter:
        pause_seconds = max(pause_seconds, PODCAST_CHAPTER_PAUSE_SECONDS)
    elif _looks_like_topic_transition(current.get("text", ""), next_info.get("text", "")):
        pause_seconds = max(pause_seconds, PODCAST_TOPIC_PAUSE_SECONDS)
    elif _looks_like_closing_turn(current.get("text", ""), next_info.get("text", "")):
        pause_seconds = max(pause_seconds, ENDING_TURN_PAUSE_SECONDS)

    return max(0.0, pause_seconds)


def _coerce_pause_seconds(value):
    if value in (None, ""):
        return None
    try:
        return min(MAX_MODEL_PAUSE_SECONDS, max(MIN_MODEL_PAUSE_SECONDS, float(value)))
    except (TypeError, ValueError):
        return None


def _silence_segment_path(target_dir, duration_seconds):
    milliseconds = int(round(duration_seconds * 1000))
    return Path(target_dir) / "pause-{:04d}ms.mp3".format(milliseconds)


def _looks_like_topic_transition(text, next_text):
    combined = "{} {}".format(text or "", next_text or "")
    return bool(
        re.search(
            r"(接下来|然后我们|再看|换个|另一个|官方更新|社区|行动建议|最后一个环节)",
            combined,
        )
    )


def _looks_like_closing_turn(text, next_text):
    combined = "{} {}".format(text or "", next_text or "")
    return bool(re.search(r"(今天就聊到这里|下期再见|拜拜|感谢.*收听)", combined))


def _normalize_optional_text(value):
    return " ".join(str(value or "").split())


def _ensure_silence_segment(output_path, duration_seconds):
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r={}:cl=mono".format(PODCAST_AUDIO_SAMPLE_RATE),
        "-t",
        "{:.3f}".format(max(0.05, duration_seconds)),
        "-ar",
        str(PODCAST_AUDIO_SAMPLE_RATE),
        "-ac",
        str(PODCAST_AUDIO_CHANNELS),
        "-acodec",
        "libmp3lame",
        "-b:a",
        PODCAST_SILENCE_BITRATE,
        str(output_path),
    ]
    logger.info("生成播客转场静音: %s", output_path)
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=PODCAST_SUBPROCESS_TIMEOUT_SECONDS,
    )


def _probe_duration_seconds_float(audio_path):
    if not shutil.which("ffprobe"):
        raise RuntimeError("未找到 ffprobe，无法读取播客音频时长")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=PODCAST_SUBPROCESS_TIMEOUT_SECONDS,
        )
        return float(result.stdout.strip() or "0")
    except Exception as e:
        logger.warning("读取播客时长失败: %s", e)
        return 0.0
