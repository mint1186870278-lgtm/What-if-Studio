# iopho-skills-main 参考说明文档（用于 yinanping-studio 背景参考）

## 1. 文档目的

本文件用于给当前 `yinanping-studio` 提供 `iopho` 体系的背景参考。  
你当前工作区中与 iopho 对应的仓库是：

- `e:/10.竞赛/南客松/前端/iopho-skills-main`

该仓库核心是 **AI Agent Skills 能力库**，并非传统 Web 前端/后端工程。本文按“可落地迁移”角度整理其结构与能力。

---

## 2. 仓库定位与边界

`iopho-skills-main` 的本质是：

- 一组供 Cursor/Claude/Windsurf 等 Agent 复用的 `SKILL.md` 能力定义
- 以“视频生产流程”为核心场景（从上下文、参考片、分镜、录屏、TTS、音频到 QA）
- 通过外部 CLI/MCP 执行实际动作（下载、分析、生成、混音），仓库本身更多是“流程与策略层”

不是它的职责：

- 不提供可直接启动的前端界面（无 `src/*.tsx`、`apps/web` 等）
- 不提供可直接运行的 API 服务（无 Express/FastAPI/Go server 主体）

---

## 3. 目录结构说明

核心目录：

- `iopho-skills-main/README.md`
- `iopho-skills-main/README.zh-CN.md`
- `iopho-skills-main/skills/*`

`skills` 下主要能力分组：

- `iopho-video-director`：总编排技能（Phase 0-3）
- `iopho-product-context`：产品上下文采集与 `context.md` 生成
- `iopho-searching-videos`：视频检索
- `iopho-getting-videos`：视频/字幕/元数据拉取
- `iopho-analyzing-videos`：视频逆向为 storyboard（含 Python 脚本）
- `iopho-recording-checklist`：录屏执行清单
- `iopho-voiceover-tts`：旁白生成与时间轴拼接
- `iopho-audio-director`：音频策略与混音总控
- `iopho-seedance-prompts`：即梦 Seedance 提示词工程

另有非 iopho 前缀技能（如 `reedle`、`wribble`、`pnote`），用于内容侧工具协作。

---

## 4. “前端/后端”视角下的解读

## 4.1 前端层（在此仓库中的对应物）

严格来说，本仓库没有传统 UI 前端。  
若必须映射“前端角色”，可理解为：

- **Agent 交互层**：通过 `SKILL.md` 指导 Agent 与用户交互提问、收集参数、组织输出文档
- **产物模板层**：通过 `templates/*.md` 标准化用户可见产物（如 project-plan、checklist、context）

也就是说，它解决的是“智能工作流前台体验与结构化输出”，不是浏览器页面渲染。

## 4.2 后端层（在此仓库中的对应物）

同样没有传统 API 后端。  
可映射为“后端能力编排”的是：

- 技能定义的工具路由（调用外部 CLI/MCP）
- 工作流的阶段依赖与输入输出契约
- 参考资料与规则（`references/*.md`）

实际执行仍依赖外部系统（例如 yt-dlp、FFmpeg、TTS 引擎、LLM API）。

---

## 5. 核心技能体系（详细）

## 5.1 `iopho-video-director`（总控）

职责：

- 统一调度四阶段：Context -> Storyboard -> Production -> Visual QA
- 支持 `new` / `continue` / `jump` 三种入口
- 输出项目文件骨架与阶段断点

价值：

- 把分散技能串成可持续推进的“项目管线”
- 适合比赛场景里多人协作与任务接力

## 5.2 `iopho-product-context`

职责：

- 通过问答或扫描现有文档生成 `context.md`
- 抽取产品定位、目标受众、平台、品牌约束、禁忌内容

价值：

- 作为后续所有制作技能的“单一事实源”
- 降低口径漂移（文案、镜头、音频风格不一致）

## 5.3 `searching/getting/analyzing videos`（研究链）

### searching

- 做“查找”，不做下载
- 返回结构化候选列表（平台、时长、URL 等）

### getting

- 负责真正下载媒体/字幕/元信息
- 提供多工具回退策略

### analyzing

- 把视频逆向成 `.storyboard.md`
- 可输出逐场景关键帧
- 是“参考片 -> 可编辑分镜蓝图”的关键桥梁

## 5.4 `iopho-recording-checklist`

职责：

- 将分镜转成可执行录屏清单（逐镜任务、设备参数、录前/录后检查）

价值：

- 明显降低实机录制返工率
- 适合你们这种“需要演示成片”的比赛节奏

## 5.5 `iopho-voiceover-tts`

职责：

- 多引擎 TTS 生成
- 片段拼接为主 VO，并生成时间轴位置文件

价值：

- 让旁白可工程化落地，不靠手动逐段对齐
- 易于接你们当前视频管线

## 5.6 `iopho-audio-director`

职责：

- 先做音频方案（BGM、SFX、ducking、情绪曲线）
- 再做终混（LUFS 目标等）

价值：

- 将“音频像产品片”从经验变为流程

## 5.7 `iopho-seedance-prompts`

职责：

- 输出 Seedance 2.0 可用提示词与素材引用规范
- 约束时长/素材类型/中文 prompt 策略

价值：

- 可用于缺镜头时的生成补齐（B-roll、转场等）

---

## 6. 与当前 yinanping-studio 的结合建议

## 6.1 可直接借鉴

- **流程分层**：将“任务编排”和“执行实现”分离
- **产物标准化**：固定 `context.md`、`storyboard.md`、`audio-plan.md` 等中间产物
- **工具路由策略**：主路径 + 回退路径（失败时不阻塞）
- **阶段闸门**：每阶段结束做检查，减少后期返工

## 6.2 在你们项目中的映射建议

- `apps/web`：继续承担交互与可视化展示
- `apps/api`：吸收 iopho 的“编排思想”，引入阶段化任务结构
- `public/mock`/配置层：对齐 iopho 中间产物字段（可先 mock）

## 6.3 快速落地顺序（建议）

1. 先建立 `context` + `storyboard` 的最小模板
2. 接入“检索 -> 获取 -> 分析”的简化链路（哪怕先半自动）
3. 增加 `voiceover + audio-plan` 两个中间产物
4. 最后再接生成式补镜（Seedance）与完整 QA

---

## 7. 关键文件索引

- `e:/10.竞赛/南客松/前端/iopho-skills-main/README.md`
- `e:/10.竞赛/南客松/前端/iopho-skills-main/README.zh-CN.md`
- `e:/10.竞赛/南客松/前端/iopho-skills-main/skills/iopho-video-director/SKILL.md`
- `e:/10.竞赛/南客松/前端/iopho-skills-main/skills/iopho-product-context/SKILL.md`
- `e:/10.竞赛/南客松/前端/iopho-skills-main/skills/iopho-searching-videos/SKILL.md`
- `e:/10.竞赛/南客松/前端/iopho-skills-main/skills/iopho-getting-videos/SKILL.md`
- `e:/10.竞赛/南客松/前端/iopho-skills-main/skills/iopho-analyzing-videos/SKILL.md`
- `e:/10.竞赛/南客松/前端/iopho-skills-main/skills/iopho-analyzing-videos/scripts/video_to_storyboard.py`
- `e:/10.竞赛/南客松/前端/iopho-skills-main/skills/iopho-recording-checklist/SKILL.md`
- `e:/10.竞赛/南客松/前端/iopho-skills-main/skills/iopho-voiceover-tts/SKILL.md`
- `e:/10.竞赛/南客松/前端/iopho-skills-main/skills/iopho-audio-director/SKILL.md`
- `e:/10.竞赛/南客松/前端/iopho-skills-main/skills/iopho-seedance-prompts/SKILL.md`

---

## 8. 总结

`iopho-skills-main` 不是“前端 + 后端应用源码”，而是“视频生产智能体工作流系统”的知识与编排层。  
对 `yinanping-studio` 的最大价值，是它把复杂创作流程拆成可协作、可复用、可检查的阶段化能力，这一点非常适合作为你们后续迭代的流程蓝本。

