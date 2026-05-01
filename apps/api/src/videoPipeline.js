import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { createVideoJob } from "@yinanping/contracts";

const pipelineEvents = new EventEmitter();
const jobs = new Map();
const ARTIFACT_ROOT = path.resolve(process.cwd(), "tmp-artifacts");
const DEFAULT_CLIP_SECONDS = Number(process.env.DEMO_CLIP_SECONDS || 20);

function emitProgress(jobId, phase, message) {
  pipelineEvents.emit(jobId, { event: "progress", phase, message, ts: Date.now() });
}

function resolveIophoScript() {
  if (process.env.IOPHO_SCRIPT_PATH) return process.env.IOPHO_SCRIPT_PATH;
  return path.resolve(
    process.cwd(),
    "..",
    "..",
    "..",
    "iopho-skills-main",
    "skills",
    "iopho-analyzing-videos",
    "scripts",
    "video_to_storyboard.py"
  );
}

async function runAnalyzeScript(sourceVideoPath, outputDir) {
  const scriptPath = resolveIophoScript();
  const outputFile = path.join(outputDir, "storyboard.md");
  await fs.mkdir(outputDir, { recursive: true });

  return new Promise((resolve, reject) => {
    const python = spawn("python", [scriptPath, sourceVideoPath, outputFile], {
      env: process.env
    });
    let stderr = "";
    python.stderr.on("data", (buf) => {
      stderr += String(buf);
    });
    python.on("exit", (code) => {
      if (code === 0) {
        resolve(outputFile);
      } else {
        reject(new Error(stderr || `video_to_storyboard.py exited with ${code}`));
      }
    });
    python.on("error", reject);
  });
}

async function copySourceVideoArtifact(sourceVideoPath, outputDir, title) {
  const parsed = path.parse(sourceVideoPath);
  const ext = parsed.ext || ".mp4";
  const targetPath = path.join(outputDir, `source-preview${ext}`);
  await fs.copyFile(sourceVideoPath, targetPath);
  return {
    type: "video-source",
    title: `${title} 原始素材预览`,
    path: targetPath,
    text: `已接入真实素材：${targetPath}`
  };
}

function runCommand(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, options);
    let stderr = "";
    child.stderr?.on("data", (buf) => {
      stderr += String(buf);
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(stderr || `${command} exited with ${code}`));
      }
    });
  });
}

async function renderShortMp4(sourceVideoPath, outputPath) {
  await runCommand(
    "ffmpeg",
    [
      "-y",
      "-i",
      sourceVideoPath,
      "-t",
      String(DEFAULT_CLIP_SECONDS),
      "-vf",
      "scale=1280:-2",
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-crf",
      "24",
      "-c:a",
      "aac",
      "-b:a",
      "128k",
      "-movflags",
      "+faststart",
      outputPath
    ],
    { env: process.env }
  );
}

async function fallbackCopyAsMp4(sourceVideoPath, outputPath) {
  await fs.copyFile(sourceVideoPath, outputPath);
}

async function writePlaceholderArtifact(sessionId, summary) {
  await fs.mkdir(ARTIFACT_ROOT, { recursive: true });
  const filename = `${sessionId}-${Date.now()}.txt`;
  const artifactPath = path.join(ARTIFACT_ROOT, filename);
  await fs.writeFile(artifactPath, summary, "utf8");
  return artifactPath;
}

export function subscribeJob(jobId, listener) {
  pipelineEvents.on(jobId, listener);
  return () => pipelineEvents.off(jobId, listener);
}

export function getJob(jobId) {
  return jobs.get(jobId);
}

export function listArtifactRoot() {
  return ARTIFACT_ROOT;
}

export async function startVideoJob(session) {
  const raw = {
    jobId: `job-${Math.random().toString(36).slice(2, 8)}`,
    sessionId: session.sessionId,
    phase: "collect",
    status: "pending",
    artifacts: [],
    error: ""
  };
  const job = createVideoJob(raw);
  jobs.set(job.jobId, job);

  queueMicrotask(async () => {
    try {
      job.status = "running";
      emitProgress(job.jobId, "collect", "素材侦探整理参考素材完成。");
      await new Promise((r) => setTimeout(r, 700));

      job.phase = "analyze";
      emitProgress(job.jobId, "analyze", "开始执行视频分析脚本。");
      await new Promise((r) => setTimeout(r, 700));

      let artifact;
      let storyboardArtifact = null;
      let sourcePathReadable = false;
      if (session.sourceVideoPath) {
        const outputDir = path.join(ARTIFACT_ROOT, job.jobId);
        await fs.mkdir(outputDir, { recursive: true });
        try {
          await fs.access(session.sourceVideoPath);
          sourcePathReadable = true;
          artifact = await copySourceVideoArtifact(session.sourceVideoPath, outputDir, session.workTitle);
          emitProgress(job.jobId, "collect", "素材侦探已接入真实素材并生成预览工件。");
        } catch (error) {
          emitProgress(job.jobId, "collect", `素材路径不可用，回退占位产物：${error.message}`);
        }
        if (sourcePathReadable) {
          try {
            const storyboardPath = await runAnalyzeScript(session.sourceVideoPath, outputDir);
            storyboardArtifact = {
              type: "storyboard",
              title: `${session.workTitle} 分镜分析`,
              path: storyboardPath,
              text: `已生成分镜文件：${storyboardPath}`
            };
            if (!artifact) artifact = storyboardArtifact;
            emitProgress(job.jobId, "analyze", "iopho 分镜分析完成。");
          } catch (error) {
            emitProgress(job.jobId, "analyze", `分析脚本不可用，回退占位产物：${error.message}`);
          }
        } else {
          emitProgress(job.jobId, "analyze", "未检测到可读素材，跳过分镜分析。");
        }
      }

      job.phase = "discuss";
      emitProgress(job.jobId, "discuss", "导演组确认镜头顺序。");
      await new Promise((r) => setTimeout(r, 700));

      job.phase = "edit";
      emitProgress(job.jobId, "edit", "剪辑师生成短片剪辑方案。");
      await new Promise((r) => setTimeout(r, 700));

      job.phase = "render";
      emitProgress(job.jobId, "render", "配乐师与渲染节点正在导出 mp4。");
      await new Promise((r) => setTimeout(r, 700));

      if (sourcePathReadable && session.sourceVideoPath) {
        const outputDir = path.join(ARTIFACT_ROOT, job.jobId);
        const outputMp4Path = path.join(outputDir, "output.mp4");
        try {
          await renderShortMp4(session.sourceVideoPath, outputMp4Path);
          artifact = {
            type: "video-mp4",
            title: `${session.workTitle} · Demo短片`,
            path: outputMp4Path,
            text: `已输出真实 mp4：${outputMp4Path}`
          };
          emitProgress(job.jobId, "render", "真实 mp4 输出成功。");
        } catch (error) {
          emitProgress(job.jobId, "render", `ffmpeg 渲染失败，尝试复制素材作为保底 mp4：${error.message}`);
          try {
            await fallbackCopyAsMp4(session.sourceVideoPath, outputMp4Path);
            artifact = {
              type: "video-mp4-fallback",
              title: `${session.workTitle} · Demo短片(保底)`,
              path: outputMp4Path,
              text: `ffmpeg 不可用，已回退生成保底 mp4：${outputMp4Path}`
            };
            emitProgress(job.jobId, "render", "保底 mp4 生成成功。");
          } catch (copyError) {
            emitProgress(job.jobId, "render", `保底 mp4 生成失败：${copyError.message}`);
          }
        }
      }

      if (!artifact) {
        const textPath = await writePlaceholderArtifact(
          session.sessionId,
          `《${session.workTitle}》HE版占位成片\n结局方向：${session.endingDirection}\n说明：当前未接入真实视频渲染，已跑通任务闭环。`
        );
        artifact = {
          type: "placeholder",
          title: `${session.workTitle} · HE版`,
          path: textPath,
          text: await fs.readFile(textPath, "utf8")
        };
      }

      job.phase = "deliver";
      job.status = "done";
      job.artifacts = storyboardArtifact && storyboardArtifact.path !== artifact.path ? [artifact, storyboardArtifact] : [artifact];
      pipelineEvents.emit(job.jobId, {
        event: "complete",
        result: artifact,
        artifacts: job.artifacts,
        ts: Date.now()
      });
    } catch (error) {
      job.status = "failed";
      job.error = error.message;
      pipelineEvents.emit(job.jobId, {
        event: "complete",
        result: {
          type: "error",
          title: "任务失败",
          text: error.message
        },
        ts: Date.now()
      });
    }
  });

  return job;
}
