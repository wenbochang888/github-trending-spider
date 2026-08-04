# -*- coding: utf-8 -*-
"""OpenRouter AI provider 请求与降级行为测试。"""

import json
import sys
import unittest
from unittest.mock import MagicMock, patch

import requests

sys.path.insert(0, ".")

import config  # noqa: E402
import github_trending  # noqa: E402


class TestOpenRouterAiProvider(unittest.TestCase):
    def test_ai_app_name_falls_back_when_header_value_is_not_latin1(self):
        with patch.dict("os.environ", {"AI_APP_NAME": "每日AI前沿信息"}):
            app_name = config._get_http_header_env(
                "AI_APP_NAME",
                "AI Daily Frontier",
            )

        self.assertEqual(app_name, "AI Daily Frontier")
        app_name.encode("latin-1")

    def _success_response(self):
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summaries": [
                                    {"index": 1, "summary": "迁移成功"}
                                ]
                            }
                        )
                    }
                }
            ]
        }
        return response

    def _http_error_response(self, status_code, retry_after=None):
        response = requests.Response()
        response.status_code = status_code
        if retry_after is not None:
            response.headers["Retry-After"] = str(retry_after)
        return response

    @patch("github_trending.requests.post")
    def test_openrouter_request_uses_dedicated_key_and_json_mode(self, post):
        post.return_value = self._success_response()

        with patch("github_trending.AI_API_KEY", "openrouter-key"), \
                patch("github_trending.AI_APP_NAME", "AI Daily Frontier"), \
                patch("github_trending.AI_API_URL", "https://openrouter.ai/api/v1"), \
                patch("github_trending.AI_MODEL", "deepseek/deepseek-v4-flash-0731"):
            summaries = github_trending._call_ai_api("prompt")

        self.assertEqual(summaries[0]["summary"], "迁移成功")
        _, kwargs = post.call_args
        self.assertEqual(
            post.call_args.args[0],
            "https://openrouter.ai/api/v1/chat/completions",
        )
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer openrouter-key")
        self.assertEqual(kwargs["headers"]["X-Title"], "AI Daily Frontier")
        self.assertEqual(
            kwargs["proxies"],
            {"http": "", "https": "", "all": ""},
        )
        self.assertEqual(kwargs["json"]["model"], "deepseek/deepseek-v4-flash-0731")
        self.assertEqual(kwargs["json"]["reasoning"], {"enabled": False})
        self.assertEqual(kwargs["json"]["response_format"], {"type": "json_object"})

    @patch("github_trending.time.sleep")
    @patch("github_trending.requests.post")
    def test_permanent_http_error_does_not_retry(self, post, sleep):
        response = self._http_error_response(401)
        post.return_value = response

        summaries = github_trending._call_ai_api("prompt", max_retries=5)

        self.assertIsNone(summaries)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    @patch("github_trending.time.sleep")
    @patch("github_trending.requests.post")
    def test_rate_limit_retries_and_respects_retry_after(self, post, sleep):
        post.side_effect = [
            self._http_error_response(429, retry_after=0),
            self._success_response(),
        ]

        summaries = github_trending._call_ai_api("prompt", max_retries=2)

        self.assertEqual(summaries[0]["summary"], "迁移成功")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(0.0)

    @patch("github_trending.time.sleep")
    @patch("github_trending.requests.post")
    def test_invalid_json_retries(self, post, sleep):
        invalid = self._success_response()
        invalid.json.return_value = {
            "choices": [{"message": {"content": "not-json"}}]
        }
        post.side_effect = [invalid, self._success_response()]

        summaries = github_trending._call_ai_api("prompt", max_retries=2)

        self.assertEqual(summaries[0]["summary"], "迁移成功")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(5)

    @patch("github_trending.AI_API_KEY", "")
    @patch("github_trending.requests.post")
    def test_missing_key_keeps_existing_degradation(self, post):
        repos = [{"full_name": "owner/repo"}]

        result = github_trending.ai_summarize(repos, "每日热点")

        self.assertEqual(result[0]["ai_summary"], "（未配置 AI Token，无法生成总结）")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
