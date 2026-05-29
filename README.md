# ⚡ AI Morning Briefing (专属智能技术资讯助理)

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![Vue](https://img.shields.io/badge/vue-3.x-4fc08d.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-ff69b4.svg)

**AI Morning Briefing** 是一个面向极客与开发者的“个人专属 AI 资讯助理”。它能够自动从 GitHub Trending、Hacker News、Hugging Face 等高质量信息源采集数据，并利用 **LangGraph 智能体流水线** 根据**您的个人画像**进行深度筛选、打分、去重与智能搜索补全。最后，通过钉钉推送或极简冷峻风的 Web 面板，为您呈现结构化的晨报与技术演进网络。

---

## ✨ 核心特性 (V0.4)

* **🧠 LangGraph 智能体流水线 (Agentic Pipeline)**：摒弃了传统的硬编码流程，Loop B 现由有向无环图 (DAG) 驱动。通过 Map-Reduce 并发架构，大幅提升处理速度与稳定性，并在遇到检索失败时具备节点级重试与优雅降级能力。
* **🕵️ 意图感知路由 (Intention Routing)**：大模型会在生成摘要时自主判断新闻是否属于“完全陌生的专有名词”、“不知名开源项目”，动态输出 `needs_research` 意图，自动按需触发联网搜索 (DuckDuckGo)，告别死板的分数阈值触发机制。
* **🌊 智能按需补水 (Content Hydration)**：针对 RSS 源摘要过短（如仅有标题或少于 50 字符）的问题，自动触发 `trafilatura` 工具爬取原文正文，补充上下文信息，极大降低高价值资讯被 LLM 误判为噪音的概率。
* **🎯 精准记忆检索 (Memory Retriever)**：抛弃暴力注入 N 天历史数据的粗放方式。系统会提取当日所有入围资讯的 `ai_tags`，通过 TF-IDF 词频交集匹配，从历史记录中精准打捞相关记忆，在减少 Token 开销的同时增强脉络连贯性。
* **🤖 强个性化推荐 (Persona-based)**：通过 `.env` 中的 `USER_PERSONA` 定义你的技术栈与偏好，AI 助理会像资深技术编辑一样为你过滤并打分，仅保留真正对你有用的硬核资讯。
* **🧩 Prompt 资产化与 Tool 原子化**：所有大模型提示词从代码中剥离，存放在专属的 `prompts/` 目录下；所有外部调用能力（搜索、抓取、记忆检索）均被封装为标准的原子化 Tool。

---

## 🛠️ 技术栈

* **后端引擎**：Python 3.12 + FastAPI + LangGraph + APScheduler + SQLAlchemy
* **大模型驱动**：兼容 OpenAI API 规范的 LLM + DuckDuckGo Search
* **前端界面**：Vue 3 + Vite + Vue Router + DOMPurify + Mermaid
* **数据库**：无外部依赖的极简本地 SQLite

---

## 📦 快速开始

> ⚠️ 注意：V0.4 架构升级后，后端与项目根目录已实现完全解耦，所有后端相关操作均在 `backend/` 目录下进行。

### 1. 环境准备

本项目后端推荐使用 [uv](https://github.com/astral-sh/uv) 进行极速依赖管理。

```bash
# 克隆仓库
git clone https://github.com/yourusername/briefing_generation.git
cd briefing_generation

# 后端依赖安装
cd backend
uv sync

# 前端依赖安装
cd ../frontend
npm install
```

### 2. 环境配置

进入 `backend` 目录，复制配置文件并填写：

```bash
cd backend
cp .env.example .env
```

**关键配置项**说明（在 `backend/.env` 中）：

```ini
# --- LLM 核心配置 ---
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# --- 个性化调教 ---
# 定义你自己的画像，越详细，推荐越准
USER_PERSONA="我是一名资深后端架构师，主要关注 Python、Go 生态，以及 LLM Agent 落地应用..."

# --- V0.4 按需补水配置 ---
SCRAPER_MIN_LENGTH=50
SCRAPER_MAX_CHARS=1000
```

### 3. 一键启动

**启动后端 API 与调度任务**：
```bash
cd backend
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

1. **Loop A (高频资讯雷达)**：每隔一定时间执行。并行从各数据源采集资讯，若发现短内容自动触发 **Content Hydration** 抓取原文。之后交由 LLM 根据 `USER_PERSONA` 进行打分并提取 `ai_tags`。高分内容入库。
2. **Loop B (智能体总装流水线)**：每天早晨定时执行。LangGraph 工作流被触发：
   - 提取过去 48h 的高分新闻，语义去重并聚合。
   - 提取当日所有 `ai_tags`，精准拉取历史脉络（短期记忆）。
   - Map-Reduce 并发调用 **Analyzer Node**，如果判别存在信息盲区，意图路由至 **Researcher Node** 联网搜索补充背景。
   - 将结果聚合，生成技术演进思维导图并发布。
3. **Loop C (自净管线)**：每天凌晨自动清理过期的高频抓取历史数据。

---

## 📚 常用 API (开发者)

| 接口路径 | 方法 | 说明 |
|----------|------|------|
| `/api/briefings` | GET | 获取近期生成的早报列表 |
| `/api/briefings/{date}` | GET | 获取指定日期的早报详情（含精选与资讯流） |
| `/api/trigger?loop=A` | POST | 手动触发高频资讯抓取任务 (Loop A) |
| `/api/trigger?date=YYYY-MM-DD` | POST | 手动触发 LangGraph 早报生成流 (Loop B) |
| `/api/briefings/{date}` | DELETE | 删除指定日期早报数据及精选资讯 |

---

## 🤝 参与贡献

欢迎提交 Pull Request 或 Issue！

提交代码前请确保通过所有单元测试：
```bash
cd backend
uv run pytest tests/ -v
```

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源。
