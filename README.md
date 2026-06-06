# ⚡ AI Morning Briefing (专属智能技术资讯助理) V0.5

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![Vue](https://img.shields.io/badge/vue-3.x-4fc08d.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)

**AI Morning Briefing** 是一个面向极客与开发者的准企业级“个人专属 AI 资讯中枢”。它能够自动从高质量信息源采集数据，利用 **大模型自定义流水线** 根据**您的个人画像**进行深度槽位提取、双维打分、语义去重与智能预诊断。最后，通过极具极客美学的炫酷 Web 面板（内置宇宙星空背景）或钉钉推送，为您呈现连贯、专业的全景 Markdown 科技晨报。

---

## ✨ 核心特性 (V0.5 架构巨变)

* **🏗️ 原生高效流水线 (Linear Workflow)**：V0.5 移除了繁重的 LangGraph 依赖，采用了轻量且掌控力更强的原生线性管线（Pipeline），并在内部实现了“带反馈的多次重试机制（Feedback-loop Retry）”，确保 Markdown 生成结果的完美合规。
* **🗂️ 结构化槽位提取 (Slot Extraction)**：彻底抛弃了早期版本发散的总结逻辑。通过 `slot_extractor` 强制大模型提取事件分类、关键实体、硬指标 (hard_metrics) 等结构化槽位，让信息高度可控。
* **⚖️ 双维并轨打分系统**：取代了单一的模糊评分，从“技术实用分 (Tech Utility)”和“宏观影响分 (Macro Impact)”两个独立维度衡量新闻价值，并持久化评分理由，过滤噪音更加科学。
* **🧬 语义级双轨去重 (Embedding Dedup)**：舍弃了基于标题字符匹配的传统方式，全面引入 Embedding 向量化特征计算。通过设定绝对放行与拦截阈值，精准捕捉“换汤不换药”的重复新闻；处于灰度区间的资讯会自动交由 LLM 裁决。
* **🛡️ 滑动防抖推送 (Push Throttle)**：针对突发事件导致的刷屏推送问题，引入了基于实体标签的内存级防抖窗口。短时间内同类型的高分突发新闻会被熔断拦截，并优雅合并推送。
* **🤖 资产化 Prompt 与画像管理**：所有大模型提示词（包括您的个人技术偏好 `persona.txt`）全部分离到 `backend/prompts/` 目录，您可以像编辑文本文件一样随时调教 AI 的品味与工作流。
* **🌌 全新炫酷前端架构**：彻底重构的 Vue 3 前端，引入了 `SpaceBackground` 星空粒子背景特效，不仅展示双维度复合分数，还能将 AI 撰写的最终内容作为一篇原生多排版 Markdown 长文直接渲染。

---

## 🛠️ 技术栈

* **后端引擎**：Python 3.12 + FastAPI + APScheduler + SQLAlchemy (无 Langchain/LangGraph 绑架)
* **AI 基础设施**：兼容 OpenAI 规范的 LLM + 文本 Embedding 向量支持 + DuckDuckGo RAG 搜索
* **前端界面**：Vue 3 + Vite + Vue Router + DOMPurify (全新星空暗黑主题)
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

# --- V0.5 Embedding 去重 ---
EMBEDDING_MODEL=text-embedding-3-small
DEDUP_PASS_THRESHOLD=0.80
DEDUP_REJECT_THRESHOLD=0.95

# --- V0.5 防抖推送配置 ---
PUSH_THROTTLE_WINDOW=1800
PUSH_THROTTLE_MAX=3
```

> **个性化调教**：请直接修改 `backend/prompts/persona.txt` 来定义你的技术栈与偏好，AI 助理会依据这份文件为你过滤新闻。

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

## 📅 系统运转主循环 (Loops)

系统后端由精准的定时任务调度器（APScheduler）驱动，分为三个循环管线：

1. **Loop A (高频资讯摄入管线)**：每隔一定时间执行。
   - 抓取 RSS -> 文本粗洗 -> 提取特征计算 Embedding
   - **双轨去重**：余弦相似度硬拦截 + 灰度区 LLM 裁决
   - **预诊断与 RAG**：判断是否属于盲区并触发搜索
   - **槽位抽取**：深度解构新闻并进行双维（技术+宏观）打分
   - **防抖推送**：针对高分突破事件的防刷屏判定入库
2. **Loop B (长文早报聚合管线)**：每天早晨定时执行。
   - 提取过去 48h 的高分新闻，组装分类数据。
   - 读取 `briefing_template.md` 模板，将其交由 Filler 组装器填充内容并生成 Markdown。
   - 触发 **Validator** 进行合规性审查（如 Mermaid 图表是否正确），若不合规自带 Feedback 退回重做，通过后持久化发布。
3. **Loop C (碎片清理管线)**：定期自净。
   - 删除过期的 SQLite 历史数据。
   - 定期执行 `VACUUM` 释放碎片空间。

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
