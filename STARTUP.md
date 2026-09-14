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

### 4. 启动后端

```bash
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

保持后端终端运行，API 文档地址为 `http://localhost:8000/docs`。

### 5. 启动前端调试

另开一个终端，在项目根目录执行（`package.json` 位于 `web/`）：

```bash
cd web
npm install
npm run dev -- --host 0.0.0.0 --port 5180
```

本机访问 `http://localhost:5180`；从其他电脑访问时，使用 `http://服务器IP:5180`。
Vite 默认将 `/api`（含 SSE）和 `/ws` 转发到 `http://127.0.0.1:8000`。
如果后端使用其他端口，在 `web/.env.local` 中设置 `DEV_API_TARGET=http://127.0.0.1:实际端口`，然后重启前端。
`VITE_API_BASE` 留空即可使用代理。遇到 `ECONNREFUSED` 时，检查后端是否运行，以及代理端口是否与后端一致。

如需由后端直接提供前端页面，先在 `web/` 执行 `npm run build`，再访问 `http://localhost:8000`。

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
| `LANGGRAPH_CHECKPOINT_PATH` | 原生 interrupt 检查点 SQLite 文件 | `./storage/langgraph_checkpoints.sqlite` |

SQL 数据库保存权威用户画像、作用域偏好和创作经验；Mem0 只负责语义历史案例，不负责决定长期偏好。请在发布前执行 `uv run alembic upgrade head`，为新增画像/经验表及偏好版本字段迁移。持久卷需同时包含 SQL 数据库、检查点文件和本地记忆 fallback 文件，避免重启后丢失暂停状态或跨会话记忆。SQLite 检查点适用于当前单实例部署；多实例部署前需统一持久化 checkpointer 并验证并发恢复互斥。

### 身份校验（生产）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AUTH_SECRET` | 外部网关签发的 HS256 JWT 校验密钥；生产必填 | - |
| `AUTH_ISSUER` | 可选 JWT `iss` 校验值 | - |
| `AUTH_AUDIENCE` | 可选 JWT `aud` 校验值 | - |
| `AUTH_ALLOW_UNVERIFIED_USER_HEADER` | 是否允许无签名 `X-User-ID`（仅受控内网） | `false` |

设置 `DEBUG=false` 后，HTTP、SSE、WebSocket 和资源接口只接受有效 Bearer JWT 的 `sub`/`user_id` 作为用户身份；无签名的 `X-User-ID` 仅在开发模式或显式内网开关下接受。

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
│   ├── personalization_service.py # SQL 画像、作用域偏好与 ACE 经验
│   └── video_pipeline.py      # 视频管线
└── ...
```

## 主动提问与可靠恢复

LangGraph 保留讨论编排，通过原生 `interrupt()` 暂停并通过 `Command(resume=...)` 续跑，检查点不依赖 HTTP 连接存活。需求解析、提问决策、回答处理节点共同维护共享 `CreativeBrief`。所有导演与 Critic 接收同一版本；优先级为“当前明确要求 > 项目决定 > 条件偏好 > 全局偏好”。

会话讨论从 `POST /api/sessions/{session_id}/discuss/stream` 启动。收到以下 SSE 后，客户端展示问题而不是标记讨论失败或完成：

```text
data: {"type":"awaiting_input","question_id":"q_example","question":{"id":"q_example","question":"请选择方向","options":["保持当前方向","更忠实原作"],"allow_free_text":true,"allow_decide":true}}

data: {"type":"paused","stop_reason":"awaiting_user"}
```

使用同一会话 ID 回答并继续消费返回的 SSE：

```http
POST /api/sessions/{session_id}/resume
Content-Type: application/json

{"selected_option":"更忠实原作"}
```

也支持 `{"free_text":"这次改成开放式结局"}`、`{"answer":"你决定"}`；`text` 是兼容字段。返回顺序为 `answer_applied` → 后续导演事件 → `script` → `task_result`，也可能再次收到问题并暂停。空回答返回 422；已完成的讨论返回 409；不存在或未暂停的检查点会给出明确错误。问题 ID 与已回答事项保存在图状态中以减少重复询问。

兼容工程级入口 `/api/projects/{project_id}/script/stream` 的客户端，使用 `/api/projects/{project_id}/script/resume`（别名 `/api/projects/{project_id}/resume`）。该兼容流程以工程 UUID 作为图 thread ID，状态保存在 Project，不额外创建 Session；会话入口才维护 Session 生命周期。不要混用两个入口的 ID。`/api/sessions/{session_id}/discuss/resume` 是会话恢复别名。

WebSocket 的 `pause_now`/`resume_now` 是进程内手动暂停控制，不等同于持久化的主动提问恢复；回答原生主动问题应使用上述 REST resume 接口。

## 用户画像与创作经验

所有个性化 API 位于 `/api/users/{user_id}`。`GET/PUT /profile` 读写结局倾向、情感风格、原作忠实度；`GET/POST /preferences` 管理带作用域、条件、证据来源、版本和状态的偏好。删除 `/preferences/{id}` 只使记录失效，保留审计历史。

`POST /observations` 使用查询参数 `text`、`source`、`scope`，只接受用户表达、选择、编辑和显式反馈来源。`scope` 可为 `global`、`project`、`session`、`request`；短期作用域必须绑定对应工程/会话。一次性要求请明确使用 `request`，不要写入全局画像。模型输出不是用户证据，不应提交为观察。

`GET/POST /experiences` 查询或增量维护“适用场景—创作建议—用户证据”，相近经验去重修订，`DELETE /experiences/{id}` 使其失效。`GET /personalization-context?current_request=...&project_id=...&session_id=...` 可检查本次解析结果。`POST /api/feedback` 先将显式反馈形成的偏好与经验事务性提交 SQL，再尽力补写 Mem0 历史案例；后者失败不撤销 SQL 数据。

开发版可用 `X-User-ID` 请求头绑定调用者。画像 API 会拒绝与路径 `user_id` 不一致的请求；工程/会话请求会依据工程 `metadata_.owner_user_id` 做归属校验。`DEBUG=true` 时允许省略请求头（仅本地兼容），`DEBUG=false` 时缺失身份返回 401、跨用户访问返回 403，且未建立归属的资源拒绝访问。此功能不是生产认证；公网部署必须在网关接入 OIDC/JWT、租户隔离与密钥轮换。

GEPA 实验接口位于 `/api/gepa`：候选提示词创建后，先用固定 `GEPA_MODEL`/`GEPA_BUDGET` 执行独立评测，再调用 compare 获取“画像基线 → 经验 → 优化”三阶段指标，达到阈值后 publish。注册表默认 `storage/gepa/registry.json`（`GEPA_STORE_PATH` 可覆盖），候选发布会自动归档同策略旧版本；未通过独立评测的候选不会发布。

## 持续优化阶段

本轮先建立可审计学习、经验注入和暂停恢复闭环。GEPA 需要真实用户反馈及独立评测后再启用，不会在线直接发布未经验证的提示词。后续固定 API 模型版本与调用预算，对比“画像基线 → 加入经验 → GEPA 优化”，优先评测本次例外正确率、修正一致性和跨会话无效提问数量；没有独立评测结果时不宣称收益或更新模型权重。

GEPA 已提供可执行的候选闭环：`POST /api/gepa/proposals` 生成候选，或使用
`POST /api/gepa/optimize` 一次完成三阶段对比、留出集独立评测和阈值发布。设置
`GEPA_USE_API=true` 才会调用提示词 mutation API；无 API 或调用失败会保留确定性候选，
并且不会绕过独立评测门槛。发布后的 `director_writing` 补充策略会自动注入新的导演讨论，
已经运行的 checkpoint 不会被热修改。

ANet 只负责服务注册、发现和跨 Agent 调用；AutoGen/LangGraph 负责导演讨论域。ANet daemon
不可用时会返回明确的 unavailable 状态，不会把 AutoGen 当作 ANet 的回退路径。

如需启用规则之后的结构化提问判断，可设置 `INTERACTION_POLICY_USE_API=true`；模型只能在规则允许的候选上选择继续、给建议或暂停，重复提问和越权仍由规则拒绝。

首页提供影视作品档案入口和“打开已有工程”列表。讨论页刷新后可请求
`/api/sessions/{id}/discussion-state`（工程兼容入口为 `/api/projects/{id}/discussion-state`）
读取当前问题与 CreativeBrief；用户回答会通过原生 `Command(resume=...)` 续跑同一检查点。
