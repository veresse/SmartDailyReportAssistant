# ⚡ AI Morning Briefing (专属智能技术资讯助理)

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![Vue](https://img.shields.io/badge/vue-3.x-4fc08d.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)

**AI Morning Briefing** 是一个面向极客与开发者的“个人专属 AI 资讯助理”。它能够自动从 GitHub Trending、Hacker News、Hugging Face 等高质量信息源采集数据，并利用大语言模型（LLM）根据**您的个人画像**进行深度筛选、打分、去重与总结。最后，通过钉钉推送或极简暗黑风的 Web 面板，为您呈现结构化的晨报与技术演进网络。

---

## ✨ 核心特性 (V0.3)

* **🤖 强个性化推荐 (Persona-based)**：彻底告别信息过载。通过 `.env` 中的 `USER_PERSONA` 定义你的技术栈与偏好，AI 助理会像资深技术编辑一样为你过滤并打分，仅保留真正对你有用的硬核资讯。
* **🛡️ 三层智能去重管线**：
  * **拦截层**：利用 `rapidfuzz` 过滤历史 24 小时的高相似度标题新闻，节约 Token 开销。
  * **语义层**：同日不同源事件（如同一个开源项目在 GitHub 和 HN 同时上榜）语义聚合。
  * **记忆层**：注入过去 3 天的短期记忆作为上下文，如果新闻在近期已报道，AI 将打上 `[重复已阅]` 标签并在前端视觉降级。
* **🏷️ AI 智能标签 (`ai_tags`)**：大模型会在分析新闻时自动提取前沿实体与概念标签，形成赛博朋克风的专属词库。
* **🧠 技术演进网络**：自动梳理当日各新闻的关联脉络，生成 Mermaid 思维导图。
* **📱 全端适配与推送**：支持钉钉群机器人的富文本（含导图与链接）推送，安全策略适配自定义关键字（如 `【日报】`）；同时提供极简冷峻风 (Dark-Glassmorphism) 的专属 Web Dashboard。
* **🧹 自动化存储管理**：轻量级 SQLite 单体存储，内置后台清理机制，自动清除过期（默认 7 天）的历史冗余抓取记录，保持系统轻快。

---

## 🛠️ 技术栈

* **后端引擎**：Python 3.12 + FastAPI + SQLAlchemy + APScheduler + rapidfuzz
* **大模型驱动**：兼容 OpenAI API 规范的 LLM + DuckDuckGo Search (背景检索)
* **前端界面**：Vue 3 + Vite + Vue Router + DOMPurify + Mermaid
* **数据库**：无外部依赖的极简本地 SQLite

---

## 📦 快速开始

### 1. 环境准备

本项目后端推荐使用 [uv](https://github.com/astral-sh/uv) 进行极速依赖管理。

```bash
# 克隆仓库
git clone https://github.com/yourusername/briefing_generation.git
cd briefing_generation

# 后端依赖安装
uv sync --extra dev

# 前端依赖安装
cd frontend
npm install
```

### 2. 环境配置

回到项目根目录，复制配置文件并填写：

```bash
cp .env.example .env
```

**关键配置项**说明（在 `.env` 中）：

```ini
# --- LLM 核心配置 ---
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# --- V0.3 个性化调教 ---
# 定义你自己的画像，越详细，推荐越准
USER_PERSONA="我是一名资深后端架构师，主要关注 Python、Go 生态，以及 LLM Agent 落地应用..."
# 只有打分大于等于该值的资讯才会进入早报
SCORE_THRESHOLD=75

# --- 钉钉推送配置 (可选) ---
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=your_token
DINGTALK_SECRET=SECxxxxxxxxxxxxxxxxxxxx
```

### 3. 一键启动

**启动后端 API 与调度任务**：
```bash
uv run uvicorn briefing.main:app --reload --port 8000
```

**启动前端开发服务器**：
```bash
cd frontend
npm run dev
```

* 默认前端访问地址：http://localhost:5173
* 后端 API 文档：http://localhost:8000/docs

---

## 📅 工作流说明 (Loops)

系统后端由精准的定时任务调度器（APScheduler）驱动，分为三个循环管线：

1. **Loop A (高频资讯雷达)**：每两小时执行一次。并行从各数据源采集资讯，经过第一层“标题相似度比对”后，交由 LLM 根据 `USER_PERSONA` 进行打分并提取 `ai_tags`。只有高分内容会落库留存。
2. **Loop B (每日早报总装)**：每天早晨 8:00 执行（可配置）。从过去 24 小时内的高分库中提取数据，结合历史 3 天的短期记忆（防御性去重），生成包含一句话总结、核心价值、背景补充以及技术演进思维导图的完整早报。
3. **Loop C (自净管线)**：每天凌晨 2:00 执行。自动清理超过保留期限（`CLEANUP_RETENTION_DAYS`）的无用原始垃圾数据，压缩 SQLite 体积。

---

## 📚 常用 API (开发者)

| 接口路径 | 方法 | 说明 |
|----------|------|------|
| `/api/briefings` | GET | 获取近期生成的早报列表 |
| `/api/briefings/{date}` | GET | 获取指定日期的早报详情（含精选与资讯流） |
| `/api/trigger?loop=A` | POST | 手动触发高频资讯抓取任务 (Loop A) |
| `/api/trigger?date=YYYY-MM-DD` | POST | 手动触发或重做某日的早报生成 (Loop B) |
| `/api/briefings/{date}` | DELETE | 删除指定日期早报数据及精选资讯 |

---

## 🤝 参与贡献

欢迎提交 Pull Request 或 Issue！

提交代码前请确保通过所有单元测试：
```bash
uv run pytest -v
```

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源。
