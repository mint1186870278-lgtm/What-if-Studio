import fs from "node:fs/promises";
import path from "node:path";
import { startVideoJob, subscribeJob } from "../src/videoPipeline.js";

const reportDir = path.resolve(process.cwd(), "tmp-reports");

function waitForJob(jobId) {
  return new Promise((resolve) => {
    const events = [];
    const unsubscribe = subscribeJob(jobId, (payload) => {
      events.push(payload);
      if (payload.event === "complete") {
        unsubscribe();
        resolve({ events, result: payload.result, artifacts: payload.artifacts || [] });
      }
    });
  });
}

async function runScenario(name, session, expectedCheck) {
  const job = await startVideoJob(session);
  const completed = await waitForJob(job.jobId);
  const progressLines = completed.events
    .filter((item) => item.event === "progress")
    .map((item) => `${item.phase}: ${item.message}`);
  const passed = expectedCheck({ result: completed.result, progressLines });
  return {
    name,
    jobId: job.jobId,
    resultType: completed.result?.type || "unknown",
    resultText: completed.result?.text || "",
    progressLines,
    passed
  };
}

async function main() {
  const smokeVideoPath = String(process.env.SMOKE_VIDEO_PATH || "").trim();
  const report = [];
  const restoreIopho = process.env.IOPHO_SCRIPT_PATH;
  const now = Date.now();

  if (smokeVideoPath) {
    report.push(
      await runScenario(
        "正常素材路径",
        {
          sessionId: `smoke-normal-${now}`,
          workTitle: "Smoke Normal",
          endingDirection: "正常链路验证",
          stylePreference: "auto",
          sourceVideoPath: smokeVideoPath
        },
        ({ result }) => String(result?.type || "").startsWith("video-mp4")
      )
    );
  } else {
    report.push({
      name: "正常素材路径",
      skipped: true,
      reason: "未设置 SMOKE_VIDEO_PATH，跳过该场景"
    });
  }

  if (smokeVideoPath) {
    process.env.IOPHO_SCRIPT_PATH = "Z:/missing/video_to_storyboard.py";
    report.push(
      await runScenario(
        "素材存在但分镜脚本失败",
        {
          sessionId: `smoke-analyze-fallback-${now}`,
          workTitle: "Smoke Analyze Fallback",
          endingDirection: "验证分析回退",
          stylePreference: "auto",
          sourceVideoPath: smokeVideoPath
        },
        ({ result, progressLines }) =>
          String(result?.type || "").startsWith("video-mp4") &&
          progressLines.some((line) => line.includes("分析脚本不可用"))
      )
    );
  } else {
    report.push({
      name: "素材存在但分镜脚本失败",
      skipped: true,
      reason: "未设置 SMOKE_VIDEO_PATH，跳过该场景"
    });
  }

  if (typeof restoreIopho === "string") {
    process.env.IOPHO_SCRIPT_PATH = restoreIopho;
  } else {
    delete process.env.IOPHO_SCRIPT_PATH;
  }
  report.push(
    await runScenario(
      "素材路径错误",
      {
        sessionId: `smoke-invalid-path-${now}`,
        workTitle: "Smoke Invalid Path",
        endingDirection: "验证错误路径回退",
        stylePreference: "auto",
        sourceVideoPath: "Z:/this/path/does/not/exist.mp4"
      },
      ({ result, progressLines }) =>
        result?.type === "placeholder" &&
        progressLines.some((line) => line.includes("素材路径不可用"))
    )
  );

  const markdownLines = [
    "# Video Pipeline Smoke Report",
    "",
    `- generatedAt: ${new Date().toISOString()}`,
    "",
    "## Scenarios"
  ];

  for (const item of report) {
    if (item.skipped) {
      markdownLines.push(`- ${item.name}: SKIPPED (${item.reason})`);
      continue;
    }
    markdownLines.push(`- ${item.name}: ${item.passed ? "PASS" : "FAIL"} (resultType=${item.resultType})`);
    markdownLines.push(`  - jobId: ${item.jobId}`);
    markdownLines.push(`  - resultText: ${item.resultText}`);
    for (const line of item.progressLines) {
      markdownLines.push(`  - progress: ${line}`);
    }
  }

  const hasFailure = report.some((item) => !item.skipped && !item.passed);
  await fs.mkdir(reportDir, { recursive: true });
  const reportPath = path.join(reportDir, "video-smoke-report.md");
  await fs.writeFile(reportPath, `${markdownLines.join("\n")}\n`, "utf8");
  console.log(`video smoke report: ${reportPath}`);
  if (hasFailure) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
