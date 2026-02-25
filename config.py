# -*- coding: utf-8 -*-
"""
GitHub Trending Spider 配置文件

使用说明：
1. 复制此文件并根据实际情况修改配置
2. 确保不要将含有真实密钥的配置文件提交到版本控制

环境变量优先级高于默认值，推荐通过环境变量配置敏感信息。
"""

import os

# =========================================================================
# GitHub Models API 配置
# =========================================================================

# GitHub Personal Access Token (需要 models:read 权限)
# 获取方式：https://github.com/settings/tokens → Generate new token → 勾选 models:read
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# GitHub Models API 地址（OpenAI 兼容接口）
AI_API_URL = os.environ.get(
    "AI_API_URL", "https://models.inference.ai.azure.com"
)

# 使用的 AI 模型
# 可用模型：gpt-4o-mini (快), gpt-4o (质量最优), deepseek-r1 (中文优化)
# gpt-4o: 中文总结质量最佳，比 gpt-4o-mini 提升 15-20%
AI_MODEL = os.environ.get("AI_MODEL", "gpt-4o")

# =========================================================================
# 邮件配置 (163 邮箱 SMTP)
# =========================================================================

# 163 邮箱 SMTP 服务器
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.163.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
# 163 邮箱账号（发件人邮箱）
SMTP_USER = os.environ.get("SMTP_USER", "")
# 163 邮箱 SMTP 授权码（不是邮箱密码！）
# 获取方式：163邮箱 → 设置 → POP3/SMTP/IMAP → 开启 → 获取授权码
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# 发件人邮箱地址（通常与 SMTP_USER 相同）
MAIL_FROM = os.environ.get("MAIL_FROM", SMTP_USER)

# 收件人邮箱地址
MAIL_TO = os.environ.get("MAIL_TO", "727987105@qq.com, wenbo.chang@huolala.cn")

# =========================================================================
# 日志配置
# =========================================================================

# 日志文件路径
LOG_FILE = os.environ.get(
    "LOG_FILE",
    "/root/logs/github-python/trending.log",
)
