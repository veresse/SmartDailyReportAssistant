# 智能 AI 开发者早报系统

自动采集 GitHub Trending、Hacker News、Hugging Face 等技术信息源，筛选 AI 相关新闻，并用大模型生成结构化早报、背景知识和技术演进思维导图。

## 功能概览

- 多源采集：GitHub Trending、Hacker News Top Stories、Hugging Face Papers/Models/Spaces。
- AI 新闻过滤：先按目标读者筛选 AI 相关内容，再进入摘要流程。
- 语义去重：合并不同来源中指向同一事件/项目的话题。
- 结构化摘要：生成一句话总结、核心要点、重要性说明和分类。
- 背景知识补充：识别术语/模型/项目/公司等关键词，使用 DDGS 联网检索后再让 LLM 补充背景。
- 技术演进思维导图：生成 Mermaid mindmap，并在前端渲染为可交互图。
- 前端看板：日历视图、早报详情页、思维导图节点跳转到对应新闻。
- 钉钉推送：早报生成后推送思维导图图片链接、前端详情链接和文字兜底摘要。
- 任务恢复：后端重启时会把中断遗留的 processing/collecting 任务标记为 failed。
- 重新生成：详情页可删除某日早报及关联数据，再重新生成。

## 技术栈

- 后端：Python 3.12、FastAPI、SQLAlchemy、APScheduler、OpenAI-compatible API、DDGS。
- 前端：Vue 3、Vue Router、Vite、Mermaid、DOMPurify。
- 默认数据库：SQLite，路径为 `data/briefing.db`。

## 目录结构

```text
src/briefing/
  ai/             # 去重、过滤、摘要、背景补充、思维导图生成
  api/            # FastAPI 路由
  collectors/     # 多源采集器
  push/           # 钉钉等推送适配
  scheduler/      # 早报生成编排与定时任务
frontend/         # Vue 前端
tests/            # 后端单元测试
docs/             # 需求文档
test/             # 原始采集脚本参考
```

## 环境准备

后端使用 `uv` 管理依赖：

```bash
uv sync --extra dev
```

前端安装依赖：

```bash
cd frontend
npm install
```

## 配置

复制环境变量模板：

```bash
cp .env.example .env
```

Windows PowerShell 可使用：

```powershell
Copy-Item .env.example .env
```

至少需要配置：

```env
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
DATABASE_URL=sqlite:///./data/briefing.db
FRONTEND_BASE_URL=http://localhost:5173
```

钉钉推送可选配置：

```env
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=your-token
DINGTALK_SECRET=SECxxxxxxxxxxxxxxxx
DINGTALK_TIMEOUT=10
DINGTALK_SUMMARY_MAX_ITEMS=20
```

注意：`.env` 包含密钥和 webhook，不要提交到 Git。

## 启动

启动后端：

```bash
uv run uvicorn briefing.main:app --reload --port 8000
```

启动前端：

```bash
cd frontend
npm run dev
```

前端默认访问：

```text
http://localhost:5173
```

后端健康检查：

```text
http://localhost:8000/health
```

## 常用 API

- `GET /api/briefings`：早报列表。
- `GET /api/briefings/{date}`：指定日期早报详情。
- `POST /api/trigger?date=YYYY-MM-DD`：手动生成指定日期早报；不传 `date` 时生成今天。
- `DELETE /api/briefings/{date}`：删除指定日期早报、核心新闻和原始采集数据。
- `GET /api/dates`：日历可用日期。

## 流程说明

1. 启动时初始化数据库并注册定时任务。
2. 采集多个平台的候选新闻。
3. 保存原始数据到 `raw_news_items`。
4. 使用 LLM 语义去重。
5. 使用 LLM 按目标读者筛选 AI 相关新闻。
6. 并行调用 LLM 生成摘要和背景知识。
7. 生成 Mermaid 思维导图。
8. 保存 `daily_briefings` 和 `briefing_items`。
9. 如果配置了钉钉 webhook，则推送思维导图图片链接、详情页链接和文字摘要。

## 测试与构建

后端测试：

```bash
uv run pytest
```

或：

```bash
.venv/Scripts/python.exe -m pytest
```

前端构建：

```bash
cd frontend
npm run build
```

## Git 提交建议

推荐提交：

- `src/`
- `frontend/src/`
- `frontend/public/`
- `tests/`
- `docs/`
- `pyproject.toml`
- `uv.lock`
- `frontend/package.json`
- `frontend/package-lock.json`
- `.env.example`
- `.gitignore`
- `README.md`

不要提交：

- `.env`
- `.venv/`
- `data/*.db`
- `__pycache__/`
- `.pytest_cache/`
- `frontend/node_modules/`
- `frontend/dist/`
