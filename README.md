# GitHub Trending Spider

每日自动爬取 GitHub Trending 热点项目，通过 AI 生成中文总结，邮件推送到指定邮箱。

## 功能

- 爬取 GitHub Trending **每日热点** 和 **每周热点**
- 通过 GitHub Models API (GPT-4o-mini) 生成中文总结
- 生成精美 HTML 表格邮件，包含项目信息和 AI 分析
- 支持 crontab 定时执行

## 环境要求

- Python 3.6+（已测试 Python 3.8）
- Linux 服务器（CentOS / Ubuntu 等）
- GitHub 账号（用于 GitHub Models API）
- 163 邮箱（用于 SMTP 发送邮件）

## 快速部署

### 1. 安装依赖

```bash
cd /path/to/github-trending-spider
pip3 install -r requirements.txt
```

### 2. 获取 GitHub Personal Access Token

1. 访问 https://github.com/settings/tokens
2. 点击 **Generate new token (classic)**
3. 勾选 `models:read` 权限
4. 生成并复制 token

### 3. 配置环境变量

```bash
cp .env.example .env
vim .env  # 填入你的 GITHUB_TOKEN 和 SMTP_PASSWORD
source .env
```

`.env.example` 中已预设了发件人和收件人邮箱，你只需填入两个密钥：

| 变量 | 说明 |
|------|------|
| `GITHUB_TOKEN` | GitHub PAT，需 `models:read` 权限 |
| `SMTP_PASSWORD` | 163 邮箱 SMTP 授权码 |

### 5. 手动测试

```bash
python3 github_trending.py
```

如果一切正常，你的邮箱会收到一封 GitHub Trending 热点报告邮件。

### 6. 配置 Crontab 定时任务

```bash
crontab -e
```

添加以下内容（每天早上 8:00 执行）：

```bash
# 方式一：使用 source 加载 .env（推荐）
0 8 * * * cd /path/to/github-trending-spider && source .env && /usr/bin/python3 github_trending.py >> cron.log 2>&1
```

或直接在 crontab 中内联环境变量：

```bash
0 8 * * * cd /path/to/github-trending-spider && GITHUB_TOKEN="ghp_xxx" SMTP_USER="changwenbo141@163.com" SMTP_PASSWORD="xxx" MAIL_TO="727987105@qq.com" /usr/bin/python3 github_trending.py >> cron.log 2>&1
```

## 文件结构

```
github-trending-spider/
├── github_trending.py   # 主脚本
├── config.py            # 配置文件（从环境变量读取，已 gitignore）
├── .env.example         # 环境变量模板
├── .env                 # 实际环境变量（已 gitignore，需自行创建）
├── requirements.txt     # Python 依赖
├── .gitignore           # Git 忽略规则
└── README.md            # 本文件

## 邮件效果

邮件包含两个表格：

| 分类 | 内容 |
|------|------|
| 📅 每日热点 | 当天 GitHub 上最热门的项目 |
| 📆 每周热点 | 本周 GitHub 上最热门的项目 |

每个表格包含以下列：

| 列 | 说明 |
|----|------|
| # | 序号 |
| 项目 | 项目名称（可点击跳转）+ 简短描述 |
| 语言 | 编程语言 |
| ⭐ Stars | 总 star 数 |
| 🍴 Forks | 总 fork 数 |
| 📈 新增 | 当天/本周新增 star 数 |
| 📝 AI 总结 | AI 生成的中文项目分析 |

## GitHub Models API 免费额度

| 模型 | 每日请求数 | 每请求 Token |
|------|-----------|-------------|
| gpt-4o-mini (Low tier) | 150 次/天 | 8000 in, 4000 out |
| gpt-4o (High tier) | 50 次/天 | 8000 in, 4000 out |

本脚本默认使用 `gpt-4o-mini`，每次运行只需 2 次 API 调用（每日+每周各一次），免费额度完全足够。

## 故障排查

1. **邮件发送失败**：检查 163 邮箱 SMTP 授权码是否正确，是否开启了 SMTP 服务
2. **AI 总结为空**：检查 GITHUB_TOKEN 是否有效，是否有 `models:read` 权限
3. **爬取失败**：检查服务器网络是否能访问 github.com
4. **查看日志**：`cat trending.log`
