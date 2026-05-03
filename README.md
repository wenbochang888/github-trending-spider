# GitHub + HN 热点报告 Spider

每日自动爬取 GitHub Trending 热点项目和 Hacker News Top 10 热门帖子，通过 AI 生成中文总结，合并为一封 HTML 邮件推送到指定邮箱。

## 功能

- 爬取 GitHub Trending **每日热点** 和 **每周热点** (各 Top 5)
- 爬取 **Hacker News Top 10** 热门帖子及评论 (通过官方 Firebase API)
- 通过 GitHub Models API (GPT-4o) 生成中文总结
- GitHub 总结：项目功能、特点、适用场景
- HN 总结：帖子主题 + 评论区核心观点/争议点
- 生成 HTML 表格邮件，支持多收件人
- GitHub 和 HN 独立容错，任一成功即发送邮件
- 支持 crontab 定时执行

## 部署

### 1. 克隆 & 安装

```bash
git clone https://github.com/wenbochang888/github-trending-spider.git
cd github-trending-spider
pip3 install -r requirements.txt
```

### 2. 配置环境变量

编辑 `~/.bash_profile`，在末尾追加：

```bash
# GitHub + HN Spider
export GITHUB_TOKEN="ghp_你的token"
export SMTP_USER="changwenbo141@163.com"
export SMTP_PASSWORD="你的163授权码"
export MAIL_TO="727987105@qq.com"
```

生效：

```bash
source ~/.bash_profile
```

> GitHub Token 获取：https://github.com/settings/tokens -> Generate new token -> 勾选 `models:read`

### 3. 测试

```bash
python3 main.py
```

收到邮件就说明成功。日志在 `/root/logs/github-python/trending.log`。

### 4. 定时任务

```bash
crontab -e
```

加一行：

```
0 8 * * * source ~/.bash_profile && cd /root/work/workspace/gitee/github-trending-spider && /usr/bin/python3 main.py
```

## 文件结构

```
github-trending-spider/
├── main.py              # 主入口，协调全流程
├── github_trending.py   # GitHub Trending 爬虫 + AI 总结
├── hacker_news.py       # Hacker News API 获取 + 评论抓取 + AI 总结
├── email_builder.py     # HTML 邮件模板生成
├── email_sender.py      # SMTP 邮件发送
├── config.py            # 配置中心（从环境变量读取）
├── test_email.py        # SMTP 邮件发送测试
├── requirements.txt     # Python 依赖
└── README.md            # 本文件
```

## 可选配置项

以下配置均有默认值，通过环境变量覆盖：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `HN_TOP_COUNT` | 10 | HN 获取前 N 个热门帖子 |
| `HN_COMMENTS_PER_STORY` | 10 | 每帖获取前 N 条顶级评论 |
| `HN_MAX_RETRIES` | 5 | HN 请求最大重试次数 |
| `HN_CONCURRENT_WORKERS` | 10 | 并发请求线程数 |
| `AI_MODEL` | gpt-4o | AI 模型 |

## 故障排查

```bash
# 查看日志
cat /root/logs/github-python/trending.log

# 检查环境变量是否生效
echo $GITHUB_TOKEN
echo $SMTP_PASSWORD
```
