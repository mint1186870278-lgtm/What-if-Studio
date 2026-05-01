import fs from "node:fs/promises";
import path from "node:path";
import {
  generateDiscussionTimeline,
  generateTemplateDiscussionTimeline
} from "../src/discussionEngine.js";
import { generateDistilledDiscussionTimeline } from "../src/distilledDiscussionEngine.js";

const rootDir = path.resolve(process.cwd());
const datasetPath = path.join(rootDir, "data", "distill-dataset.json");
const reportDir = path.join(rootDir, "tmp-reports");

function scoreTimeline(session, timeline, referenceBullets) {
  const turns = timeline.filter((item) => item.event === "turn");
  const summaries = timeline.filter((item) => item.event === "summary");
  const finalTurn = turns.at(-1)?.content || "";
  const contentBlob = timeline.map((item) => item.content || item.goal || "").join("\n");

  const agendaScore = ["topic-1", "topic-2", "topic-3", "finalize"].every((stage) =>
    timeline.some((item) => item.stage === stage)
  )
    ? 100
    : 60;

  const executionKeywords = ["镜头", "剪辑", "交付", "节奏"];
  const executionHits = executionKeywords.filter((kw) => contentBlob.includes(kw)).length;
  const executionScore = Math.min(100, 40 + executionHits * 15);

  const referenceHits = referenceBullets.filter((item) => contentBlob.includes(item)).length;
  const referenceScore = Math.round((referenceHits / Math.max(referenceBullets.length, 1)) * 100);

  const endingScore = finalTurn.includes(session.endingDirection.slice(0, 6)) || contentBlob.includes(session.endingDirection)
    ? 100
    : 65;

  const brevityScore = turns.length >= 8 && summaries.length >= 3 ? 100 : 70;
  const total = Math.round((agendaScore + executionScore + referenceScore + endingScore + brevityScore) / 5);

  return {
    total,
    metrics: {
      agendaScore,
      executionScore,
      referenceScore,
      endingScore,
      brevityScore
    }
  };
}

function summarize(items, key) {
  const values = items.map((item) => item[key]).filter((v) => Number.isFinite(v));
  if (!values.length) return 0;
  return Math.round(values.reduce((sum, cur) => sum + cur, 0) / values.length);
}

async function main() {
  const raw = await fs.readFile(datasetPath, "utf8");
  const dataset = JSON.parse(raw);
  if (!Array.isArray(dataset) || !dataset.length) {
    throw new Error("distill dataset is empty");
  }

  const results = [];
  for (const item of dataset) {
    const templateTimeline = generateTemplateDiscussionTimeline(item.session);
    const distilledTimeline = generateDistilledDiscussionTimeline(item.session);
    const onlineTimeline = generateDiscussionTimeline(item.session);

    const templateScore = scoreTimeline(item.session, templateTimeline, item.referenceBullets);
    const distilledScore = scoreTimeline(item.session, distilledTimeline, item.referenceBullets);
    const onlineScore = scoreTimeline(item.session, onlineTimeline, item.referenceBullets);

    results.push({
      id: item.id,
      session: item.session,
      template: templateScore,
      distilled: distilledScore,
      online: onlineScore
    });
  }

  const summary = {
    datasetSize: results.length,
    templateAverage: summarize(results.map((r) => r.template), "total"),
    distilledAverage: summarize(results.map((r) => r.distilled), "total"),
    onlineAverage: summarize(results.map((r) => r.online), "total"),
    improvedSamples: results.filter((r) => r.distilled.total >= r.template.total).length
  };

  const timestamp = new Date().toISOString().replaceAll(":", "-");
  await fs.mkdir(reportDir, { recursive: true });
  const reportJsonPath = path.join(reportDir, `distill-eval-${timestamp}.json`);
  const reportMdPath = path.join(reportDir, "distill-eval-latest.md");
  await fs.writeFile(
    reportJsonPath,
    JSON.stringify(
      {
        generatedAt: new Date().toISOString(),
        summary,
        results
      },
      null,
      2
    ),
    "utf8"
  );

  const md = [
    "# Distill Eval Report",
    "",
    `- generatedAt: ${new Date().toISOString()}`,
    `- datasetSize: ${summary.datasetSize}`,
    `- templateAverage: ${summary.templateAverage}`,
    `- distilledAverage: ${summary.distilledAverage}`,
    `- onlineAverage: ${summary.onlineAverage}`,
    `- improvedSamples: ${summary.improvedSamples}/${summary.datasetSize}`,
    "",
    "## Top Samples",
    ...results.slice(0, 8).map(
      (r) =>
        `- ${r.id}: template=${r.template.total}, distilled=${r.distilled.total}, online=${r.online.total}`
    ),
    "",
    `Full JSON: ${reportJsonPath}`
  ].join("\n");
  await fs.writeFile(reportMdPath, md, "utf8");
  console.log(`distill eval done: ${reportJsonPath}`);
  console.log(`distill eval summary: ${reportMdPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
