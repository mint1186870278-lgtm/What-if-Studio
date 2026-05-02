# AGENTS

## 项目目标

`whatif-studio` 用于把用户“想改视频的一句话需求”转为可执行的视频生成流程，支持本地产品调用，也支持通过 ANet 对外暴露服务能力。

## 核心业务流程

1. 创建工程  
工程是顶层容器，包含素材（assets）和会话（sessions）。

2. 发起会话并进行多导演讨论  
用户提交编辑需求后，AutoGen 启动多导演讨论：  
- 每位导演先判断是否参与  
- 参与后进行头脑风暴  
- 最终形成分工（剪辑 / 配音 / 素材脚本）  
- 合并为完整脚本

3. 确认生成视频  
将素材库和完整脚本传入 Seedance API 生成视频。  
注意：当前仓库暂不实现具体 Seedance API 接入细节，只保留流程与接口位置。

4. ANet 服务暴露  
上述能力封装为 ANet 服务，供其他 Agent 调用（如：新建工程、上传素材、一句话改视频）。

## 职责边界（强约束）

- AutoGen 是“导演讨论域能力”。  
- ANet 是“服务暴露与跨 Agent 调用通道”。  
- **ANet 不是 AutoGen 的替代，也不是 AutoGen 的 fallback。**

## 模块划分

- `src/api/projects.py`：工程管理 API（创建、查询、更新、删除）
- `src/api/assets.py`：素材上传与管理 API
- `src/api/sessions.py`：会话创建与讨论流式输出（SSE）
- `src/api/jobs.py`：视频任务创建与进度流（SSE）
- `src/agents/autogen_service.py`：多导演讨论编排与脚本输出
- `src/core/anet_gateway.py`：ANet 服务入口与路由（非 fallback）
- `src/core/render_service.py`：渲染服务编排（对接 Seedance 的位置）
- `web/src`：前端交互与可视化工作台

## 当前后端 API（FastAPI）

- 工程：
  - `POST /api/projects`
  - `GET /api/projects`
  - `GET /api/projects/{project_id}`
  - `PUT /api/projects/{project_id}`
  - `DELETE /api/projects/{project_id}`

- 素材：
  - `POST /api/projects/{project_id}/assets`
  - `GET /api/projects/{project_id}/assets`
  - `GET /api/assets/{asset_id}`
  - `GET /api/assets/{asset_id}/download`
  - `DELETE /api/assets/{asset_id}`

- 会话：
  - `POST /api/sessions`
  - `GET /api/sessions/{session_id}`
  - `POST /api/sessions/{session_id}/discuss/stream`（SSE）

- 视频任务：
  - `POST /api/video-jobs`
  - `GET /api/video-jobs/{job_id}`
  - `GET /api/video-jobs/{job_id}/events`（SSE）
  - `GET /api/video-jobs/{job_id}/output`

- 网关：
  - `GET /api/gateway/services`
  - `POST /api/gateway/invoke`
  - `GET /api/gateway/invocations`
  - `GET /api/gateway/invocations/events`（SSE）

## 前端流程要求

- 首页支持：
  - 打开已有工程
  - 新建工程

- 会话区支持：
  - 发起讨论
  - SSE 流式展示导演对话气泡
  - 显示导演“加入讨论”时机

- 任务区支持：
  - 确认后发起视频生成
  - SSE 显示任务阶段进度
  - 完成后提供视频播放/下载入口
