<div align="center">

# What-if Studio

### 对结局意难平？让 AI 虚拟剧组替你重拍一个平行宇宙。

<p>
  <a href="#快速开始">快速开始</a> ·
  <a href="#核心体验">核心体验</a> ·
  <a href="#产品亮点">产品亮点</a> ·
  <a href="#路线图">路线图</a>
</p>

![Python](https://img.shields.io/badge/Python-3.10%2B-111111?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-111111?style=for-the-badge&logo=fastapi&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-Frontend-111111?style=for-the-badge&logo=vite&logoColor=white)
![D3](https://img.shields.io/badge/D3-Network%20Stage-111111?style=for-the-badge&logo=d3.js&logoColor=white)
![AutoGen](https://img.shields.io/badge/AutoGen-Multi--Agent-111111?style=for-the-badge)
![ANet](https://img.shields.io/badge/ANet-P2P%20Gateway-111111?style=for-the-badge)

</div>

---

## 一句话

你输入一句话：

> “《哈利波特与凤凰社》我不接受这个结局，小天狼星必须活下来。”

剩下的交给剧组：导演们开会、争吵、提案、分工，最后给你一段可播放的 HE 平行结局短片。

---

## 核心体验

- 不是“工具调用”，而是“围观一个活的剧组”
- 导演 Agent 会自然聚散，不是同时机械开工
- 讨论过程是实时可见的（SSE 流式）
- 成片前可能向你要素材，形成共创闭环
- 成片后直接播放/下载，支持继续重制

---

## 产品亮点

### 多导演协作，而非单模型直出

守门人负责原著精神，执行导演负责风格博弈，制作组负责落地执行。最终不是一段“答案”，而是一场“创作过程”。

### 黑金舞台 + D3 动态剧组网络

全屏网络舞台中，Agent 有“性格”与“兴趣”，会在导演室、摄影棚、剪辑室、录音室之间动态流动，像一个真正的片场生态。

### 真实工程化链路

从 `Project`、`Session` 到 `VideoJob` 的完整后端对象流，带讨论流与任务流双 SSE，前后端都可追踪每一步状态。

### 可对外暴露能力

支持通过 ANet 网关暴露服务，便于被外部 Agent 或系统调用，做成真正可集成的创作能力节点。

---

## 一个典型流程

1. 输入作品名 + 结局方向 + 可选风格偏好
2. 剧组开机，感兴趣导演陆续进入摄影棚
3. 导演讨论实时滚动，你能看到观点冲突
4. 需要素材时弹任务卡，你可上传或跳过
5. 发起视频任务，等待渲染进度
6. 成片弹出播放器，完成分享或二次制作

---

## 快速开始

### 1) 安装后端依赖

```bash
uv sync
```

### 2) 配置环境变量

```bash
cp .env.example .env
```

至少填写：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

### 3) 构建前端

```bash
cd web
npm install
npm run build
cd ..
```

### 4) 启动服务

```bash
uv run uvicorn src.main:app --reload
```

访问：

- App: `http://127.0.0.1:8000`
- API Docs: `http://127.0.0.1:8000/docs`

---

## 技术组合

- Frontend: Vite + Vanilla JS + D3
- Backend: FastAPI + SQLAlchemy + SQLite
- Multi-Agent: AutoGen AgentChat
- Video Pipeline: SiliconFlow Wan T2V（含无 Key 降级）
- Gateway: ANet SDK（可选启用）

---

## 当前已实现

- 项目/素材/会话/任务全链路 API
- 多导演讨论流式输出（SSE）
- 视频任务进度流（SSE）
- 前端网络舞台与 Agent 运行态可视化
- ANet 网关调用与调用事件流

---

## 路线图

- [x] 输入需求 → 多导演讨论 → 成片输出主流程
- [x] 双 SSE（讨论流 + 任务流）
- [ ] 任务卡素材上传体验增强
- [ ] 成片播放器沉浸式视觉升级
- [ ] 导演讨论完整回放与检索

---

## 适合谁

- 想做“剧情重写 / 平行结局”产品的团队
- 需要“多 Agent 协作可视化”示例的开发者
- 想把 AI 从“聊天框”升级到“流程系统”的创作者

---

## 结尾

如果你也有一个“这个结局我不认”的故事，欢迎把它丢给 What-if Studio，让剧组替你拍出来。
