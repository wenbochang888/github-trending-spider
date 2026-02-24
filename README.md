# GitHub Trending Spider

每日自动爬取 GitHub Trending 热点项目，通过 AI 生成中文总结，邮件推送到指定邮箱。

## 功能

- 爬取 GitHub Trending **每日热点** 和 **每周热点**
- 通过 GitHub Models API (GPT-4o-mini) 生成中文总结
- 生成 HTML 表格邮件，包含项目信息和 AI 分析
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
# GitHub Trending Spider
export GITHUB_TOKEN="ghp_你的token"
export SMTP_USER="changwenbo141@163.com"
export SMTP_PASSWORD="你的163授权码"
export MAIL_TO="727987105@qq.com"
```

生效：

```bash
source ~/.bash_profile
```

> GitHub Token 获取：https://github.com/settings/tokens → Generate new token → 勾选 `models:read`

### 3. 测试

```bash
python3 github_trending.py
```

收到邮件就说明成功。日志在 `/root/logs/github-python/trending.log`。

### 4. 定时任务

```bash
crontab -e
```

加一行：

```
0 8 * * * source ~/.bash_profile && cd /root/work/workspace/gitee/github-trending-spider && /usr/bin/python3 github_trending.py
```

## 文件结构

```
github-trending-spider/
├── github_trending.py   # 主脚本
├── config.py            # 配置（从环境变量读取）
├── requirements.txt     # Python 依赖
└── README.md            # 本文件
```

## 故障排查

```bash
# 查看日志
cat /root/logs/github-python/trending.log

# 检查环境变量是否生效
echo $GITHUB_TOKEN
echo $SMTP_PASSWORD
```
