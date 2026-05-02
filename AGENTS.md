# AGENTS

## 项目目标

`whatif-studio` 用于把用户“一句话改视频需求”转成一个简单的工程流程：

1. 创建工程并保存用户 prompt。
2. 在工程下上传图片 / 视频素材。
3. 启动 AutoGen 多导演讨论，SSE 透传讨论过程给前端，并把最终剧本写回 `projects` 表。
4. 在已有剧本的前提下生成视频，SSE 透传生成进度，并把成片 URL 写回 `projects.product`。

## 后端 API（FastAPI）

只保留以下业务入口：

- `GET /projects`
- `POST /projects`
- `GET /projects/{project_id}`
- `PUT /projects/{project_id}`
- `DELETE /projects/{project_id}`
- `GET /{project_id}/assets`
- `POST /{project_id}/assets`
- `DELETE /{project_id}/assets/{asset_id}`
- `POST /{project_id}/prepare`（SSE）
- `POST /{project_id}/generate`（SSE）
- `GET /agents`

## API 语义

- `/projects`：工程管理。
- `/{project_id}/assets`：工程下的素材管理。
- `/{project_id}/prepare`：启动 AutoGen，多导演讨论流式输出给前端；讨论完成后必须把剧本写入数据库 `projects.script`。
- `/{project_id}/generate`：启动视频生成并流式返回进度；必须存在 `projects.script` 才能生成，否则返回错误。
- `/agents`：返回 `config/agents.yaml` 中的全部 agent 配置。

## 数据库

只需要以下核心表：

- `projects`
  - `id`
  - `name`：工程名字
  - `prompt`：用户原始需求
  - `assets`：工程素材集合 / 关联
  - `script`：AutoGen 生成的剧本
  - `product`：最终成片 URL

- `assets`
  - `id`
  - `project_id`
  - `asset_type`：素材类型，只允许图片或视频
  - `url`：素材文件 URL

## 静态目录

FastAPI 必须同时暴露两个静态目录：

- `/storage` -> `storage`
- `/` -> `web/dist`

## 职责边界

- AutoGen 只负责“多导演讨论并产出剧本”。
- 视频生成只允许在工程已有剧本后启动。
- 前端只消费上述 API 和 SSE，不再依赖本地 mock 数据。
- 旧的 session、video-job、gateway 等额外业务入口不再作为项目目标的一部分。
