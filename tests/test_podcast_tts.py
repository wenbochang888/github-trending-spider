# -*- coding: utf-8 -*-
"""
每日 AI 播客 TTS 编排测试。
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, ".")

from podcast_tts import (  # noqa: E402
    _ensure_silence_segment,
    _is_reusable_segment,
    _merge_segments,
    _merge_paths_and_timeline,
    _normalize_edge_tts_signed_value,
    _pause_after_turn,
    _probe_duration_seconds_float,
    _prepare_tts_text,
    _segment_paths_with_turn_pause,
    _sleep_before_tts_retry,
    _synthesize_edge_segment,
    merge_existing_podcast,
    synthesize_podcast,
)


class TestPodcastTts(unittest.TestCase):
    def test_synthesize_podcast_uses_role_voices_and_merges(self):
        turns = [
            {"role": "male", "text": "男声台词"},
            {"role": "female", "text": "女声台词"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("podcast_tts.PODCAST_TTS_PROVIDER", "edge_tts"), \
                    patch("podcast_tts.PODCAST_VOICE_MALE", "male-voice"), \
                    patch("podcast_tts.PODCAST_VOICE_FEMALE", "female-voice"), \
                    patch("podcast_tts.PODCAST_VOICE_MALE_RATE", "-6%"), \
                    patch("podcast_tts.PODCAST_VOICE_FEMALE_RATE", "+3%"), \
                    patch("podcast_tts.PODCAST_VOICE_MALE_PITCH", "-3Hz"), \
                    patch("podcast_tts.PODCAST_VOICE_FEMALE_PITCH", "+1Hz"), \
                    patch("podcast_tts.PODCAST_VOICE_MALE_VOLUME", "-1%"), \
                    patch("podcast_tts.PODCAST_VOICE_FEMALE_VOLUME", "+2%"), \
                    patch("podcast_tts._synthesize_edge_segment") as synthesize, \
                    patch("podcast_tts._merge_segments", return_value=([], 123)) as merge, \
                    patch("podcast_tts._probe_duration_seconds_float", return_value=1.0):
                result = synthesize_podcast(turns, temp_dir)

        self.assertEqual(result["duration_seconds"], 123)
        self.assertEqual(synthesize.call_args_list[0].args[1], "male-voice")
        self.assertEqual(synthesize.call_args_list[1].args[1], "female-voice")
        self.assertEqual(
            synthesize.call_args_list[0].kwargs,
            {"rate": "-6%", "pitch": "-3Hz", "volume": "-1%"},
        )
        self.assertEqual(
            synthesize.call_args_list[1].kwargs,
            {"rate": "+3%", "pitch": "+1Hz", "volume": "+2%"},
        )
        self.assertEqual(merge.call_count, 1)

    def test_prepare_tts_text_removes_urls_without_emptying_text(self):
        text = _prepare_tts_text("嗯，先看 [项目](https://example.com)，不过 URL 不用念 https://x.test/a")

        self.assertIn("项目", text)
        self.assertIn("不过", text)
        self.assertNotIn("https://", text)
        self.assertTrue(text.strip())

    def test_segment_paths_with_turn_pause_inserts_silence_between_turns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)
            first = target_dir / "001-male.mp3"
            second = target_dir / "002-female.mp3"

            with patch("podcast_tts.PODCAST_TURN_PAUSE_SECONDS", 0.4), \
                    patch("podcast_tts._ensure_silence_segment") as ensure_silence:
                paths = _segment_paths_with_turn_pause([first, second], target_dir)

        self.assertEqual(paths, [first, target_dir / "turn-pause.mp3", second])
        ensure_silence.assert_called_once()

    def test_merge_paths_and_timeline_uses_chapter_pause(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)
            first = target_dir / "001-male.mp3"
            second = target_dir / "002-female.mp3"

            with patch("podcast_tts.PODCAST_TURN_PAUSE_SECONDS", 0.8), \
                    patch("podcast_tts.PODCAST_CHAPTER_PAUSE_SECONDS", 1.6), \
                    patch("podcast_tts._ensure_silence_segment") as ensure_silence:
                paths, timeline, expected_duration = _merge_paths_and_timeline(
                    [
                        {
                            "index": 1,
                            "path": first,
                            "role": "male",
                            "chapter": "开场",
                            "text": "第一段。",
                            "duration_seconds": 2.0,
                        },
                        {
                            "index": 2,
                            "path": second,
                            "role": "female",
                            "chapter": "开源热榜",
                            "text": "第二段。",
                            "duration_seconds": 3.0,
                        },
                    ],
                    target_dir,
                )

        self.assertEqual(paths, [first, target_dir / "pause-1600ms.mp3", second])
        self.assertEqual(timeline[0]["start_seconds"], 0.0)
        self.assertEqual(timeline[1]["start_seconds"], 3.6)
        self.assertEqual(expected_duration, 6.6)
        ensure_silence.assert_called_once_with(target_dir / "pause-1600ms.mp3", 1.6)

    def test_silence_segment_uses_podcast_audio_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "pause-0800ms.mp3"
            with patch("podcast_tts.subprocess.run") as run:
                _ensure_silence_segment(output_path, 0.8)

        command = run.call_args.args[0]
        self.assertIn("anullsrc=r=24000:cl=mono", command)
        self.assertEqual(command[command.index("-ar") + 1], "24000")
        self.assertEqual(command[command.index("-ac") + 1], "1")
        self.assertEqual(command[command.index("-b:a") + 1], "48k")

    def test_merge_rejects_duration_mismatch_without_replacing_existing_audio(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)
            segment_path = target_dir / "001-male.mp3"
            segment_path.write_bytes(b"segment")
            output_path = target_dir / "podcast.mp3"
            output_path.write_bytes(b"existing-audio")

            def write_raw_output(command, **kwargs):
                Path(command[-1]).write_bytes(b"new-raw-audio")

            with patch(
                "podcast_tts._merge_paths_and_timeline",
                return_value=([segment_path], [], 10.0),
            ), patch("podcast_tts.shutil.which", return_value="/usr/bin/tool"), patch(
                "podcast_tts.subprocess.run",
                side_effect=write_raw_output,
            ), patch("podcast_tts._probe_duration_seconds_float", return_value=5.0):
                with self.assertRaisesRegex(RuntimeError, "时长校验失败"):
                    _merge_segments([], output_path)

            self.assertEqual(output_path.read_bytes(), b"existing-audio")
            self.assertFalse((target_dir / "podcast-raw.mp3").exists())

    def test_merge_existing_podcast_requires_every_segment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(FileNotFoundError, "001-male.mp3"):
                merge_existing_podcast(
                    [{"role": "male", "text": "已有脚本台词。"}],
                    temp_dir,
                )

    def test_merge_existing_podcast_never_calls_edge_tts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)
            segments_dir = target_dir / "segments"
            segments_dir.mkdir()
            (segments_dir / "001-male.mp3").write_bytes(b"segment")
            turns = [{"role": "male", "text": "已有语音。"}]

            with patch("podcast_tts._probe_duration_seconds_float", return_value=1.0), patch(
                "podcast_tts._merge_podcast_segments",
                return_value={"duration_seconds": 1, "turn_timeline": []},
            ), patch("podcast_tts._synthesize_edge_segment") as edge_tts:
                result = merge_existing_podcast(turns, target_dir)

            self.assertEqual(result["duration_seconds"], 1)
            edge_tts.assert_not_called()

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "需要 ffmpeg 和 ffprobe",
    )
    def test_real_merge_preserves_expected_duration_and_audio_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)
            first = target_dir / "001-male.mp3"
            second = target_dir / "002-female.mp3"
            self._create_test_tone(first, 0.8, 440)
            self._create_test_tone(second, 1.0, 660)
            first_duration = _probe_duration_seconds_float(first)
            second_duration = _probe_duration_seconds_float(second)

            with patch("podcast_tts.PODCAST_TURN_PAUSE_SECONDS", 0.8):
                _, actual_duration = _merge_segments(
                    [
                        {
                            "index": 1,
                            "path": first,
                            "role": "male",
                            "text": "第一段。",
                            "duration_seconds": first_duration,
                        },
                        {
                            "index": 2,
                            "path": second,
                            "role": "female",
                            "text": "第二段。",
                            "duration_seconds": second_duration,
                        },
                    ],
                    target_dir / "podcast.mp3",
                )

            expected_duration = first_duration + 0.8 + second_duration
            self.assertAlmostEqual(actual_duration, expected_duration, delta=0.25)
            stream_info = subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=sample_rate,channels",
                    "-of",
                    "csv=p=0",
                    str(target_dir / "podcast.mp3"),
                ],
                text=True,
            ).strip()
            self.assertEqual(stream_info, "24000,1")

    def _create_test_tone(self, path, duration_seconds, frequency):
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency={}:sample_rate=24000".format(frequency),
                "-t",
                str(duration_seconds),
                "-ar",
                "24000",
                "-ac",
                "1",
                "-acodec",
                "libmp3lame",
                "-b:a",
                "48k",
                str(path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_pause_after_turn_clamps_model_pause(self):
        with patch("podcast_tts.PODCAST_TURN_PAUSE_SECONDS", 0.8):
            small_pause = _pause_after_turn(
                {"pause_after_seconds": 0.1, "chapter": "开场", "text": "第一段。"},
                {"chapter": "开场", "text": "第二段。"},
            )
            large_pause = _pause_after_turn(
                {"pause_after_seconds": 9, "chapter": "开场", "text": "第一段。"},
                {"chapter": "开场", "text": "第二段。"},
            )

        self.assertEqual(small_pause, 0.6)
        self.assertEqual(large_pause, 2.0)

    def test_old_turns_without_metadata_use_default_pause(self):
        with patch("podcast_tts.PODCAST_TURN_PAUSE_SECONDS", 0.8):
            pause = _pause_after_turn(
                {"text": "第一段。"},
                {"text": "第二段。"},
            )

        self.assertEqual(pause, 0.8)

    def test_synthesize_edge_segment_retries_and_removes_empty_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "001-male.mp3"
            attempts = {"count": 0}

            def fail_then_succeed(text, voice, path, rate, pitch, volume):
                attempts["count"] += 1
                if attempts["count"] == 1:
                    output_path.write_bytes(b"")
                    raise RuntimeError("No audio was received")
                output_path.write_bytes(b"mp3")

            with patch("podcast_tts.PODCAST_TTS_MAX_RETRIES", 2), \
                    patch("podcast_tts.PODCAST_TTS_RETRY_SECONDS", 1), \
                    patch("podcast_tts.time.sleep") as sleep, \
                    patch("podcast_tts._synthesize_edge_segment_once", side_effect=fail_then_succeed) as synthesize:
                _synthesize_edge_segment("台词", "voice", output_path)

                self.assertEqual(output_path.read_bytes(), b"mp3")
                self.assertEqual(synthesize.call_count, 2)
                sleep.assert_called_once()

    def test_normalize_edge_tts_signed_value_adds_missing_plus_sign(self):
        self.assertEqual(_normalize_edge_tts_signed_value("0%", "%"), "+0%")
        self.assertEqual(_normalize_edge_tts_signed_value("3%", "%"), "+3%")
        self.assertEqual(_normalize_edge_tts_signed_value("-4%", "%"), "-4%")
        self.assertEqual(_normalize_edge_tts_signed_value("0Hz", "Hz"), "+0Hz")

    def test_synthesize_edge_segment_normalizes_options_before_edge_tts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "001-female.mp3"

            def write_audio(text, voice, path, rate, pitch, volume):
                path.write_bytes(b"mp3")

            with patch("podcast_tts._synthesize_edge_segment_once", side_effect=write_audio) as synthesize:
                _synthesize_edge_segment(
                    "台词",
                    "voice",
                    output_path,
                    rate="0%",
                    pitch="0Hz",
                    volume="0%",
                )

        self.assertEqual(synthesize.call_args.args[3], "+0%")
        self.assertEqual(synthesize.call_args.args[4], "+0Hz")
        self.assertEqual(synthesize.call_args.args[5], "+0%")

    def test_empty_turns_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                synthesize_podcast([], temp_dir)

    def test_synthesize_podcast_reuses_existing_segments(self):
        """断点续传：已存在且有效的片段直接复用，只补缺失片段。"""
        turns = [
            {"role": "male", "text": "已有片段的台词"},
            {"role": "female", "text": "缺失片段的台词"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_dir = Path(temp_dir) / "segments"
            segments_dir.mkdir()
            (segments_dir / "001-male.mp3").write_bytes(b"existing-mp3")

            with patch("podcast_tts.PODCAST_TTS_PROVIDER", "edge_tts"), \
                    patch("podcast_tts._synthesize_edge_segment") as synthesize, \
                    patch("podcast_tts._merge_segments", return_value=([], 123)), \
                    patch("podcast_tts._probe_duration_seconds_float", return_value=1.0):
                result = synthesize_podcast(turns, temp_dir)

        self.assertEqual(result["duration_seconds"], 123)
        synthesize.assert_called_once()
        self.assertIn("002-female.mp3", str(synthesize.call_args.args[2]))

    def test_is_reusable_segment_rejects_empty_or_unreadable_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)
            empty_path = target_dir / "001-male.mp3"
            empty_path.write_bytes(b"")
            broken_path = target_dir / "002-female.mp3"
            broken_path.write_bytes(b"not-audio")

            with patch(
                "podcast_tts._probe_duration_seconds_float",
                side_effect=lambda path: 0.0 if path == broken_path else 1.5,
            ):
                self.assertFalse(_is_reusable_segment(empty_path))
                self.assertFalse(_is_reusable_segment(broken_path))
                self.assertFalse(_is_reusable_segment(target_dir / "003-male.mp3"))
                valid_path = target_dir / "004-female.mp3"
                valid_path.write_bytes(b"mp3")
                self.assertTrue(_is_reusable_segment(valid_path))

    def test_tts_retry_backoff_is_exponential_with_cap(self):
        """单段重试指数退避：3s/6s/12s/24s/48s...，上限 60s。"""
        sleeps = []

        with patch("podcast_tts.PODCAST_TTS_RETRY_SECONDS", 3), \
                patch("podcast_tts.time.sleep", side_effect=sleeps.append):
            for attempt in range(1, 8):
                _sleep_before_tts_retry(attempt)

        self.assertEqual(sleeps, [3, 6, 12, 24, 48, 60, 60])

    def test_subprocess_calls_have_timeout(self):
        """ffprobe / ffmpeg 子进程调用必须带超时，防止本地工具挂起阻塞任务。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "pause-0800ms.mp3"
            with patch("podcast_tts.subprocess.run") as run:
                _ensure_silence_segment(output_path, 0.8)

            self.assertIn("timeout", run.call_args.kwargs)
            self.assertGreater(run.call_args.kwargs["timeout"], 0)


if __name__ == "__main__":
    unittest.main()
