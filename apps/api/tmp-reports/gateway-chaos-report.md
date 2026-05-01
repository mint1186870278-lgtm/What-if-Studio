# Gateway Chaos Smoke Report

- generatedAt: 2026-04-30T09:11:22.393Z
- apiBase: http://localhost:3567

## Scenarios
- 跨服务编排能力: PASS (timelineTurns=19)
- 失败降级与替代服务: PASS (fallbackFrom=soundtrack.suggest)
- 未知能力失败保护: PASS (unknown capability should fail safely)

## Latest Invocations
- 2026-04-30T09:11:22.385Z | smoke.gateway -> orchestrator-hub / production.plan | ok | 0ms
- 2026-04-30T09:11:22.385Z | orchestrator-hub -> audio-lab / soundtrack.suggest | ok | 0ms
- 2026-04-30T09:11:22.385Z | orchestrator-hub -> director-brain / discussion.generateTimeline | ok | 0ms
- 2026-04-30T09:11:22.372Z | smoke.gateway -> orchestrator-hub / production.plan | ok | 1ms
- 2026-04-30T09:11:22.371Z | orchestrator-hub -> audio-lab / soundtrack.suggest | ok | 0ms
- 2026-04-30T09:11:22.371Z | orchestrator-hub -> director-brain / discussion.generateTimeline | ok | 0ms
- 2026-04-30T09:10:53.216Z | smoke.gateway -> unresolved / discussion.generateTimeline | failed | 1ms
- 2026-04-30T09:10:53.199Z | smoke.gateway -> orchestrator-hub / production.plan | ok | 2ms
- 2026-04-30T09:10:53.199Z | orchestrator-hub -> audio-lab / soundtrack.suggest | ok | 0ms
- 2026-04-30T09:10:53.199Z | orchestrator-hub -> director-brain / discussion.generateTimeline | ok | 2ms
