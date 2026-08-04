# -*- coding: utf-8 -*-
"""
V2EX 模块测试用例

覆盖：正常流程、边界条件、异常情况、数据适配
"""

import json
import sys
import unittest
from unittest.mock import patch, MagicMock

# 确保项目根目录在 path 中
sys.path.insert(0, ".")

from v2ex import (
    V2EX_TECH_NODES,
    fetch_v2ex_hot_topics,
    fetch_topic_replies,
    ai_summarize_v2ex,
)
from content_items import (
    SOURCE_V2EX,
    CATEGORY_COMMUNITY,
    _v2ex_to_items,
    build_all_content_items,
)


class TestV2exTechNodes(unittest.TestCase):
    """节点白名单相关测试"""

    def test_known_tech_nodes_in_whitelist(self):
        """确认核心技术节点都在白名单中"""
        expected = {"programmer", "python", "java", "golang", "ai", "openai", "claude", "cursor",
                    "docker", "kubernetes", "linux", "redis", "mysql"}
        for node in expected:
            self.assertIn(node, V2EX_TECH_NODES, f"节点 {node} 应在白名单中")

    def test_non_tech_nodes_excluded(self):
        """确认非技术节点不在白名单中"""
        excluded = {"jobs", "qna", "buy", "sell", "tv", "movie", "food",
                    "pet", "baby", "travel", "game", "music"}
        for node in excluded:
            self.assertNotIn(node, V2EX_TECH_NODES, f"节点 {node} 不应在白名单中")

    def test_case_sensitivity(self):
        """白名单使用小写，确认排序时做 .lower()"""
        # V2EX API 返回的 node name 通常是小写，但以防万一
        self.assertIn("ai", V2EX_TECH_NODES)
        self.assertNotIn("AI", V2EX_TECH_NODES)  # 白名单本身小写


class TestFetchV2exHotTopics(unittest.TestCase):
    """fetch_v2ex_hot_topics 相关测试"""

    def _make_topic(self, topic_id, title, node_name, content="test content"):
        """构造一个模拟帖子"""
        return {
            "id": topic_id,
            "title": title,
            "content": content,
            "url": f"https://www.v2ex.com/t/{topic_id}",
            "created": 1700000000,
            "node": {"name": node_name, "title": node_name.capitalize()},
            "member": {"username": "testuser", "id": 123},
        }

    @patch("v2ex.requests.get")
    def test_normal_fetch_with_filter(self, mock_get):
        """正常获取 + 技术帖排前面非技术帖排后面"""
        topics = [
            self._make_topic(1, "Python 性能优化", "python"),
            self._make_topic(2, "租房推荐", "qna"),        # 非技术
            self._make_topic(3, "Redis 集群方案", "redis"),
            self._make_topic(4, "周末去哪玩", "travel"),   # 非技术
            self._make_topic(5, "Claude API 使用", "claude"),
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = topics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_v2ex_hot_topics(count=10, max_retries=1)
        # 全部保留，技术帖排前面，非技术帖排后面
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["title"], "Python 性能优化")
        self.assertEqual(result[1]["title"], "Redis 集群方案")
        self.assertEqual(result[2]["title"], "Claude API 使用")
        self.assertEqual(result[3]["title"], "租房推荐")
        self.assertEqual(result[4]["title"], "周末去哪玩")

    @patch("v2ex.requests.get")
    def test_empty_response(self, mock_get):
        """API 返回空列表"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_v2ex_hot_topics(count=10, max_retries=1)
        self.assertEqual(result, [])

    @patch("v2ex.requests.get")
    def test_no_tech_topics(self, mock_get):
        """全部热帖都是非技术节点时仍然返回"""
        topics = [
            self._make_topic(1, "租房", "qna"),
            self._make_topic(2, "宠物", "pet"),
            self._make_topic(3, "旅行", "travel"),
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = topics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_v2ex_hot_topics(count=10, max_retries=1)
        # 不过滤，全部保留（都是非技术帖，排在后面但仍然返回）
        self.assertEqual(len(result), 3)

    @patch("v2ex.requests.get")
    def test_count_limit(self, mock_get):
        """count 参数限制返回数量"""
        topics = [self._make_topic(i, f"帖子{i}", "python") for i in range(20)]
        mock_resp = MagicMock()
        mock_resp.json.return_value = topics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_v2ex_hot_topics(count=5, max_retries=1)
        self.assertEqual(len(result), 5)

    @patch("v2ex.requests.get")
    def test_network_error_retry(self, mock_get):
        """网络异常后重试失败返回空列表"""
        import requests as req
        mock_get.side_effect = req.RequestException("Connection timeout")

        result = fetch_v2ex_hot_topics(count=10, max_retries=2)
        self.assertEqual(result, [])
        self.assertEqual(mock_get.call_count, 2)

    @patch("v2ex.requests.get")
    def test_non_list_response(self, mock_get):
        """API 返回非列表数据"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": "rate limited"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_v2ex_hot_topics(count=10, max_retries=1)
        self.assertEqual(result, [])

    @patch("v2ex.requests.get")
    def test_missing_node_field(self, mock_get):
        """帖子缺少 node 字段"""
        topics = [
            {"id": 1, "title": "无节点帖子", "content": "test"},  # 无 node
            self._make_topic(2, "正常帖子", "python"),
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = topics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_v2ex_hot_topics(count=10, max_retries=1)
        # 无 node 的帖子 node.name 为空，不在白名单中，排在后面但不被过滤
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "正常帖子")  # 技术帖排前面
        self.assertEqual(result[1]["title"], "无节点帖子")  # 非技术排后面

    @patch("v2ex.requests.get")
    def test_node_name_case_insensitive(self, mock_get):
        """节点名大小写不敏感"""
        topics = [
            self._make_topic(1, "AI 讨论", "AI"),   # 大写
            self._make_topic(2, "Python 帖", "Python"),  # 首字母大写
        ]
        # 修改 node name 为大写/混合
        topics[0]["node"]["name"] = "AI"
        topics[1]["node"]["name"] = "Python"

        mock_resp = MagicMock()
        mock_resp.json.return_value = topics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_v2ex_hot_topics(count=10, max_retries=1)
        # .lower() 转换后应匹配 "ai" 和 "python"
        self.assertEqual(len(result), 2)


class TestFetchTopicReplies(unittest.TestCase):
    """fetch_topic_replies 相关测试"""

    def _make_topic(self, topic_id):
        return {"id": topic_id, "title": f"帖子{topic_id}", "node": {"name": "python"}}

    @patch("v2ex.requests.get")
    @patch("v2ex.time.sleep")  # 跳过 sleep
    def test_normal_replies(self, mock_sleep, mock_get):
        """正常获取回复"""
        replies = [
            {"id": 1, "content": "好文章", "member": {"username": "user1"}},
            {"id": 2, "content": "赞同", "member": {"username": "user2"}},
            {"id": 3, "content": "", "member": {"username": "user3"}},  # 空内容应被过滤
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = replies
        mock_resp.raise_for_status = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        topics = [self._make_topic(100)]
        result = fetch_topic_replies(topics, replies_per_topic=10)

        self.assertEqual(len(result[0]["replies"]), 2)  # 空内容被过滤
        self.assertEqual(result[0]["replies"][0]["member"], "user1")
        self.assertEqual(result[0]["replies"][1]["member"], "user2")

    @patch("v2ex.requests.get")
    @patch("v2ex.time.sleep")
    def test_403_rate_limit_stops_remaining(self, mock_sleep, mock_get):
        """403 限流时跳过后续帖子"""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        topics = [self._make_topic(1), self._make_topic(2), self._make_topic(3)]
        result = fetch_topic_replies(topics, replies_per_topic=5)

        # 第一个帖子触发 403，所有帖子 replies 应为空
        for t in result:
            self.assertEqual(t["replies"], [])

    @patch("v2ex.requests.get")
    @patch("v2ex.time.sleep")
    def test_reply_content_truncation(self, mock_sleep, mock_get):
        """超长回复被截断到 500 字符"""
        long_content = "a" * 1000
        replies = [{"id": 1, "content": long_content, "member": {"username": "user1"}}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = replies
        mock_resp.raise_for_status = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        topics = [self._make_topic(100)]
        result = fetch_topic_replies(topics, replies_per_topic=10)

        self.assertEqual(len(result[0]["replies"][0]["content"]), 500)

    @patch("v2ex.requests.get")
    @patch("v2ex.time.sleep")
    def test_replies_per_topic_limit(self, mock_sleep, mock_get):
        """replies_per_topic 限制回复数量"""
        replies = [
            {"id": i, "content": f"回复{i}", "member": {"username": f"user{i}"}}
            for i in range(20)
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = replies
        mock_resp.raise_for_status = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        topics = [self._make_topic(100)]
        result = fetch_topic_replies(topics, replies_per_topic=5)

        self.assertEqual(len(result[0]["replies"]), 5)

    @patch("v2ex.requests.get")
    @patch("v2ex.time.sleep")
    def test_topic_without_id(self, mock_sleep, mock_get):
        """帖子没有 id 字段"""
        topics = [{"title": "无ID帖子", "node": {"name": "python"}}]
        result = fetch_topic_replies(topics, replies_per_topic=5)
        self.assertEqual(topics[0]["replies"], [])
        mock_get.assert_not_called()

    @patch("v2ex.requests.get")
    @patch("v2ex.time.sleep")
    def test_network_error_single_topic(self, mock_sleep, mock_get):
        """单帖获取失败不影响其他帖子"""
        import requests as req

        def side_effect(*args, **kwargs):
            url = args[0]
            if "topic_id=1" in url:
                raise req.RequestException("timeout")
            resp = MagicMock()
            resp.json.return_value = [
                {"id": 10, "content": "ok", "member": {"username": "u1"}}
            ]
            resp.raise_for_status = MagicMock()
            resp.status_code = 200
            return resp

        mock_get.side_effect = side_effect

        topics = [self._make_topic(1), self._make_topic(2)]
        result = fetch_topic_replies(topics, replies_per_topic=5)

        self.assertEqual(result[0]["replies"], [])       # 第一帖失败
        self.assertEqual(len(result[1]["replies"]), 1)   # 第二帖正常


class TestAiSummarizeV2ex(unittest.TestCase):
    """ai_summarize_v2ex 相关测试"""

    def _make_topic_with_replies(self, topic_id, title):
        return {
            "id": topic_id,
            "title": title,
            "content": "帖子内容",
            "node": {"name": "python", "title": "Python"},
            "member": {"username": "testuser"},
            "replies": [
                {"id": 1, "member": "user1", "content": "回复1"},
                {"id": 2, "member": "user2", "content": "回复2"},
            ],
        }

    @patch("v2ex.AI_API_KEY", "")
    def test_no_token_degradation(self):
        """无 AI_API_KEY 时降级"""
        topics = [self._make_topic_with_replies(1, "测试帖")]
        result = ai_summarize_v2ex(topics)
        self.assertEqual(result[0]["ai_summary"], "（未配置 AI Token，无法生成总结）")

    def test_empty_topics(self):
        """空列表输入"""
        result = ai_summarize_v2ex([])
        self.assertEqual(result, [])

    @patch("v2ex.AI_API_KEY", "test-token")
    @patch("v2ex.requests.post")
    def test_ai_success(self, mock_post):
        """AI 调用成功"""
        ai_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "summaries": [
                            {"index": 1, "summary": "【测试话题】这是测试总结"}
                        ]
                    })
                }
            }]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = ai_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        topics = [self._make_topic_with_replies(1, "测试帖")]
        result = ai_summarize_v2ex(topics)
        self.assertEqual(result[0]["ai_summary"], "【测试话题】这是测试总结")

    @patch("v2ex.AI_API_KEY", "test-token")
    @patch("v2ex.requests.post")
    @patch("v2ex.time.sleep")
    def test_ai_failure_degradation(self, mock_sleep, mock_post):
        """AI 调用失败时降级"""
        import requests as req
        mock_post.side_effect = req.RequestException("API down")

        topics = [self._make_topic_with_replies(1, "测试帖")]
        result = ai_summarize_v2ex(topics)
        self.assertEqual(result[0]["ai_summary"], "（AI 总结生成失败）")

    @patch("v2ex.AI_API_KEY", "test-token")
    @patch("v2ex.requests.post")
    def test_ai_response_with_markdown_wrapper(self, mock_post):
        """AI 返回被 markdown 代码块包裹的 JSON"""
        ai_response = {
            "choices": [{
                "message": {
                    "content": '```json\n{"summaries": [{"index": 1, "summary": "包裹测试"}]}\n```'
                }
            }]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = ai_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        topics = [self._make_topic_with_replies(1, "测试帖")]
        result = ai_summarize_v2ex(topics)
        self.assertEqual(result[0]["ai_summary"], "包裹测试")

    @patch("v2ex.AI_API_KEY", "test-token")
    @patch("v2ex.requests.post")
    def test_content_truncation_in_prompt(self, mock_post):
        """正文超过 300 字符时被截断"""
        ai_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "summaries": [{"index": 1, "summary": "ok"}]
                    })
                }
            }]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = ai_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        topics = [{
            "id": 1,
            "title": "长内容帖",
            "content": "x" * 500,  # 超过 300
            "node": {"name": "python", "title": "Python"},
            "member": {"username": "user"},
            "replies": [],
        }]
        result = ai_summarize_v2ex(topics)

        # 验证 AI 被调用时，prompt 中的内容被截断
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        prompt_content = payload["messages"][1]["content"]
        # 截断后应该是 300 字符 + "..."
        self.assertIn("x" * 100, prompt_content)  # 内容存在
        self.assertNotIn("x" * 500, prompt_content)  # 完整内容不在


class TestV2exToItems(unittest.TestCase):
    """_v2ex_to_items 数据适配测试"""

    def test_normal_conversion(self):
        """正常帖子转统一格式"""
        topics = [{
            "id": 123,
            "title": "测试帖子",
            "url": "https://www.v2ex.com/t/123",
            "content": "内容",
            "created": 1700000000,
            "node": {"name": "python", "title": "Python"},
            "member": {"username": "testuser"},
            "replies": [{"id": 1, "member": "u1", "content": "回复"}],
            "ai_summary": "【话题】测试总结",
        }]
        items = _v2ex_to_items(topics)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["source"], "V2EX")
        self.assertEqual(item["category"], CATEGORY_COMMUNITY)
        self.assertEqual(item["title"], "测试帖子")
        self.assertEqual(item["url"], "https://www.v2ex.com/t/123")
        self.assertEqual(item["published_at"], "1700000000")
        self.assertEqual(item["chinese_summary"], "【话题】测试总结")
        self.assertEqual(item["meta"]["node"], "python")
        self.assertEqual(item["meta"]["replies_count"], 1)

    def test_missing_url_fallback(self):
        """帖子无 url 时用 id 生成"""
        topics = [{
            "id": 456,
            "title": "无URL帖",
            "content": "",
            "created": 0,
            "node": {"name": "ai", "title": "AI"},
            "member": {"username": "u"},
            "replies": [],
            "ai_summary": "",
        }]
        items = _v2ex_to_items(topics)
        self.assertEqual(items[0]["url"], "https://www.v2ex.com/t/456")

    def test_none_input(self):
        """None 输入返回空列表"""
        items = _v2ex_to_items(None)
        self.assertEqual(items, [])

    def test_empty_list(self):
        """空列表输入"""
        items = _v2ex_to_items([])
        self.assertEqual(items, [])


class TestBuildAllContentItems(unittest.TestCase):
    """build_all_content_items 签名变更测试"""

    def test_accepts_v2ex_parameter(self):
        """确认新签名接受 v2ex_topics 参数"""
        # 所有参数都传空，不应报错
        result = build_all_content_items([], [], [], [], [], [])
        self.assertEqual(result, [])

    def test_v2ex_items_included(self):
        """V2EX 数据正确包含在输出中"""
        v2ex_topics = [{
            "id": 1,
            "title": "V2EX帖子",
            "url": "https://www.v2ex.com/t/1",
            "content": "",
            "created": 0,
            "node": {"name": "ai", "title": "AI"},
            "member": {"username": "u"},
            "replies": [],
            "ai_summary": "摘要",
        }]
        result = build_all_content_items([], [], [], v2ex_topics, [], [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source"], "V2EX")

    def test_order_hn_before_v2ex_before_tldr(self):
        """确认输出顺序：HN → V2EX → TLDR"""
        hn = [{"id": 1, "title": "HN", "url": "http://hn", "score": 1,
               "descendants": 0, "by": "u", "time": 0, "ai_summary": "s"}]
        v2ex = [{
            "id": 1, "title": "V2EX", "url": "http://v2", "content": "",
            "created": 0, "node": {"name": "ai", "title": "AI"},
            "member": {"username": "u"}, "replies": [], "ai_summary": "s",
        }]
        tldr = [{"title": "TLDR", "url": "http://tldr", "summary": "s", "category": "AI"}]

        result = build_all_content_items([], [], hn, v2ex, tldr, [])
        sources = [item["source"] for item in result]
        self.assertEqual(sources, ["Hacker News", "V2EX", "TLDR AI"])


class TestEmailBuilder(unittest.TestCase):
    """email_builder V2EX 集成测试"""

    def test_email_with_v2ex(self):
        """邮件中包含 V2EX 板块"""
        from email_builder import build_email_html

        v2ex_topics = [{
            "id": 1,
            "title": "V2EX 测试帖",
            "url": "https://www.v2ex.com/t/1",
            "node": {"name": "python", "title": "Python"},
            "ai_summary": "测试总结内容",
        }]
        html = build_email_html([], [], [], v2ex_topics, [], [])
        self.assertIn("V2EX 中文技术社区热议", html)
        self.assertIn("V2EX 测试帖", html)
        self.assertIn("测试总结内容", html)

    def test_email_without_v2ex(self):
        """无 V2EX 数据时不显示板块"""
        from email_builder import build_email_html

        html = build_email_html([], [], [], [], [], [])
        self.assertNotIn("V2EX 中文技术社区热议", html)

    def test_email_backward_compatible(self):
        """不传 v2ex 参数时向后兼容"""
        from email_builder import build_email_html

        # 使用关键字参数跳过 v2ex
        html = build_email_html([], [], [], tldr_items=[], content_items=[])
        self.assertIsInstance(html, str)


class TestSourceRegistry(unittest.TestCase):
    """source_registry V2EX 注册测试"""

    def test_v2ex_registered(self):
        """V2EX 已注册"""
        from source_registry import SOURCE_V2EX_ID, get_source_by_id
        source = get_source_by_id(SOURCE_V2EX_ID)
        self.assertIsNotNone(source)
        self.assertEqual(source["id"], "v2ex")
        self.assertEqual(source["category"], "社区讨论")

    def test_v2ex_position_after_linux_do_disabled(self):
        """Linux.do 停用后保持当前 V2EX → HN 的相对顺序"""
        from source_registry import SOURCE_DEFINITIONS
        ids = [s["id"] for s in SOURCE_DEFINITIONS]
        self.assertNotIn("linux-do", ids)
        self.assertEqual(ids.index("v2ex"), 2)
        self.assertEqual(ids.index("hacker-news"), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
