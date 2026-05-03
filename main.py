#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub + HN 热点报告 Spider 主入口

协调 GitHub Trending 爬虫、Hacker News 数据获取、AI 总结和邮件发送。
"""

import logging
import sys
import time
from datetime import datetime

from config import LOG_FILE

# ---------------------------------------------------------------------------
# 日志配置（全局初始化，其他模块通过 logging.getLogger 获取）
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("GitHub + HN 热点报告 Spider 启动 - %s", datetime.now().isoformat())
    logger.info("=" * 60)

    # 延迟导入，确保日志配置已初始化
    from github_trending import fetch_trending, ai_summarize
    from hacker_news import fetch_hn_top_stories, fetch_all_comments, ai_summarize_hn
    from email_builder import build_email_html
    from email_sender import send_email, send_failure_notify

    errors = []

    # ==========================
    # GitHub 阶段
    # ==========================
    logger.info("--- [GitHub] 开始爬取每日热点 ---")
    daily_repos = fetch_trending(since="daily")
    logger.info("每日热点: 获取到 %d 个仓库", len(daily_repos))
    if not daily_repos:
        errors.append("爬取 GitHub 每日热点失败")

    time.sleep(3)

    logger.info("--- [GitHub] 开始爬取每周热点 ---")
    weekly_repos = fetch_trending(since="weekly")
    logger.info("每周热点: 获取到 %d 个仓库", len(weekly_repos))
    if not weekly_repos:
        errors.append("爬取 GitHub 每周热点失败")

    # GitHub AI 总结
    if daily_repos:
        logger.info("--- [GitHub] AI 总结每日热点 ---")
        daily_repos = ai_summarize(daily_repos, "每日热点")
        time.sleep(5)

    if weekly_repos:
        logger.info("--- [GitHub] AI 总结每周热点 ---")
        weekly_repos = ai_summarize(weekly_repos, "每周热点")

    # ==========================
    # Hacker News 阶段
    # ==========================
    hn_stories = []
    logger.info("--- [HN] 开始获取 Top Stories ---")
    try:
        hn_stories = fetch_hn_top_stories()
        if hn_stories:
            logger.info("HN Top Stories: 获取到 %d 个帖子", len(hn_stories))

            logger.info("--- [HN] 开始获取评论 ---")
            hn_stories = fetch_all_comments(hn_stories)

            logger.info("--- [HN] AI 总结 ---")
            time.sleep(5)
            hn_stories = ai_summarize_hn(hn_stories)
        else:
            errors.append("获取 HN Top Stories 失败")
    except Exception as e:
        logger.error("HN 阶段异常: %s", e)
        errors.append("HN 阶段异常: {}".format(e))
        hn_stories = []

    # ==========================
    # 判断是否有数据
    # ==========================
    if not daily_repos and not weekly_repos and not hn_stories:
        logger.error("所有数据源均获取失败")
        send_failure_notify(
            "所有数据源均获取失败：{}".format("; ".join(errors))
        )
        sys.exit(1)

    # ==========================
    # 生成邮件并发送
    # ==========================
    logger.info("--- 生成邮件内容 ---")
    html = build_email_html(daily_repos, weekly_repos, hn_stories)

    today = datetime.now().strftime("%Y-%m-%d")
    subject = "GitHub + HN 热点报告 - {}".format(today)

    logger.info("--- 发送邮件 ---")
    success = send_email(html, subject)
    if success:
        logger.info("全部完成！")
    else:
        logger.error("邮件发送失败")
        send_failure_notify("邮件发送失败")
        sys.exit(1)

    if errors:
        logger.warning("部分数据源获取失败（已降级处理）: %s", errors)


if __name__ == "__main__":
    main()
