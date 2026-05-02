# whatif-studio

面向「意难平重剪」场景的全栈项目：FastAPI 后端 + Vite 前端。

## 使用 uv 启动后端

1. 安装依赖
```bash
uv sync
```

2. 启动 API
```bash
uv run uvicorn src.main:app --reload
```

3. 访问
- API: `http://127.0.0.1:8000`
- 前端（已 build 后由后端托管）: `http://127.0.0.1:8000`

## Build 前端

```bash
cd web
npm install
npm run build
```

构建产物在 `web/dist`，后端会自动托管该目录。

## 说明

项目架构、模块划分、业务流程与 ANet/AutoGen 职责边界详见 [AGENTS.md](/d:/Projects/What-if.studio/AGENTS.md)。
