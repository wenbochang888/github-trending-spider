# -*- coding: utf-8 -*-
"""
邮件发送模块

负责 SMTP 邮件发送和失败通知。
"""

import logging
import smtplib
from datetime import datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import (
    MAIL_FROM,
    MAIL_TO,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_SERVER,
    SMTP_USER,
)

logger = logging.getLogger(__name__)


def _parse_recipients():
    """解析 MAIL_TO 配置，支持多收件人（逗号分隔）。"""
    if isinstance(MAIL_TO, str):
        return [r.strip() for r in MAIL_TO.split(",") if r.strip()]
    else:
        return MAIL_TO if isinstance(MAIL_TO, list) else [MAIL_TO]


def send_email(html_content, subject):
    """
    通过 SMTP 发送 HTML 邮件。

    Args:
        html_content: HTML 邮件正文
        subject: 邮件主题

    Returns:
        bool: 发送是否成功
    """
    recipients = _parse_recipients()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = MAIL_FROM
    msg["To"] = ", ".join(recipients)
    text_part = MIMEText("请使用支持 HTML 的邮件客户端查看此邮件。", "plain", "utf-8")
    html_part = MIMEText(html_content, "html", "utf-8")
    msg.attach(text_part)
    msg.attach(html_part)

    try:
        logger.info("正在连接 SMTP 服务器 %s:%d ...", SMTP_SERVER, SMTP_PORT)
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(MAIL_FROM, recipients, msg.as_string())
        logger.info("邮件发送成功！收件人: %s", recipients)
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP 认证失败，请检查邮箱账号和授权码")
    except smtplib.SMTPException as e:
        logger.error("SMTP 错误: %s", e)
    except Exception as e:
        logger.error("邮件发送异常: %s", e)

    return False


def send_failure_notify(error_msg):
    """当主流程失败时，发送一封简单的失败通知邮件。"""
    recipients = _parse_recipients()

    try:
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = MIMEText(
            "GitHub + HN 热点报告 Spider 运行失败\n\n"
            "时间: {}\n"
            "错误: {}\n\n"
            "请检查服务器日志: /root/logs/github-python/trending.log".format(today, error_msg),
            "plain", "utf-8"
        )
        msg["Subject"] = Header("[FAIL] GitHub + HN Spider - {}".format(today), "utf-8")
        msg["From"] = MAIL_FROM
        msg["To"] = ", ".join(recipients)

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(MAIL_FROM, recipients, msg.as_string())
        logger.info("失败通知邮件已发送")
    except Exception as e:
        logger.error("发送失败通知邮件也失败了: %s", e)
