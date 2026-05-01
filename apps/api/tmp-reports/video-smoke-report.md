# Video Pipeline Smoke Report

- generatedAt: 2026-04-27T13:11:38.133Z

## Scenarios
- 正常素材路径: PASS (resultType=video-mp4)
  - jobId: job-x2fibb
  - resultText: 已输出真实 mp4：E:\10.竞赛\南客松\前端\yinanping-studio\apps\api\tmp-artifacts\job-x2fibb\output.mp4
  - progress: analyze: 开始执行视频分析脚本。
  - progress: collect: 素材侦探已接入真实素材并生成预览工件。
  - progress: analyze: 分析脚本不可用，回退占位产物：Traceback (most recent call last):
  File "E:\10.����\�Ͽ���\ǰ��\iopho-skills-main\skills\iopho-analyzing-videos\scripts\video_to_storyboard.py", line 14, in <module>
    import google.generativeai as genai
ModuleNotFoundError: No module named 'google'

  - progress: discuss: 导演组确认镜头顺序。
  - progress: edit: 剪辑师生成短片剪辑方案。
  - progress: render: 配乐师与渲染节点正在导出 mp4。
  - progress: render: 真实 mp4 输出成功。
- 素材存在但分镜脚本失败: PASS (resultType=video-mp4)
  - jobId: job-yizptc
  - resultText: 已输出真实 mp4：E:\10.竞赛\南客松\前端\yinanping-studio\apps\api\tmp-artifacts\job-yizptc\output.mp4
  - progress: analyze: 开始执行视频分析脚本。
  - progress: collect: 素材侦探已接入真实素材并生成预览工件。
  - progress: analyze: 分析脚本不可用，回退占位产物：python: can't open file 'Z:\\missing\\video_to_storyboard.py': [Errno 2] No such file or directory

  - progress: discuss: 导演组确认镜头顺序。
  - progress: edit: 剪辑师生成短片剪辑方案。
  - progress: render: 配乐师与渲染节点正在导出 mp4。
  - progress: render: 真实 mp4 输出成功。
- 素材路径错误: PASS (resultType=placeholder)
  - jobId: job-uvwf1t
  - resultText: 《Smoke Invalid Path》HE版占位成片
结局方向：验证错误路径回退
说明：当前未接入真实视频渲染，已跑通任务闭环。
  - progress: analyze: 开始执行视频分析脚本。
  - progress: collect: 素材路径不可用，回退占位产物：ENOENT: no such file or directory, access 'Z:\this\path\does\not\exist.mp4'
  - progress: analyze: 未检测到可读素材，跳过分镜分析。
  - progress: discuss: 导演组确认镜头顺序。
  - progress: edit: 剪辑师生成短片剪辑方案。
  - progress: render: 配乐师与渲染节点正在导出 mp4。
