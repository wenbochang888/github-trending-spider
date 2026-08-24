# -*- coding: utf-8 -*-
"""
FastAPI 进程内采集调度器。

生产环境应使用单 worker 运行 uvicorn，避免多个 worker 同时启动调度器。
"""

import logging
import threading
import time
from datetime import datetime, timedelta

from config import (
    PODCAST_ENABLED,
    PODCAST_RUN_STALE_WARN_SECONDS,
    PODCAST_SCHEDULE_TIME,
    SPIDER_RUN_ON_STARTUP,
    SPIDER_SCHEDULE_TIMES,
    SPIDER_SCHEDULER_ENABLED,
)

logger = logging.getLogger(__name__)

_scheduler_thread = None
_podcast_scheduler_thread = None
_stop_event = threading.Event()
_run_lock = threading.Lock()
_podcast_run_lock = threading.Lock()
_podcast_run_started_at = None


def parse_schedule_times(value):
    """解析 HH:MM,HH:MM 格式的每日调度时间。"""
    result = []
    for item in (value or "").split(","):
        text = item.strip()
        if not text:
            continue
        hour_text, minute_text = text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("调度时间超出范围: {}".format(text))
        result.append((hour, minute))

    if not result:
        raise ValueError("至少需要配置一个调度时间")
    return sorted(set(result))


def start_scheduler():
    """启动后台调度线程。"""
    global _scheduler_thread, _podcast_scheduler_thread

    if not SPIDER_SCHEDULER_ENABLED and not PODCAST_ENABLED:
        logger.info("内置调度已关闭")
        return

    _stop_event.clear()

    if SPIDER_SCHEDULER_ENABLED:
        if _scheduler_thread and _scheduler_thread.is_alive():
            logger.info("内置采集调度已在运行")
        else:
            try:
                schedule_times = parse_schedule_times(SPIDER_SCHEDULE_TIMES)
            except ValueError as e:
                logger.error("内置采集调度配置无效: %s", e)
            else:
                _scheduler_thread = threading.Thread(
                    target=_scheduler_loop,
                    args=(schedule_times,),
                    name="spider-scheduler",
                    daemon=True,
                )
                _scheduler_thread.start()
                logger.info("内置采集调度已启动: %s", SPIDER_SCHEDULE_TIMES)

    if PODCAST_ENABLED:
        if _podcast_scheduler_thread and _podcast_scheduler_thread.is_alive():
            logger.info("每日播客调度已在运行")
        else:
            try:
                podcast_schedule_times = parse_schedule_times(PODCAST_SCHEDULE_TIME)
            except ValueError as e:
                logger.error("每日播客调度配置无效: %s", e)
            else:
                _podcast_scheduler_thread = threading.Thread(
                    target=_podcast_scheduler_loop,
                    args=(podcast_schedule_times,),
                    name="podcast-scheduler",
                    daemon=True,
                )
                _podcast_scheduler_thread.start()
                logger.info("每日播客调度已启动: %s", PODCAST_SCHEDULE_TIME)

    if SPIDER_SCHEDULER_ENABLED and SPIDER_RUN_ON_STARTUP:
        trigger_spider_async("startup")


def stop_scheduler():
    """停止后台调度线程。"""
    _stop_event.set()
    if _scheduler_thread and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=5)
    if _podcast_scheduler_thread and _podcast_scheduler_thread.is_alive():
        _podcast_scheduler_thread.join(timeout=5)
    logger.info("内置调度已停止")


def trigger_spider_async(reason):
    """异步触发一次采集。"""
    thread = threading.Thread(
        target=_run_spider_with_lock,
        args=(reason,),
        name="spider-runner",
        daemon=True,
    )
    thread.start()
    return thread


def trigger_podcast_async(reason, scheduled_time=None):
    """异步触发一次播客生成。"""
    thread = threading.Thread(
        target=_run_podcast_with_lock,
        args=(reason, scheduled_time),
        name="podcast-runner",
        daemon=True,
    )
    thread.start()
    return thread


def _scheduler_loop(schedule_times):
    while not _stop_event.is_set():
        next_run_at = _next_run_time(datetime.now(), schedule_times)
        wait_seconds = max(1, int((next_run_at - datetime.now()).total_seconds()))
        logger.info("下一次采集时间: %s", next_run_at.isoformat(timespec="seconds"))
        if _stop_event.wait(wait_seconds):
            break
        _run_spider_with_lock("schedule", next_run_at)


def _podcast_scheduler_loop(schedule_times):
    """播客调度循环：只负责触发，不等待任务结束。

    生成任务在独立 runner 线程执行。即使 runner 因网络异常挂死，
    调度循环也能继续运行并每天输出"任务运行中"告警，避免 2026-08-08
    那种调度线程被同步阻塞 10 天、无任何日志的情况。
    """
    while not _stop_event.is_set():
        next_run_at = _next_run_time(datetime.now(), schedule_times)
        wait_seconds = max(1, int((next_run_at - datetime.now()).total_seconds()))
        logger.info("下一次每日播客生成时间: %s", next_run_at.isoformat(timespec="seconds"))
        if _stop_event.wait(wait_seconds):
            break
        _warn_if_podcast_run_stale()
        trigger_podcast_async("schedule", next_run_at)


def _warn_if_podcast_run_stale():
    """检测上一轮播客任务是否疑似挂死，超过阈值打 ERROR 告警。"""
    global _podcast_run_started_at

    started_at = _podcast_run_started_at
    if started_at is None:
        return
    elapsed = (datetime.now() - started_at).total_seconds()
    if elapsed > PODCAST_RUN_STALE_WARN_SECONDS:
        logger.error(
            "播客生成任务疑似挂死：已运行 %.0f 秒（阈值 %.0f 秒）仍未结束，"
            "本轮调度触发将被锁拒绝；如持续出现请重启服务",
            elapsed,
            PODCAST_RUN_STALE_WARN_SECONDS,
        )


def _run_spider_with_lock(reason, scheduled_time=None):
    if not _run_lock.acquire(blocking=False):
        logger.warning("已有采集任务运行中，跳过本次触发: %s", reason)
        return False

    try:
        logger.info("开始执行采集任务: %s", reason)
        from main import run_spider

        return run_spider(scheduled_time=scheduled_time)
    except Exception as e:
        logger.exception("采集任务异常: %s", e)
        return False
    finally:
        _run_lock.release()


def _run_podcast_with_lock(reason, scheduled_time=None):
    global _podcast_run_started_at

    if not _podcast_run_lock.acquire(blocking=False):
        logger.warning("已有播客生成任务运行中，跳过本次触发: %s", reason)
        return False

    try:
        _podcast_run_started_at = datetime.now()
        logger.info("开始执行每日播客生成任务: %s", reason)
        from podcast_builder import run_podcast_generation

        result = run_podcast_generation(scheduled_time=scheduled_time)
        return result.get("status") in ("success", "skipped", "disabled")
    except Exception as e:
        logger.exception("每日播客生成任务异常: %s", e)
        return False
    finally:
        _podcast_run_started_at = None
        _podcast_run_lock.release()


def _next_run_time(now, schedule_times):
    for hour, minute in schedule_times:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate

    first_hour, first_minute = schedule_times[0]
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(
        hour=first_hour,
        minute=first_minute,
        second=0,
        microsecond=0,
    )
