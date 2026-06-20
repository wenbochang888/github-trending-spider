# -*- coding: utf-8 -*-
"""
Generate a Qumei Product Department AI morning report from AI Daily Frontier data.

The script is standalone and uses only Python standard library modules so other
devices can clone the project and run it after the normal project setup. It
never reads or prints secret values.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


DEFAULT_INPUT = Path("output/latest.json")

SOURCE_GITHUB_DAILY = "GitHub Trending Daily"
SOURCE_GITHUB_WEEKLY = "GitHub Trending Weekly"
SOURCE_HACKER_NEWS = "Hacker News"
SOURCE_LINUX_DO = "Linux.do"
SOURCE_V2EX = "V2EX"
SOURCE_TLDR_AI = "TLDR AI"
SOURCE_OPENAI = "OpenAI"
SOURCE_ANTHROPIC = "Anthropic"
SOURCE_INFOQ = "InfoQ AI Development"
SOURCE_DEEPMIND = "Google DeepMind"
SOURCE_HUGGINGFACE = "Hugging Face"
SOURCE_MISTRAL = "Mistral"

AGENT_KEYWORDS = (
    "agent", "agents", "agentic", "mcp", "skill", "skills", "tool", "tools",
    "code", "coding", "memory", "browser", "workflow", "automation",
    "智能体", "工具", "技能", "记忆", "工作流", "自动化",
)
MODEL_KEYWORDS = (
    "model", "models", "gpt", "claude", "gemini", "glm", "deepseek",
    "mistral", "reasoning", "benchmark", "eval", "evaluation",
    "模型", "推理", "评测", "基准",
)
HARDWARE_KEYWORDS = (
    "robot", "hardware", "edge", "device", "scanner", "chip", "home",
    "iot", "matter", "voice", "vision", "camera",
    "机器人", "硬件", "设备", "家居", "语音", "视觉", "芯片",
)
COST_KEYWORDS = (
    "cost", "spend", "usage", "token", "tokens", "quota", "pricing",
    "budget", "额度", "费用", "成本", "订阅",
)
SAFETY_KEYWORDS = (
    "security", "privacy", "leak", "governance", "control", "policy",
    "safe", "alignment", "risk", "权限", "隐私", "安全", "治理", "泄露",
)


def main():
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    input_path = resolve_path(base_dir, args.input)
    source_status = {
        "frontier": "未读取",
        "token": "已配置" if bool(os.environ.get("GITHUB_TOKEN")) else "未配置",
    }

    if args.refresh:
        source_status["frontier"] = refresh_frontier(base_dir)

    payload = load_payload(input_path)
    if payload.get("items"):
        source_status["frontier"] = "可用"
    elif source_status["frontier"] == "未读取":
        source_status["frontier"] = "不可用"

    report = build_report(payload, source_status, args.date)
    if args.output:
        output_path = resolve_path(base_dir, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)
        if not report.endswith("\n"):
            sys.stdout.write("\n")


def parse_args():
    parser = argparse.ArgumentParser(description="生成中文「曲美产品部 AI晨报」。")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="统一 JSON，默认 output/latest.json")
    parser.add_argument("--output", help="可选：写入 Markdown 文件；不传则输出到屏幕")
    parser.add_argument("--date", help="可选：覆盖报告日期，格式建议 YYYY年M月D日")
    parser.add_argument("--refresh", action="store_true", help="生成前先运行 main.py 刷新本地聚合数据")
    return parser.parse_args()


def resolve_path(base_dir, value):
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


def refresh_frontier(base_dir):
    try:
        result = subprocess.run(
            [sys.executable, "main.py"],
            cwd=str(base_dir),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
    except Exception:
        return "刷新失败，尝试读取缓存"
    if result.returncode == 0:
        return "已刷新"
    return "刷新失败，尝试读取缓存"


def load_payload(path):
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text, strict=False)
    except Exception:
        return {"generated_at": "", "item_count": 0, "items": []}


def build_report(payload, source_status, date_text=None):
    items = payload.get("items") or []
    today = date_text or format_today()
    report_parts = [
        "# 曲美产品部 AI晨报｜{}".format(today),
        "",
        "## 今日重点",
        "",
    ]
    for index, item in enumerate(build_focus_items(items), 1):
        report_parts.append("{}. 判断：{}".format(index, item["judgment"]))
        report_parts.append("   建议动作：{}".format(item["action"]))
    report_parts.extend(["", "## 硬件消费和软件动态", ""])
    report_parts.extend(render_section(build_hardware_section(items)))
    report_parts.extend(["", "## 大模型动态", ""])
    report_parts.extend(render_section(build_model_section(items)))
    report_parts.extend(["", "## 开源平台动态", ""])
    report_parts.extend(render_section(build_open_source_section(items)))
    report_parts.extend(["", "## 今日建议动作", ""])
    for index, action in enumerate(build_action_items(), 1):
        report_parts.append("{}. {}".format(index, action))
    report_parts.extend(["", "## AI Daily Frontier 摘要", ""])
    report_parts.extend(render_section(build_frontier_summary(items)))
    report_parts.extend(["", "## 数据源说明", ""])
    report_parts.append(build_source_note(payload, source_status))
    return "\n".join(report_parts).strip() + "\n"


def build_focus_items(items):
    github_agent = top_titles(items, [SOURCE_GITHUB_DAILY, SOURCE_GITHUB_WEEKLY], AGENT_KEYWORDS, 3)
    safety = top_titles(items, [SOURCE_DEEPMIND, SOURCE_HUGGINGFACE, SOURCE_TLDR_AI, SOURCE_INFOQ], SAFETY_KEYWORDS, 2)
    cost = top_titles(items, [SOURCE_OPENAI, SOURCE_LINUX_DO, SOURCE_V2EX, SOURCE_GITHUB_DAILY], COST_KEYWORDS, 2)
    model = top_titles(items, [SOURCE_OPENAI, SOURCE_ANTHROPIC, SOURCE_MISTRAL, SOURCE_TLDR_AI, SOURCE_LINUX_DO], MODEL_KEYWORDS, 2)

    focus = []
    if github_agent:
        focus.append({
            "judgment": "本地聚合器显示，开源热榜正在集中出现 Agent 技能、MCP 记忆、工具压缩和 Agent 原生应用，竞争点已从“会聊天”转向“会调用工具、会记住项目、会被审计”。代表信号：{}。".format("、".join(github_agent)),
            "action": "AI盒子和软件配置台先补“技能/工具管理页”，支持启停、权限、日志和版本回滚。",
        })
    else:
        focus.append({
            "judgment": "本地聚合器今天没有抓到特别集中的 Agent 开源项目，但行业主线仍是工具调用、记忆和可控执行。",
            "action": "继续把 AI盒子能力拆成可配置技能，不要只做单轮问答。",
        })
    if safety:
        focus.append({
            "judgment": "Agent 安全、隐私和治理信号升温，说明一旦接入文件、网页、客服或设备控制，风险会从回答错误扩大到越权执行。代表信号：{}。".format("、".join(safety)),
            "action": "龙虾U盘/AI龙虾加入“资料访问范围”和“禁止外发内容”两级开关，默认白名单。",
        })
    if cost:
        focus.append({
            "judgment": "社区和厂商都在讨论用量、额度、成本和企业支出控制，真实用户会先问“稳定吗、多少钱、能不能切换”。代表信号：{}。".format("、".join(cost)),
            "action": "配置台增加模型调用次数、预估费用、失败率和人工接管率。",
        })
    if model:
        focus.append({
            "judgment": "大模型更新频率继续升高，但有些消息仍是传闻或灰度，产品架构不能押注单一模型。代表信号：{}。".format("、".join(model)),
            "action": "模型接入层保持可插拔：同一任务至少准备主模型、备用模型和本地降级策略。",
        })
    focus.append({
        "judgment": "智能家居和物理 AI 的落地关键不是更会聊天，而是能稳定完成设备控制、场景编排和异常接管。",
        "action": "AI盒子先做 5 个一键模板：灯光、窗帘、空调、电视/投影、老人提醒，并提供测试按钮。",
    })
    return focus[:5]


def build_hardware_section(items):
    robot_titles = top_titles(items, [SOURCE_HUGGINGFACE, SOURCE_DEEPMIND, SOURCE_TLDR_AI, SOURCE_HACKER_NEWS], HARDWARE_KEYWORDS, 3)
    lines = []
    if robot_titles:
        lines.append("物理 AI/硬件信号：{}。产品判断：曲美不宜直接追复杂机器人，先做“摄像头/传感器识别 + 家庭场景建议 + 人工确认执行”。".format("、".join(robot_titles)))
    else:
        lines.append("硬件侧今天没有强新品信号。产品判断：AI盒子仍应优先打磨稳定控制和低配置成本，而不是追逐硬件概念。")
    lines.append("智能家居方向：用户买单的是少配置、少误触、可接管。产品判断：自然语言入口必须落到可测试的设备动作，不要停留在对话演示。")
    lines.append("软件配置台方向：配置、测试、发布、回滚、成本监控应在同一入口完成。产品判断：面向小白用户时，只显示中文结论和下一步动作，排错细节放高级区。")
    return lines


def build_model_section(items):
    model_titles = top_titles(items, [SOURCE_OPENAI, SOURCE_ANTHROPIC, SOURCE_MISTRAL, SOURCE_TLDR_AI, SOURCE_LINUX_DO], MODEL_KEYWORDS, 5)
    lines = []
    if model_titles:
        lines.append("模型更新：{}。产品判断：模型能力差距仍在变化，配置台要支持按任务切换，而不是全站固定一个模型。".format("、".join(model_titles)))
    lines.append("评测方向：部署前模拟、真实任务回放和企业用量分析正在变重要。产品判断：内部选型要用客服、导购、配置、售后真实样本评测。")
    lines.append("运营表达：外部宣传少讲参数，多讲“每天少做哪几件事、失败时谁接管、费用怎么控制”。")
    return lines


def build_open_source_section(items):
    github_titles = top_titles(items, [SOURCE_GITHUB_DAILY, SOURCE_GITHUB_WEEKLY], AGENT_KEYWORDS + COST_KEYWORDS, 6)
    infoq_titles = top_titles(items, [SOURCE_INFOQ, SOURCE_HUGGINGFACE, SOURCE_DEEPMIND], AGENT_KEYWORDS + SAFETY_KEYWORDS, 4)
    lines = []
    if github_titles:
        lines.append("GitHub 热榜：{}。产品判断：Agent 生态正在形成“技能市场 + 工具治理 + token 成本优化”的组合。".format("、".join(github_titles)))
    if infoq_titles:
        lines.append("工程平台：{}。产品判断：企业级 Agent 需要验证、权限、数据边界和审计，不只是更强模型。".format("、".join(infoq_titles)))
    lines.append("曲美可复用方向：先沉淀产品、客服、运营、硬件调试四类内部技能，再考虑开放给门店或经销商。")
    return lines


def build_action_items():
    return [
        "产品部：今天拉一张“AI盒子技能清单”，至少列 20 个技能，标注适用对象、输入、输出、风险等级和是否联网。",
        "软件：本周给配置台补最小成本面板，展示模型供应商、调用次数、失败次数、预估费用和人工接管次数。",
        "运营/销售：准备一版小白话术，把“用了什么大模型”改成“能帮门店/家庭每天少做哪三件事”。",
    ]


def build_frontier_summary(items):
    source_counts = Counter(item.get("source") for item in items)
    lines = []
    if source_counts:
        lines.append("本地聚合器本次读取 {} 条内容，覆盖 {} 个来源。产品判断：可以作为产品部每日信号底座，但仍要把传闻和官方信息分开。".format(len(items), len(source_counts)))
    github = top_titles(items, [SOURCE_GITHUB_DAILY, SOURCE_GITHUB_WEEKLY], AGENT_KEYWORDS, 3)
    if github:
        lines.append("GitHub + 产品判断：{} 代表 Agent 工具链继续升温，适合转成 AI盒子的技能/插件治理能力。".format("、".join(github)))
    tldr = top_titles(items, [SOURCE_TLDR_AI], AGENT_KEYWORDS + SAFETY_KEYWORDS + MODEL_KEYWORDS, 3)
    if tldr:
        lines.append("TLDR AI + 产品判断：{} 提醒我们关注 Agent 记忆、隐私、安全和模型更新节奏。".format("、".join(tldr)))
    infoq = top_titles(items, [SOURCE_INFOQ], AGENT_KEYWORDS + SAFETY_KEYWORDS, 2)
    if infoq:
        lines.append("InfoQ + 产品判断：{} 说明企业 AI 正在进入工程治理阶段，配置台要承担验证和审计职责。".format("、".join(infoq)))
    community = top_titles(items, [SOURCE_LINUX_DO, SOURCE_V2EX], MODEL_KEYWORDS + COST_KEYWORDS + AGENT_KEYWORDS, 3)
    if community:
        lines.append("Linux.do/V2EX + 产品判断：{} 说明真实用户更关心稳定性、额度、订阅和是否按自己的方式执行。".format("、".join(community)))
    if not lines:
        lines.append("本地聚合器暂无可读内容。产品判断：先检查采集任务，再用最近缓存生成降级晨报。")
    return lines[:6]


def build_source_note(payload, source_status):
    generated_at = payload.get("generated_at") or "未知时间"
    count = payload.get("item_count") or len(payload.get("items") or [])
    token_note = "GitHub Token 已配置" if source_status.get("token") == "已配置" else "GitHub Token 未配置，AI 摘要可能降级但原始资讯仍可用"
    return "联网检索由采集器刷新承担；本地 AI Daily Frontier {}，读取到 {} 条内容（生成时间：{}）；Obsidian 未作为本脚本必需数据源；{}；Redis 状态以采集程序结果为准。".format(
        source_status.get("frontier", "未知"),
        count,
        generated_at,
        token_note,
    )


def top_titles(items, sources, keywords, limit):
    source_set = set(sources)
    scored = []
    for item in items:
        if item.get("source") not in source_set:
            continue
        text = item_text(item)
        score = keyword_score(text, keywords)
        if score <= 0:
            continue
        score += int((item.get("meta") or {}).get("priority_score") or 0) / 100.0
        scored.append((score, clean_title(item.get("title", ""))))
    result = []
    seen = set()
    for _, title in sorted(scored, reverse=True):
        key = title.lower()
        if not title or key in seen:
            continue
        seen.add(key)
        result.append(title)
        if len(result) >= limit:
            break
    return result


def keyword_score(text, keywords):
    lower = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in lower)


def item_text(item):
    return " ".join(str(item.get(key, "")) for key in (
        "source", "category", "title", "original_summary", "chinese_summary", "backend_focus"
    ))


def clean_title(title):
    text = re.sub(r"\s+", " ", title or "").strip()
    return text[:80]


def render_section(lines):
    return ["- {}".format(line) for line in lines if line]


def format_today():
    now = datetime.now()
    return "{}年{}月{}日".format(now.year, now.month, now.day)


if __name__ == "__main__":
    main()
