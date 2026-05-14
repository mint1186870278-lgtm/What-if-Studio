# What-if Studio 启动指南

## 快速开始

### 1. 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少填写一个 LLM 的 API Key
```

### 3. 运行数据库迁移

```bash
alembic upgrade head
```

### 4. 启动服务

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 `http://localhost:8000` 查看前端界面。

---

## 环境变量参考

### LLM 配置（至少配置一个）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | - |
| `OPENAI_BASE_URL` | OpenAI 兼容 API 地址 | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | 默认模型名称 | `gpt-4o-mini` |
| `ANTHROPIC_API_KEY` | Claude API 密钥 | - |
| `ZHIPU_API_KEY` | 智谱 GLM API 密钥 | - |
| `SILICONFLOW_API_KEY` | 硅基流动 API 密钥 | - |

### 数据库切换

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | SQLite 连接串 | `sqlite:///./whatif.db` |
| `POSTGRES_USER` | PostgreSQL 用户名（设置了即启用 PG） | - |
| `POSTGRES_PASSWORD` | PostgreSQL 密码 | - |
| `POSTGRES_HOST` | PostgreSQL 主机 | `localhost` |
| `POSTGRES_PORT` | PostgreSQL 端口 | `5432` |
| `POSTGRES_DB` | PostgreSQL 数据库名 | `whatif` |

**切换方式**：设置 `POSTGRES_USER` 环境变量即自动从 SQLite 切换到 PostgreSQL。

### 视频生成模型

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HAPPYHORSE_API_KEY` | HappyHorse (DashScope) 视频编辑 | - |
| `KLING_API_KEY` | Kling (快手) 视频生成 | - |
| `WAN_API_KEY` | Wan 视频生成 | - |

### 记忆系统

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MEM0_API_KEY` | Mem0 API 密钥（可选，无可本地回退） | - |
| `CHROMA_PERSIST_PATH` | Chroma 向量数据库存储路径 | `./storage/chroma` |

---

## 配置不同 LLM 提供商

### OpenAI / 兼容 API

```env
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

### Claude (Anthropic)

```env
ANTHROPIC_API_KEY=sk-ant-xxx
```

### 智谱 GLM

```env
ZHIPU_API_KEY=xxx
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
```

### DeepSeek

使用 OpenAI 兼容端点：

```env
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

---

## 配置视频模型

### HappyHorse（视频编辑 — 需要源视频）

```env
HAPPYHORSE_API_KEY=sk-xxx
```

HappyHorse 是主力视频编辑模型，需要提供源视频 URL + 编辑指令。

### Kling（文生视频）

```env
KLING_API_KEY=xxx
```

### Wan（文生视频）

```env
WAN_API_KEY=xxx
WAN_BASE_URL=
```

无视频 API Key 时，系统使用 ffmpeg 字幕叠加作为回退方案。

---

## 数据库迁移

```bash
# 生成新迁移（模型变更后）
alembic revision --autogenerate -m "描述你的变更"

# 执行迁移
alembic upgrade head

# 回滚一步
alembic downgrade -1

# 查看迁移历史
alembic history
```

---

## 成本优化：分镜预览

视频生成成本较高，系统支持两步流程：

1. **分镜预览**（低成本）：调用文本 LLM 将剧本拆分为分镜脚本，确认叙事结构
2. **视频生成**（高成本）：用户确认分镜后，调用视频模型生成完整视频

前端可通过 API 分步调用实现此流程。

---

## 架构说明

```
src/
├── agents/
│   ├── langgraph_service.py   # LangGraph 讨论编排（新）
│   └── autogen_service.py     # AutoGen 讨论编排（旧，保留兼容）
├── api/
│   ├── ws.py                  # WebSocket：用户介入
│   ├── sessions.py            # SSE 讨论流
│   └── ...
├── core/
│   ├── model_router.py        # 模型路由器（文本+视频）
│   ├── memory_service.py      # 记忆系统（Mem0 + Chroma）
│   └── video_pipeline.py      # 视频管线
└── ...
```
