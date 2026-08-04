# -*- coding: utf-8 -*-
"""
每日 AI 播客生成编排测试。
"""

import json
import requests
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, ".")

from podcast_builder import (  # noqa: E402
    build_podcast_script,
    build_timed_chapters,
    _build_script_prompt,
    _call_script_ai_api,
    _normalize_script_payload,
    load_podcast_source_snapshots,
    resolve_target_content_date,
    rebuild_podcast_audio,
    run_podcast_generation,
)
from podcast_store import (  # noqa: E402
    load_latest_podcast_metadata,
    load_podcast_metadata,
    write_podcast_metadata,
    write_podcast_script,
)


class TestPodcastBuilder(unittest.TestCase):
    def _write_archive(self, root, source_id="github-daily", date_text="2026-07-19"):
        target_dir = Path(root) / source_id / date_text
        target_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": "{}T23:50:00".format(date_text),
            "source": {"id": source_id, "label": "GitHub 日榜"},
            "item_count": 1,
            "items": [
                {
                    "title": "AI infra project",
                    "url": "https://example.com/ai",
                    "chinese_summary": "一个 AI 基础设施项目。",
                    "backend_focus": "关注队列、缓存和可观测性。",
                }
            ],
        }
        with (target_dir / "01.json").open("w", encoding="utf-8") as f:
            json.dump(payload, f)

    def test_target_content_date_uses_yesterday(self):
        run_at = datetime(2026, 7, 20, 2, 30, 0)

        self.assertEqual(resolve_target_content_date(run_at), "2026-07-19")

    def test_existing_success_metadata_skips_generation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            write_podcast_metadata(
                {
                    "date": "2026-07-19",
                    "title": "done",
                    "audio_url": "/api/podcasts/2026-07-19/podcast.mp3",
                    "duration_seconds": 1,
                    "generated_at": "2026-07-20T02:30:00",
                    "source_count": 1,
                    "item_count": 1,
                    "status": "success",
                    "error": "",
                    "chapters": [],
                },
                output_dir=temp_dir,
            )

            with patch("podcast_builder.PODCAST_ENABLED", True):
                result = run_podcast_generation(
                    scheduled_time=datetime(2026, 7, 20, 2, 30, 0),
                    output_dir=temp_dir,
                )

            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "already-success")

    def test_no_archive_writes_failed_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("podcast_builder.PODCAST_ENABLED", True):
                result = run_podcast_generation(
                    scheduled_time=datetime(2026, 7, 20, 2, 30, 0),
                    output_dir=temp_dir,
                )

            metadata = load_podcast_metadata("2026-07-19", output_dir=temp_dir)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(metadata["status"], "failed")
            self.assertEqual(metadata["item_count"], 0)

    def test_load_source_snapshots_excludes_configured_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write_archive(temp_dir, source_id="github-daily")
            self._write_archive(temp_dir, source_id="tldr-ai")
            self._write_archive(temp_dir, source_id="infoq")

            snapshots = load_podcast_source_snapshots("2026-07-19", output_dir=temp_dir)

            source_ids = [snapshot["source"]["id"] for snapshot in snapshots]
            self.assertIn("github-daily", source_ids)
            self.assertNotIn("tldr-ai", source_ids)
            self.assertNotIn("infoq", source_ids)

    def test_successful_generation_writes_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write_archive(temp_dir)
            script = {
                "title": "2026-07-19 AI 音频日报",
                "summary": "今天的热点集中在 AI 基础设施、开发工具和官方模型更新。",
                "chapters": [{"time": "00:00", "title": "今日主线"}],
                "turns": [
                    {"role": "male", "text": "今天先看开源热榜。"},
                    {"role": "female", "text": "这个项目和后端工程很相关。"},
                ],
            }

            with patch("podcast_builder.PODCAST_ENABLED", True), \
                    patch("podcast_builder.PODCAST_MIN_TURN_COUNT", 1), \
                    patch("podcast_builder.PODCAST_MIN_SCRIPT_CHARS", 1), \
                    patch("podcast_builder.build_podcast_script", return_value=script), \
                    patch("podcast_builder.synthesize_podcast", return_value={"duration_seconds": 123}):
                result = run_podcast_generation(
                    scheduled_time=datetime(2026, 7, 20, 2, 30, 0),
                    output_dir=temp_dir,
                )

            metadata = load_podcast_metadata("2026-07-19", output_dir=temp_dir)
            self.assertEqual(result["status"], "success")
            self.assertEqual(metadata["status"], "success")
            self.assertEqual(metadata["summary"], "今天的热点集中在 AI 基础设施、开发工具和官方模型更新。")
            self.assertEqual(metadata["duration_seconds"], 123)
            self.assertEqual(metadata["source_count"], 1)
            self.assertEqual(metadata["item_count"], 1)

    def test_normalize_script_payload_accepts_missing_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write_archive(temp_dir)
            script = {
                "title": "2026-07-19 AI 音频日报",
                "chapters": [{"time": "00:00", "title": "今日主线"}],
                "turns": [
                    {"role": "male", "text": "今天先看开源热榜。"},
                    {"role": "female", "text": "这个项目和后端工程很相关。"},
                ],
            }

            with patch("podcast_builder.PODCAST_ENABLED", True), \
                    patch("podcast_builder.PODCAST_MIN_TURN_COUNT", 1), \
                    patch("podcast_builder.PODCAST_MIN_SCRIPT_CHARS", 1), \
                    patch("podcast_builder.build_podcast_script", return_value=script), \
                    patch("podcast_builder.synthesize_podcast", return_value={"duration_seconds": 123}):
                result = run_podcast_generation(
                    scheduled_time=datetime(2026, 7, 20, 2, 30, 0),
                    output_dir=temp_dir,
                )

            metadata = load_podcast_metadata("2026-07-19", output_dir=temp_dir)
            self.assertEqual(result["status"], "success")
            self.assertEqual(metadata["summary"], "")

    def test_generation_reuses_existing_valid_script(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write_archive(temp_dir)
            script = {
                "title": "已生成脚本",
                "summary": "已有脚本可以复用。",
                "chapters": [{"time": "00:00", "title": "今日主线"}],
                "turns": [
                    {"role": "male", "text": "直接复用这一段。"},
                    {"role": "female", "text": "不用重新请求模型。"},
                ],
            }
            write_podcast_script("2026-07-19", script, output_dir=temp_dir)

            with patch("podcast_builder.PODCAST_ENABLED", True), \
                    patch("podcast_builder.build_podcast_script", side_effect=AssertionError("should not call AI")), \
                    patch("podcast_builder.synthesize_podcast", return_value={"duration_seconds": 123}):
                result = run_podcast_generation(
                    scheduled_time=datetime(2026, 7, 20, 2, 30, 0),
                    output_dir=temp_dir,
                )

            metadata = load_podcast_metadata("2026-07-19", output_dir=temp_dir)
            self.assertEqual(result["status"], "success")
            self.assertEqual(metadata["title"], "已生成脚本")
            self.assertEqual(metadata["summary"], "已有脚本可以复用。")

    def test_rebuild_podcast_audio_reuses_segments_and_updates_current_latest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            date_text = "2026-07-19"
            script = {
                "title": "已有脚本",
                "summary": "不重新生成脚本。",
                "chapters": [{"time": "00:00", "title": "片头"}],
                "turns": [{"role": "male", "chapter": "片头", "text": "完整台词。"}],
            }
            write_podcast_script(date_text, script, output_dir=temp_dir)
            write_podcast_metadata(
                {
                    "date": date_text,
                    "title": "原有标题",
                    "summary": "原有摘要",
                    "audio_url": "/api/podcasts/{}/podcast.mp3".format(date_text),
                    "duration_seconds": 115,
                    "generated_at": "2026-07-20T02:30:00",
                    "source_count": 6,
                    "item_count": 48,
                    "status": "success",
                    "error": "",
                    "chapters": [],
                },
                output_dir=temp_dir,
            )

            with patch(
                "podcast_builder.merge_existing_podcast",
                return_value={
                    "duration_seconds": 225,
                    "turn_timeline": [{"chapter": "片头", "start_seconds": 0}],
                },
            ) as merge, patch(
                "podcast_builder.build_podcast_script",
                side_effect=AssertionError("should not call AI"),
            ):
                result = rebuild_podcast_audio(date_text, output_dir=temp_dir)

            metadata = load_podcast_metadata(date_text, output_dir=temp_dir)
            self.assertEqual(result["status"], "success")
            self.assertEqual(metadata["duration_seconds"], 225)
            self.assertEqual(metadata["title"], "原有标题")
            self.assertEqual(metadata["summary"], "原有摘要")
            self.assertEqual(metadata["source_count"], 6)
            self.assertEqual(metadata["item_count"], 48)
            self.assertEqual(
                load_latest_podcast_metadata(output_dir=temp_dir)["duration_seconds"],
                225,
            )
            merge.assert_called_once()

    def test_rebuild_old_date_does_not_replace_newer_latest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_date = "2026-07-19"
            new_date = "2026-07-20"
            for date_text in (old_date, new_date):
                write_podcast_script(
                    date_text,
                    {"turns": [{"role": "male", "text": "完整台词。"}]},
                    output_dir=temp_dir,
                )
                write_podcast_metadata(
                    {
                        "date": date_text,
                        "title": date_text,
                        "audio_url": "/api/podcasts/{}/podcast.mp3".format(date_text),
                        "duration_seconds": 115,
                        "generated_at": "2026-07-21T02:30:00",
                        "source_count": 1,
                        "item_count": 1,
                        "status": "success",
                        "error": "",
                        "chapters": [],
                    },
                    output_dir=temp_dir,
                )

            with patch(
                "podcast_builder.merge_existing_podcast",
                return_value={"duration_seconds": 225, "turn_timeline": []},
            ):
                result = rebuild_podcast_audio(old_date, output_dir=temp_dir)

            self.assertEqual(result["status"], "success")
            self.assertEqual(load_latest_podcast_metadata(output_dir=temp_dir)["date"], new_date)

    def test_rebuild_rejects_metadata_for_different_date(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            date_text = "2026-07-19"
            target_dir = Path(temp_dir) / "podcasts" / date_text
            target_dir.mkdir(parents=True)
            with (target_dir / "metadata.json").open("w", encoding="utf-8") as f:
                json.dump({"date": "2026-07-18", "status": "success"}, f)

            with patch("podcast_builder.merge_existing_podcast") as merge:
                result = rebuild_podcast_audio(date_text, output_dir=temp_dir)

            self.assertEqual(result["status"], "failed")
            self.assertIn("日期", result["error"])
            merge.assert_not_called()

    def test_rebuild_failure_preserves_success_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            date_text = "2026-07-19"
            write_podcast_script(
                date_text,
                {"turns": [{"role": "male", "text": "完整台词。"}]},
                output_dir=temp_dir,
            )
            original = {
                "date": date_text,
                "title": "原有标题",
                "audio_url": "/api/podcasts/{}/podcast.mp3".format(date_text),
                "duration_seconds": 115,
                "generated_at": "2026-07-20T02:30:00",
                "source_count": 6,
                "item_count": 48,
                "status": "success",
                "error": "",
                "chapters": [],
            }
            write_podcast_metadata(original, output_dir=temp_dir)

            with patch(
                "podcast_builder.merge_existing_podcast",
                side_effect=FileNotFoundError("missing segment"),
            ):
                result = rebuild_podcast_audio(date_text, output_dir=temp_dir)

            self.assertEqual(result["status"], "failed")
            self.assertEqual(
                load_podcast_metadata(date_text, output_dir=temp_dir),
                original,
            )

    def test_metadata_write_failure_restores_original_audio_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            date_text = "2026-07-19"
            write_podcast_script(
                date_text,
                {"turns": [{"role": "male", "text": "完整台词。"}]},
                output_dir=temp_dir,
            )
            original = {
                "date": date_text,
                "title": "原有标题",
                "audio_url": "/api/podcasts/{}/podcast.mp3".format(date_text),
                "duration_seconds": 115,
                "generated_at": "2026-07-20T02:30:00",
                "source_count": 6,
                "item_count": 48,
                "status": "success",
                "error": "",
                "chapters": [],
            }
            write_podcast_metadata(original, output_dir=temp_dir)
            audio_path = Path(temp_dir) / "podcasts" / date_text / "podcast.mp3"
            audio_path.write_bytes(b"old-audio")

            def replace_audio(_turns, target_dir):
                (Path(target_dir) / "podcast.mp3").write_bytes(b"new-audio")
                return {"duration_seconds": 225, "turn_timeline": []}

            with patch(
                "podcast_builder.merge_existing_podcast",
                side_effect=replace_audio,
            ), patch(
                "podcast_builder.write_podcast_metadata",
                side_effect=RuntimeError("metadata write failed"),
            ):
                result = rebuild_podcast_audio(date_text, output_dir=temp_dir)

            self.assertEqual(result["status"], "failed")
            self.assertEqual(audio_path.read_bytes(), b"old-audio")
            self.assertEqual(load_podcast_metadata(date_text, output_dir=temp_dir), original)

    def test_rebuild_podcast_audio_respects_existing_lock(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            date_text = "2026-07-19"
            write_podcast_script(
                date_text,
                {"turns": [{"role": "male", "text": "完整台词。"}]},
                output_dir=temp_dir,
            )
            write_podcast_metadata(
                {
                    "date": date_text,
                    "title": "原有标题",
                    "audio_url": "/api/podcasts/{}/podcast.mp3".format(date_text),
                    "duration_seconds": 115,
                    "generated_at": "2026-07-20T02:30:00",
                    "source_count": 6,
                    "item_count": 48,
                    "status": "success",
                    "error": "",
                    "chapters": [],
                },
                output_dir=temp_dir,
            )

            with patch("podcast_builder.acquire_podcast_lock", return_value=False), patch(
                "podcast_builder.merge_existing_podcast",
            ) as merge:
                result = rebuild_podcast_audio(date_text, output_dir=temp_dir)

            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "locked")
            merge.assert_not_called()

    def test_normalize_script_payload_filters_invalid_turns(self):
        payload = {
            "turns": [
                {"role": "male", "text": "这条可以保留。"},
                {"role": "narrator", "text": "这个角色不支持。"},
                {"role": "female", "text": "   "},
            ],
        }

        script = _normalize_script_payload("2026-07-19", payload)

        self.assertEqual(script["turns"], [{"role": "male", "text": "这条可以保留。"}])

    def test_script_prompt_guides_natural_conversation(self):
        snapshots = [
            {
                "source": {"label": "GitHub 日榜"},
                "items": [
                    {
                        "title": "AI infra project",
                        "url": "https://example.com/ai",
                        "chinese_summary": "一个 AI 基础设施项目。",
                        "backend_focus": "关注队列、缓存和可观测性。",
                    }
                ],
            }
        ]

        prompt = _build_script_prompt("2026-07-19", snapshots)

        self.assertIn("真实节目", prompt)
        self.assertIn("4 到 8 分钟", prompt)
        self.assertIn("35 到 50 轮", prompt)
        self.assertIn("pause_after_seconds", prompt)
        self.assertIn("chapter 必须等于所属章节标题", prompt)
        self.assertIn("每个 turns 元素只写一个角色的一小轮话", prompt)
        self.assertIn("不要使用模板化播报腔", prompt)
        self.assertIn("不要朗读 URL", prompt)

    def test_normalize_script_payload_keeps_chapter_and_pause_metadata(self):
        payload = {
            "turns": [
                {
                    "role": "male",
                    "chapter": "开源热榜",
                    "pause_after_seconds": "1.1",
                    "text": "这条可以保留。",
                }
            ],
        }

        script = _normalize_script_payload("2026-07-19", payload)

        self.assertEqual(
            script["turns"],
            [
                {
                    "role": "male",
                    "text": "这条可以保留。",
                    "chapter": "开源热榜",
                    "pause_after_seconds": 1.1,
                }
            ],
        )

    def test_build_timed_chapters_uses_tts_timeline(self):
        chapters = [
            {"time": "00:00", "title": "开场"},
            {"time": "07:00", "title": "开源热榜"},
        ]
        timeline = [
            {"chapter": "开场", "start_seconds": 0},
            {"chapter": "开源热榜", "start_seconds": 92.4},
        ]

        timed_chapters = build_timed_chapters(chapters, timeline, 123)

        self.assertEqual(
            timed_chapters,
            [
                {"time": "00:00", "title": "开场"},
                {"time": "01:32", "title": "开源热榜"},
            ],
        )

    def test_build_timed_chapters_caps_missing_chapter_to_duration(self):
        chapters = [
            {"time": "00:00", "title": "开场"},
            {"time": "07:00", "title": "行动建议"},
        ]

        timed_chapters = build_timed_chapters(chapters, [], 100)

        self.assertEqual(timed_chapters[-1], {"time": "00:50", "title": "行动建议"})

    def test_generation_retries_low_quality_new_script_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write_archive(temp_dir)
            short_script = {
                "title": "短脚本",
                "summary": "太短。",
                "chapters": [{"time": "00:00", "title": "今日主线"}],
                "turns": [{"role": "male", "text": "太短。"}],
            }
            better_script = {
                "title": "更完整脚本",
                "summary": "重试后更完整。",
                "chapters": [{"time": "00:00", "title": "今日主线"}],
                "turns": [
                    {"role": "male", "chapter": "今日主线", "text": "第一段足够长。"},
                    {"role": "female", "chapter": "今日主线", "text": "第二段也足够长。"},
                ],
            }

            with patch("podcast_builder.PODCAST_ENABLED", True), \
                    patch("podcast_builder.PODCAST_MIN_TURN_COUNT", 2), \
                    patch("podcast_builder.PODCAST_MIN_SCRIPT_CHARS", 10), \
                    patch(
                        "podcast_builder.build_podcast_script",
                        side_effect=[short_script, better_script],
                    ) as build_script, \
                    patch(
                        "podcast_builder.synthesize_podcast",
                        return_value={
                            "duration_seconds": 240,
                            "turn_timeline": [{"chapter": "今日主线", "start_seconds": 0}],
                        },
                    ):
                result = run_podcast_generation(
                    scheduled_time=datetime(2026, 7, 20, 2, 30, 0),
                    output_dir=temp_dir,
                )

            metadata = load_podcast_metadata("2026-07-19", output_dir=temp_dir)
            self.assertEqual(result["status"], "success")
            self.assertEqual(metadata["title"], "更完整脚本")
            self.assertEqual(build_script.call_count, 2)

    def test_call_script_ai_api_retries_transient_ssl_error(self):
        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "turns": [
                                            {"role": "male", "text": "重试后成功。"}
                                        ]
                                    }
                                )
                            }
                        }
                    ]
                }

        with patch("podcast_builder.AI_API_KEY", "openrouter-key"), \
                patch("podcast_builder.AI_APP_NAME", "AI Daily Frontier"), \
                patch("podcast_builder.PODCAST_SCRIPT_MODEL", "deepseek/deepseek-v4-flash-0731"), \
                patch("podcast_builder.PODCAST_SCRIPT_MAX_RETRIES", 2), \
                patch("podcast_builder.PODCAST_SCRIPT_RETRY_SECONDS", 1), \
                patch("podcast_builder.time.sleep") as sleep, \
                patch(
                    "podcast_builder.requests.post",
                    side_effect=[
                        requests.exceptions.SSLError("ssl eof"),
                        FakeResponse(),
                    ],
                ) as post:
            payload = _call_script_ai_api("prompt")

        self.assertEqual(payload["turns"][0]["text"], "重试后成功。")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once()
        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer openrouter-key")
        self.assertEqual(kwargs["headers"]["X-Title"], "AI Daily Frontier")
        self.assertEqual(
            kwargs["proxies"],
            {"http": "", "https": "", "all": ""},
        )
        self.assertEqual(kwargs["json"]["model"], "deepseek/deepseek-v4-flash-0731")
        self.assertEqual(kwargs["json"]["reasoning"], {"enabled": False})
        self.assertEqual(kwargs["json"]["response_format"], {"type": "json_object"})

    def test_build_podcast_script_rejects_retired_provider(self):
        with patch("podcast_builder.PODCAST_SCRIPT_PROVIDER", "github_models"), \
                self.assertRaisesRegex(ValueError, "暂不支持"):
            build_podcast_script("2026-08-05", [])

    def test_build_podcast_script_requires_ai_api_key(self):
        with patch("podcast_builder.PODCAST_SCRIPT_PROVIDER", "openrouter"), \
                patch("podcast_builder.AI_API_KEY", ""), \
                self.assertRaisesRegex(RuntimeError, "AI_API_KEY"):
            build_podcast_script("2026-08-05", [])

    def test_call_script_ai_api_does_not_retry_permanent_error(self):
        response = requests.Response()
        response.status_code = 402

        with patch("podcast_builder.PODCAST_SCRIPT_MAX_RETRIES", 5), \
                patch("podcast_builder.time.sleep") as sleep, \
                patch("podcast_builder.requests.post", return_value=response) as post, \
                self.assertRaises(requests.exceptions.HTTPError):
            _call_script_ai_api("prompt")

        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_call_script_ai_api_respects_retry_after(self):
        limited = requests.Response()
        limited.status_code = 429
        limited.headers["Retry-After"] = "1.5"

        success = MagicMock()
        success.status_code = 200
        success.raise_for_status.return_value = None
        success.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"turns": [{"role": "male", "text": "成功"}]}
                        )
                    }
                }
            ]
        }

        with patch("podcast_builder.PODCAST_SCRIPT_MAX_RETRIES", 2), \
                patch("podcast_builder.time.sleep") as sleep, \
                patch(
                    "podcast_builder.requests.post",
                    side_effect=[limited, success],
                ) as post:
            payload = _call_script_ai_api("prompt")

        self.assertEqual(payload["turns"][0]["text"], "成功")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1.5)


if __name__ == "__main__":
    unittest.main()
