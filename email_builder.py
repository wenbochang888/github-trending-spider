# -*- coding: utf-8 -*-
"""
HTML 邮件生成模块

负责将 GitHub Trending 和 Hacker News 数据构建成 HTML 邮件内容。
"""

from datetime import datetime

from config import AI_MODEL


def _escape_html(text):
    """简单的 HTML 转义。"""
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


def build_email_html(daily_repos, weekly_repos, hn_stories):
    """
    将 GitHub Trending 和 Hacker News 数据构建成完整的 HTML 邮件内容。

    Args:
        daily_repos: GitHub 每日热点仓库列表
        weekly_repos: GitHub 每周热点仓库列表
        hn_stories: Hacker News 热门帖子列表

    Returns:
        str: 完整的 HTML 邮件内容
    """
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
        "<h1>GitHub + HN 热点报告 - {}</h1>".format(today),
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

    # 无数据提示
    if not has_github and not hn_stories:
        html_parts.append("<p>今日未能获取到任何热点数据，请检查网络或日志。</p>")

    # 页脚
    html_parts.extend([
        '<div class="footer">',
        "<p>此邮件由 GitHub + HN 热点报告 Spider 自动生成并发送。</p>",
        "<p>数据来源：<a href='https://github.com/trending'>GitHub Trending</a> "
        "| <a href='https://news.ycombinator.com/'>Hacker News</a> "
        "| AI 总结：GitHub Models ({}) </p>".format(AI_MODEL),
        "</div>",
        "</body></html>",
    ])

    return "\n".join(html_parts)
