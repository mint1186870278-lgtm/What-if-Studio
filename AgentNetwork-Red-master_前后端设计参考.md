# AgentNetwork-Red-master 前后端详细说明（用于 yinanping-studio 背景参考）

## 1. 文档目的与范围

本说明面向当前 `yinanping-studio` 项目，系统梳理 `AgentNetwork-Red-master` 的前端与后端实现，覆盖：

- 前端整体架构、页面设计、可视化机制、状态流、通信方式
- 后端服务启动、路由/API、鉴权、WebSocket 事件、数据模型与业务流程
- 设计文档与实际代码的差异点
- 对 `yinanping-studio` 的可借鉴策略与风险提醒

说明依据源码目录：`e:/10.竞赛/南客松/前端/AgentNetwork-Red-master`

---

## 2. 项目总体结构

`AgentNetwork-Red-master` 不是单一前后端应用，而是由多个子系统组成：

- `display-demo`：大屏前端（Vite + D3），用于 Agent 网络展示与“话题回放”
- `qr-gui`：Node 网关 + 手机端 H5 + 队列/SSE，负责把手机发起的话题推给大屏
- `ui/server` + `cmd/dddserver`：Go DDD 后端（餐厅域 API + WS）
- `ui/docs`：较完整的 API/UI 设计文档（部分超前于代码）
- `internal/bd` + `cmd/bd*`：BD 数据流水线（独立于 DDD 主 API）
- `bd/display`：静态展示页（非 Agent 网络大屏）

关键结论：`display-demo` 与 `ui/server` 在仓库中并存，但当前可运行的大屏主链路更直接依赖 `qr-gui` 队列接口，而不是直接吃 DDD 的 `/api/ddd/v1`。

---

## 3. 前端详细设计

## 3.1 技术栈与打包结构

路径：`display-demo`

- 构建：Vite
- 可视化：D3 v7
- Markdown 渲染：`marked`
- 头像生成：`boring-avatars`
- React 19：仅用于生成静态 SVG 头像（`renderToStaticMarkup`），不是 React SPA

入口与页面：

- `display-demo/index.html` -> `src/main.js`（大屏）
- `display-demo/detail.html` -> `src/detail.js`（Agent 详情页）
- `vite.config.js` 配置多入口构建

## 3.2 页面层与视觉模块设计

大屏主页面由 `main.js` 中 `buildShell()` 直接拼出壳层，核心模块：

- `#network-stage`：网络图舞台
- `#live-overlay`：直播/回放浮层（消息流）
- `#spotlight-card`：闲时聚光灯 Agent 卡片
- `#idle-banner`：待机提示
- `#queue-indicator`：排队话题数量
- `#agent-detail-overlay`：点击节点后的档案卡
- `/api/switch?mode=mobile`：移动端切换入口

特点：不是组件框架驱动，而是“D3 + 原生 DOM 动态壳层”的轻前端模式。

## 3.3 前端状态管理与数据流

### 3.3.1 运行时内核（runtime）

`src/runtime.js` 的 `AgentRuntime` 维护：

- agents（Agent 当前状态）
- activeSessions（当前会话/任务）
- eventLog（事件）

采用观察者模式：

- `runtime.subscribe(listener)`
- 状态变更后 `emit()`，通常由 `requestAnimationFrame` 合帧推送

`main.js` 订阅后把快照交给网络图：

- `network.update(snapshot, { selection, query, theme })`

### 3.3.2 队列桥接（queueBridge）

`src/queueBridge.js` 负责从后端队列读取“待播放话题”，并按顺序回放：

- `GET /api/queue`：获取队列
- `GET /api/queue/:id`：获取单话题详情
- `POST /api/queue/:id/played`：标记播放完成
- `EventSource('/api/queue/events')`：监听新话题

回调链：

- `onPlaybackStart(topic)` -> 打开直播层
- `onMessage(msg)` -> 逐条渲染消息
- `onPlaybackEnd()` -> 关闭直播层/恢复闲态

### 3.3.3 详情页状态

`detail.js` 以 URL 参数 `?id=` 选取 Agent，结合：

- 静态档案数据（seed）
- localStorage 中的 `liveSnapshot`（期望实时）

注意：代码中 `writeLiveSnapshot` 定义存在，但主链路接线不完整，详情页“实时性”在现状下偏弱。

## 3.4 网络可视化与交互机制（socialNetwork）

路径：`src/socialNetwork.js`

### 3.4.1 渲染层级

- SVG + 分层 Group：`zoneLayer`、`linkLayer`、`nodeLayer`
- 内置 `defs` 用于滤镜、渐变、头像 pattern

### 3.4.2 力模型

`d3.forceSimulation` 组合了多种力：

- `charge`（斥力）
- `collision`（碰撞）
- `wander`（漫游）
- `session`（会话聚合）
- `bounds`（边界约束）
- `bezierGather`（曲线聚集动态）

这使节点在“闲时游走”和“任务聚合”之间可平滑切换。

### 3.4.3 摄像机与视角

包含 `CAMERA_PRESETS`（overview / session）与视角变换逻辑，可做全局与会话焦点切换。

### 3.4.4 交互

- 点击 Agent 节点 -> `onSelectAgent`
- 点击 Session 区域 -> `onSelectSession`
- 点击空白 -> `onClearSelection`
- Tooltip + 高亮反馈

## 3.5 前端头像系统设计

路径：`src/avatarSystem.js`

头像策略是双路径：

- 若 Agent 有 portrait URL，优先用真实图片
- 否则使用 `boring-avatars` 动态生成 SVG DataURL 作为 fallback

这套设计可直接借鉴到 `yinanping-studio`：先支持真人头像，再自动回退算法头像，避免空图。

## 3.6 主题与视觉语义设计

路径：`src/themes.js`

- 主题提供 graph、group 色板等配置
- `applyTheme` 统一注入视觉变量
- 网络图/节点/边/文字颜色随主题变化

好处：视觉方案与业务逻辑解耦，便于比赛演示切风格。

## 3.7 前端数据来源与接口关系

前端实际依赖数据源分为三类：

- `public/mock/*.json`：Agent 初始种子
- `qr-gui` 的 queue API + SSE：实时回放驱动
-（设计上）DDD API/WS：文档可用，但 display-demo 当前未深度接入

---

## 4. 后端详细设计（DDD 服务）

## 4.1 技术栈与运行方式

后端主体路径：

- `cmd/dddserver/main.go`
- `ui/server/*`
- `ui/server/store/*`
- `ui/server/anet/client.go`

技术栈：

- Go + net/http
- SQLite（`modernc.org/sqlite`）
- WebSocket（gorilla/websocket）

启动参数（`main.go`）：

- `-data-dir`（默认 `./ddd-data`）
- `-host`（默认 `0.0.0.0`）
- `-port`（默认 `9000`）
- `-anet-url`（默认 `http://127.0.0.1:3998`）
- `-anet-token`（为空则尝试读取 `$HOME/.anet/api_token`）

## 4.2 HTTP 路由设计

由 `ui/server/server.go` 统一注册，前缀为 `/api/ddd/v1`。

主要资源域：

- `restaurant/status`：全局状态
- `meta`：服务能力说明
- `menu`：技能菜单 CRUD
- `tables`：入座/离座
- `rooms`：包间操作
- `orders`：下单/上菜/消化
- `bill`：账单获取/支付/确认
- `agents`：画像与历史

附加实时通道：

- `GET /ws/dashboard`

## 4.3 鉴权与身份设计

实现位于 `ui/server/auth.go`，当前规则：

- 通过请求头 `X-Agent-DID` 传递身份
- DID 必须以 `did:key:` 开头
- 匿名可访问只读接口
- 写操作由 `requireAgent(...)` 强制要求身份

这与部分文档中写的 Bearer 用法不同：Bearer 主要用于 DDD 服务调用 ANet daemon，而非前端调用 DDD 的主鉴权。

## 4.4 错误模型与接口风格

`server.go` 统一 JSON 输出与错误结构：

- 成功：`writeJSON(...)`
- 错误：`{ error, message, suggestion }`

此外：

- 请求体解析限制 1MiB
- CORS 允许 `*`
- `OPTIONS` 返回 204

这套错误格式很适合给 Agent/前端做可解释错误处理。

## 4.5 业务流程编排（就餐域）

核心链路：

1. 入座 `tables/sit`
2. 下单 `orders`
3. 上菜 `orders/{id}/serve`
4. 消化 `orders/{id}/digest`
5. 离桌 `tables/leave`
6. 账单 `bill/{session}`
7. 支付 `bill/{session}/pay`
8. 确认 `bill/{session}/confirm`

每个关键节点会触发广播事件（order.*, table.update, bill.paid 等）。

## 4.6 WebSocket 事件系统

`server.broadcast(event, data)` 会：

- 构造 `{event, timestamp, data}`
- 推送给所有 WS 连接
- 同时写入 `events` 表，支持审计/回放

`ws.go` 里还会定时推送 `restaurant.status` 心跳快照。

## 4.7 数据存储模型（SQLite）

`ui/server/store/store.go` 迁移并管理核心表：

- `skills`
- `tables`
- `sessions`
- `rooms`
- `orders`
- `order_items`
- `bills`
- `agent_stats`
- `events`

数据库特性：

- WAL 模式
- `SetMaxOpenConns(1)`（与 SQLite 并发模型匹配）

## 4.8 ANet 外部集成

`ui/server/anet/client.go` 封装调用本机 ANet 服务：

- status / credits
- transfer
- CAS get/put
- reputation attest
- DM send

DDD 本身主要负责“餐厅域编排与状态”，把资金/身份/内容分发等能力外包给 ANet。

---

## 5. 设计文档与实现差异（重点）

以下是背景参考时最容易踩坑的地方：

- 文档端口常写 `8080`，代码默认是 `9000`
- 文档里有些认证描述是 Bearer，但 DDD 实际对客户端看的是 `X-Agent-DID`
- 文档提到的一些 ANet 事件/能力在代码中未完全广播实现
- 前端 `display-demo` 当前主要吃 `qr-gui` 队列，不是直接接 DDD API
- 详情页实时快照链路接线不完整（有读接口但主线写入不足）

建议把 `ui/docs` 视为“目标规格”，把 `ui/server` 视为“当前真实实现”。

---

## 6. 对 yinanping-studio 的背景借鉴建议

## 6.1 可直接借鉴

- `runtime + network` 分层：把“业务状态”和“可视化状态”拆开
- 队列桥设计：用统一播放编排器承接异步话题（回放、插队、完结回调）
- 头像双路径：真人图优先 + 自动 fallback
- 统一错误对象：`error/message/suggestion`，利于调试与 AI 纠错
- WS 事件落库：线上问题可追溯、可回放

## 6.2 需谨慎迁移

- 不要直接照抄文档认证方式，必须按代码真实协议适配
- DDD + ANet 是 Go 生态，与你当前 Node API 的整合成本较高
- 支付/确认流程在示例实现中偏 Demo 安全等级，上线需强化校验

## 6.3 建议迁移路径

1. 先借前端架构思想（runtime/queue/network/avatar），不强绑定 Go DDD
2. 在现有 `apps/api` 里补“统一错误对象 + 事件日志”
3. 再考虑是否引入独立 WS 通道，替代当前纯 SSE 单链路

---

## 7. 关键文件索引（便于二次查阅）

前端关键：

- `AgentNetwork-Red-master/display-demo/src/main.js`
- `AgentNetwork-Red-master/display-demo/src/socialNetwork.js`
- `AgentNetwork-Red-master/display-demo/src/runtime.js`
- `AgentNetwork-Red-master/display-demo/src/queueBridge.js`
- `AgentNetwork-Red-master/display-demo/src/avatarSystem.js`
- `AgentNetwork-Red-master/display-demo/src/detail.js`
- `AgentNetwork-Red-master/display-demo/src/themes.js`

后端关键：

- `AgentNetwork-Red-master/cmd/dddserver/main.go`
- `AgentNetwork-Red-master/ui/server/server.go`
- `AgentNetwork-Red-master/ui/server/auth.go`
- `AgentNetwork-Red-master/ui/server/ws.go`
- `AgentNetwork-Red-master/ui/server/handlers_*.go`
- `AgentNetwork-Red-master/ui/server/store/store.go`
- `AgentNetwork-Red-master/ui/server/store/queries.go`
- `AgentNetwork-Red-master/ui/server/anet/client.go`
- `AgentNetwork-Red-master/ui/docs/api-design.md`
- `AgentNetwork-Red-master/ui/docs/ui-design.md`

---

## 8. 一句话总结

`AgentNetwork-Red-master` 的价值不在“可直接整包复用”，而在它清晰展示了“运行时状态机 + 队列驱动回放 + D3 网络可视化 + 领域 API + 事件广播”的组合模式；对 `yinanping-studio` 最适合的是吸收其架构思路和接口组织方式，再按现有 Node/SSE 技术栈做本地化实现。

