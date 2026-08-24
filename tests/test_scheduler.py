# -*- coding: utf-8 -*-
"""
内置调度器测试。
"""

import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, ".")

import scheduler  # noqa: E402
from scheduler import parse_schedule_times  # noqa: E402


class TestScheduler(unittest.TestCase):
    def tearDown(self):
        scheduler._stop_event.clear()
        scheduler._podcast_run_started_at = None

    def test_parse_podcast_schedule_time(self):
        self.assertEqual(parse_schedule_times("02:30"), [(2, 30)])

    def test_parse_multiple_schedule_times(self):
        self.assertEqual(
            parse_schedule_times("23:50,07:50,15:50"),
            [(7, 50), (15, 50), (23, 50)],
        )

    def test_invalid_schedule_time(self):
        with self.assertRaises(ValueError):
            parse_schedule_times("25:00")

    def test_podcast_scheduler_loop_triggers_without_waiting(self):
        """调度循环只触发不等待：生成任务在独立线程跑，runner 挂死不阻塞调度。"""
        triggered = []

        def fake_trigger(reason, scheduled_time=None):
            triggered.append((reason, scheduled_time))
            scheduler._stop_event.set()  # 触发一次后结束循环
            return MagicMock()

        soon = datetime.now() + timedelta(seconds=0.05)
        with patch("scheduler._next_run_time", return_value=soon), \
                patch("scheduler.trigger_podcast_async", side_effect=fake_trigger):
            scheduler._podcast_scheduler_loop([(2, 30)])

        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0][0], "schedule")
        self.assertEqual(triggered[0][1], soon)

    def test_warn_if_podcast_run_stale_logs_error(self):
        """任务运行超过阈值仍未结束，打 ERROR 告警。"""
        scheduler._podcast_run_started_at = datetime.now() - timedelta(seconds=7201)

        with patch("scheduler.PODCAST_RUN_STALE_WARN_SECONDS", 7200), \
                patch("scheduler.logger") as logger:
            scheduler._warn_if_podcast_run_stale()

        logger.error.assert_called_once()

    def test_warn_if_podcast_run_recent_does_not_log(self):
        """任务运行时长正常时不告警。"""
        scheduler._podcast_run_started_at = datetime.now()

        with patch("scheduler.PODCAST_RUN_STALE_WARN_SECONDS", 7200), \
                patch("scheduler.logger") as logger:
            scheduler._warn_if_podcast_run_stale()

        logger.error.assert_not_called()

    def test_run_podcast_with_lock_records_started_at(self):
        """任务开始/结束时维护开始时间，供卡死检测使用。"""
        started_at_values = []

        def fake_generation(scheduled_time=None):
            started_at_values.append(scheduler._podcast_run_started_at)
            return {"status": "success"}

        with patch("scheduler._podcast_run_lock"), \
                patch("podcast_builder.run_podcast_generation", side_effect=fake_generation):
            scheduler._run_podcast_with_lock("test")

        self.assertIsNotNone(started_at_values[0])
        self.assertIsNone(scheduler._podcast_run_started_at)


if __name__ == "__main__":
    unittest.main()
