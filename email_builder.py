# -*- coding: utf-8 -*-
"""
HTML 邮件生成模块

负责将 GitHub Trending、Hacker News 和 TLDR AI 数据构建成 HTML 邮件内容。
"""

from datetime import datetime

from config import AI_MODEL
from content_items import (
    SOURCE_ANTHROPIC,
    SOURCE_INFOQ_AI,
    # 上游日报停止更新，暂时停用；恢复邮件板块时取消导入。
    # SOURCE_LINUX_DO,
    SOURCE_OPENAI,
)


def _escape_html(text):
    """简单的 HTML 转义。"""
    text = str(text or "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_github_table(repos):
    """构建 GitHub Trending 表格的 HTML。"""
    rows = [
        "<table>",
        "<tr>"
        "<th>#</th>"
        "<th>项目</th>"
        "<th>Stars</th>"
        "<th>AI 总结</th>"
        "</tr>",
    ]

    for i, r in enumerate(repos, 1):
        rows.append(
            "<tr>"
            "<td>{}</td>"
            '<td><a href="{}">{}</a></td>'
            '<td class="stars">{:,}</td>'
            '<td class="summary">{}</td>'
            "</tr>".format(
                i,
                r["url"],
                r["full_name"],
                r["stars"],
                _escape_html(r.get("ai_summary", "")),
            )
        )

    rows.append("</table>")
    return "\n".join(rows)


def _build_hn_table(stories):
    """构建 Hacker News 表格的 HTML。"""
    rows = [
        "<table>",
        "<tr>"
        "<th>#</th>"
        "<th>标题</th>"
        "<th>分数</th>"
        "<th>评论数</th>"
        "<th>AI 总结</th>"
        "</tr>",
    ]

    for i, s in enumerate(stories, 1):
        title = _escape_html(s.get("title", ""))
        url = s.get("url", "")
        hn_url = "https://news.ycombinator.com/item?id={}".format(s.get("id", ""))
        score = s.get("score", 0)
        comments_count = s.get("descendants", 0)
        ai_summary = _escape_html(s.get("ai_summary", ""))

        # 标题链接到原文，如果无原文 URL 则链接到 HN 讨论页
        link_url = url if url else hn_url
        title_html = '<a href="{}">{}</a>'.format(link_url, title)
        # 评论数链接到 HN 讨论页
        comments_html = '<a href="{}">{}</a>'.format(hn_url, comments_count)

        rows.append(
            "<tr>"
            "<td>{}</td>"
            "<td>{}</td>"
            '<td class="stars">{}</td>'
            '<td class="comments">{}</td>'
            '<td class="summary">{}</td>'
            "</tr>".format(
                i,
                title_html,
                score,
                comments_html,
                ai_summary,
            )
        )

    rows.append("</table>")
    return "\n".join(rows)


def _build_v2ex_table(topics):
    """构建 V2EX 热帖表格的 HTML。"""
    rows = [
        "<table>",
        "<tr>"
        "<th>#</th>"
        "<th>话题</th>"
        "<th>节点</th>"
        "<th>AI 总结</th>"
        "</tr>",
    ]

    for i, t in enumerate(topics, 1):
        url = t.get("url") or "https://www.v2ex.com/t/{}".format(t.get("id", ""))
        title = _escape_html(t.get("title", ""))
        node_title = _escape_html(t.get("node", {}).get("title", ""))
        summary = _escape_html(t.get("ai_summary", ""))
        rows.append(
            "<tr>"
            "<td>{}</td>"
            '<td><a href="{}">{}</a></td>'
            "<td>{}</td>"
            '<td class="summary">{}</td>'
            "</tr>".format(i, url, title, node_title, summary)
        )

    rows.append("</table>")
    return "\n".join(rows)


def _build_tldr_ai_table(items):
    """构建 TLDR AI 表格的 HTML。"""
    rows = [
        "<table>",
        "<tr>"
        "<th>#</th>"
        "<th>标题</th>"
        "<th>中文摘要</th>"
        "<th>原文链接</th>"
        "</tr>",
    ]

    for i, item in enumerate(items, 1):
        title = _escape_html(item.get("title", ""))
        url = _escape_html(item.get("url", ""))
        ai_summary = _escape_html(item.get("ai_summary") or item.get("summary", ""))
        category = _escape_html(item.get("category", ""))
        title_text = "{} ({})".format(title, category) if category else title

        rows.append(
            "<tr>"
            "<td>{}</td>"
            '<td><a href="{}">{}</a></td>'
            '<td class="summary">{}</td>'
            '<td><a href="{}">原文</a></td>'
            "</tr>".format(
                i,
                url,
                title_text,
                ai_summary,
                url,
            )
        )

    rows.append("</table>")
    return "\n".join(rows)


def _build_linux_do_table(items):
    """构建 Linux.do 技术日报表格。"""
    rows = [
        "<table>",
        "<tr>"
        "<th>#</th>"
        "<th>标题</th>"
        "<th>分组</th>"
        "<th>回复数</th>"
        "<th>AI 总结</th>"
        "</tr>",
    ]

    for i, item in enumerate(items, 1):
        title = _escape_html(item.get("title", ""))
        url = _escape_html(item.get("url", ""))
        meta = item.get("meta", {}) or {}
        section_title = _escape_html(meta.get("section_title", ""))
        reply_count = _escape_html(meta.get("reply_count", 0))
        summary = _escape_html(item.get("chinese_summary", ""))

        rows.append(
            "<tr>"
            "<td>{}</td>"
            '<td><a href="{}">{}</a></td>'
            "<td>{}</td>"
            '<td class="comments">{}</td>'
            '<td class="summary">{}</td>'
            "</tr>".format(
                i,
                url,
                title,
                section_title,
                reply_count,
                summary,
            )
        )

    rows.append("</table>")
    return "\n".join(rows)


def _build_content_items_table(items):
    """构建统一信息项表格。"""
    rows = [
        "<table>",
        "<tr>"
        "<th>#</th>"
        "<th>来源</th>"
        "<th>标题</th>"
        "<th>发布时间</th>"
        "<th>中文摘要</th>"
        "<th>后端关注点</th>"
        "</tr>",
    ]

    for i, item in enumerate(items, 1):
        title = _escape_html(item.get("title", ""))
        url = _escape_html(item.get("url", ""))
        source = _escape_html(item.get("source", ""))
        published_at = _escape_html(item.get("published_at", ""))
        chinese_summary = _escape_html(item.get("chinese_summary", ""))
        backend_focus = _escape_html(item.get("backend_focus", ""))

        rows.append(
            "<tr>"
            "<td>{}</td>"
            "<td>{}</td>"
            '<td><a href="{}">{}</a></td>'
            "<td>{}</td>"
            '<td class="summary">{}</td>'
            '<td class="summary">{}</td>'
            "</tr>".format(
                i,
                source,
                url,
                title,
                published_at,
                chinese_summary,
                backend_focus,
            )
        )

    rows.append("</table>")
    return "\n".join(rows)


def build_email_html(daily_repos, weekly_repos, hn_stories, v2ex_topics=None, tldr_items=None, content_items=None):
    """
    将 GitHub Trending、Hacker News、V2EX 和 TLDR AI 数据构建成完整的 HTML 邮件内容。

    Args:
        daily_repos: GitHub 每日热点仓库列表
        weekly_repos: GitHub 每周热点仓库列表
        hn_stories: Hacker News 热门帖子列表
        v2ex_topics: V2EX 技术热帖列表
        tldr_items: TLDR AI 精选内容列表
        content_items: 统一信息项列表

    Returns:
        str: 完整的 HTML 邮件内容
    """
    if v2ex_topics is None:
        v2ex_topics = []
    if tldr_items is None:
        tldr_items = []
    if content_items is None:
        content_items = []

    openai_items = [
        item for item in content_items
        if item.get("source") == SOURCE_OPENAI
    ]
    anthropic_items = [
        item for item in content_items
        if item.get("source") == SOURCE_ANTHROPIC
    ]
    engineering_items = [
        item for item in content_items
        if item.get("source") == SOURCE_INFOQ_AI
    ]
    # 上游日报停止更新，暂时停用；保留原筛选逻辑供未来恢复。
    # linux_do_items = [
    #     item for item in content_items
    #     if item.get("source") == SOURCE_LINUX_DO
    # ]

    today = datetime.now().strftime("%Y-%m-%d")
    html_parts = [
        "<!DOCTYPE html>",
        '<html><head><meta charset="utf-8">',
        "<style>",
        "  body { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; "
        "         color: #24292e; padding: 20px; max-width: 1000px; margin: 0 auto; }",
        "  h1 { color: #0366d6; border-bottom: 2px solid #e1e4e8; padding-bottom: 10px; }",
        "  h2 { color: #24292e; margin-top: 30px; }",
        "  table { border-collapse: collapse; width: 100%; margin: 15px 0; }",
        "  th { background-color: #0366d6; color: white; padding: 10px 12px; "
        "       text-align: left; font-size: 13px; }",
        "  td { padding: 10px 12px; border-bottom: 1px solid #e1e4e8; "
        "       font-size: 13px; vertical-align: top; }",
        "  tr:nth-child(even) { background-color: #f6f8fa; }",
        "  tr:hover { background-color: #f0f4f8; }",
        "  a { color: #0366d6; text-decoration: none; }",
        "  a:hover { text-decoration: underline; }",
        "  .lang { display: inline-block; padding: 2px 8px; border-radius: 12px; "
        "          background: #eff3f6; font-size: 12px; }",
        "  .stars { color: #e3b341; font-weight: bold; }",
        "  .comments { color: #6a737d; font-weight: bold; }",
        "  .period { color: #22863a; font-size: 12px; }",
        "  .summary { color: #586069; line-height: 1.5; }",
        "  .section-divider { margin-top: 40px; border-top: 3px solid #e1e4e8; "
        "                     padding-top: 10px; }",
        "  .footer { margin-top: 30px; padding-top: 15px; border-top: 1px solid #e1e4e8; "
        "            color: #6a737d; font-size: 12px; }",
        "</style>",
        "</head><body>",
        "<h1>AI 后端专项信息源报告 - {}</h1>".format(today),
    ]

    # GitHub 板块
    has_github = daily_repos or weekly_repos
    if has_github:
        html_parts.append('<div class="github-section">')
        if daily_repos:
            html_parts.append("<h2>GitHub 每日热点 (Daily)</h2>")
            html_parts.append(_build_github_table(daily_repos))
        if weekly_repos:
            html_parts.append("<h2>GitHub 每周热点 (Weekly)</h2>")
            html_parts.append(_build_github_table(weekly_repos))
        html_parts.append("</div>")

    # HN 板块
    if hn_stories:
        html_parts.append('<div class="section-divider"></div>')
        html_parts.append('<div class="hn-section">')
        html_parts.append("<h2>Hacker News Top {}</h2>".format(len(hn_stories)))
        html_parts.append(_build_hn_table(hn_stories))
        html_parts.append("</div>")

    # Linux.do 板块：上游日报停止更新，暂时停用；保留供未来恢复。
    # if linux_do_items:
    #     html_parts.append('<div class="section-divider"></div>')
    #     html_parts.append('<div class="linux-do-section">')
    #     html_parts.append("<h2>Linux.do 技术日报 Top {}</h2>".format(len(linux_do_items)))
    #     html_parts.append(_build_linux_do_table(linux_do_items))
    #     html_parts.append("</div>")

    # V2EX 板块
    if v2ex_topics:
        html_parts.append('<div class="section-divider"></div>')
        html_parts.append('<div class="v2ex-section">')
        html_parts.append("<h2>V2EX 中文技术社区热议 Top {}</h2>".format(len(v2ex_topics)))
        html_parts.append(_build_v2ex_table(v2ex_topics))
        html_parts.append("</div>")

    # TLDR AI 板块
    if tldr_items:
        html_parts.append('<div class="section-divider"></div>')
        html_parts.append('<div class="tldr-ai-section">')
        html_parts.append("<h2>TLDR AI 今日精选 Top {}</h2>".format(len(tldr_items)))
        html_parts.append(_build_tldr_ai_table(tldr_items))
        html_parts.append("</div>")

    # OpenAI 官方更新板块
    if openai_items:
        html_parts.append('<div class="section-divider"></div>')
        html_parts.append('<div class="openai-section">')
        html_parts.append("<h2>OpenAI 官方更新 Top {}</h2>".format(len(openai_items)))
        html_parts.append(_build_content_items_table(openai_items))
        html_parts.append("</div>")

    # Anthropic 官方更新板块
    if anthropic_items:
        html_parts.append('<div class="section-divider"></div>')
        html_parts.append('<div class="anthropic-section">')
        html_parts.append("<h2>Anthropic 官方更新 Top {}</h2>".format(len(anthropic_items)))
        html_parts.append(_build_content_items_table(anthropic_items))
        html_parts.append("</div>")

    # AI 工程实践板块
    if engineering_items:
        html_parts.append('<div class="section-divider"></div>')
        html_parts.append('<div class="ai-engineering-section">')
        html_parts.append(
            '<h2>InfoQ AI Development 工程实践 Top {} '
            '(<a href="https://www.infoq.com/ai-development/">页面</a>)</h2>'.format(
                len(engineering_items)
            )
        )
        html_parts.append(_build_content_items_table(engineering_items))
        html_parts.append("</div>")

    # 无数据提示
    if not has_github and not hn_stories and not tldr_items and not content_items:
        html_parts.append("<p>今日未能获取到任何热点数据，请检查网络或日志。</p>")

    # 页脚
    html_parts.extend([
        '<div class="footer">',
        "<p>此邮件由 AI 后端专项信息源 Spider 自动生成并发送。</p>",
        "<p>数据来源：<a href='https://github.com/trending'>GitHub Trending</a> "
        "| <a href='https://news.ycombinator.com/'>Hacker News</a> "
        # 上游日报停止更新，暂时停用；恢复时取消页脚链接注释。
        # "| <a href='https://news.linuxe.top/'>Linux.do 技术日报</a> "
        "| <a href='https://www.v2ex.com/'>V2EX</a> "
        "| <a href='https://ai.tldr.tech/'>TLDR AI</a> "
        "| <a href='https://openai.com/news/'>OpenAI</a> "
        "| <a href='https://www.anthropic.com/news'>Anthropic</a> "
        "| <a href='https://www.infoq.com/ai-development/'>InfoQ AI Development</a> "
        "| AI 总结：OpenRouter ({}) </p>".format(AI_MODEL),
        "</div>",
        "</body></html>",
    ])

    return "\n".join(html_parts)
