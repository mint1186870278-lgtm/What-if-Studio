import fs from "node:fs/promises";
import path from "node:path";

const apiBase = String(process.env.API_BASE || "http://localhost:3567").trim();
const token = String(process.env.GATEWAY_TOKEN || "agent-network-demo-token");
const reportDir = path.resolve(process.cwd(), "tmp-reports");

async function invoke(body) {
  const res = await fetch(`${apiBase}/api/gateway/invoke`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Gateway-Token": token
    },
    body: JSON.stringify(body)
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(json?.error?.message || `invoke failed: ${res.status}`);
  }
  return json;
}

async function listInvocations(limit = 8) {
  const res = await fetch(`${apiBase}/api/gateway/invocations?limit=${limit}`);
  const json = await res.json();
  return Array.isArray(json?.invocations) ? json.invocations : [];
}

async function main() {
  const session = {
    sessionId: `chaos-${Date.now()}`,
    workTitle: "Agent Network Chaos Demo",
    endingDirection: "主服务故障后仍能自动回退并交付可解释结果",
    stylePreference: "warmHealing",
    sourceVideoPath: ""
  };

  const scenarios = [];

  const s1 = await invoke({
    capabilityId: "production.plan",
    caller: "smoke.gateway",
    input: { session }
  });
  scenarios.push({
    name: "跨服务编排能力",
    status: s1.ok ? "PASS" : "FAIL",
    detail: `timelineTurns=${s1?.result?.plan?.timelineTurns || 0}`
  });

  const s2 = await invoke({
    capabilityId: "soundtrack.suggest",
    caller: "smoke.gateway",
    input: {
      session,
      stylePreference: session.stylePreference,
      endingDirection: session.endingDirection,
      forceFail: true
    },
    options: {
      retries: 1,
      fallbackCapabilityId: "production.plan"
    }
  });
  scenarios.push({
    name: "失败降级与替代服务",
    status: s2?.audit?.fallbackFromCapabilityId ? "PASS" : "FAIL",
    detail: `fallbackFrom=${s2?.audit?.fallbackFromCapabilityId || "none"}`
  });

  let failedByDesign = false;
  try {
    await invoke({
      capabilityId: "capability.not.exists",
      caller: "smoke.gateway",
      input: {}
    });
  } catch (_error) {
    failedByDesign = true;
  }
  scenarios.push({
    name: "未知能力失败保护",
    status: failedByDesign ? "PASS" : "FAIL",
    detail: "unknown capability should fail safely"
  });

  const latestInvocations = await listInvocations(12);
  const markdown = [
    "# Gateway Chaos Smoke Report",
    "",
    `- generatedAt: ${new Date().toISOString()}`,
    `- apiBase: ${apiBase}`,
    "",
    "## Scenarios",
    ...scenarios.map((item) => `- ${item.name}: ${item.status} (${item.detail})`),
    "",
    "## Latest Invocations",
    ...latestInvocations.map(
      (item) =>
        `- ${item.createdAt} | ${item.caller} -> ${item.targetServiceId} / ${item.capabilityId} | ${item.status} | ${item.durationMs}ms`
    )
  ].join("\n");

  await fs.mkdir(reportDir, { recursive: true });
  const reportPath = path.join(reportDir, "gateway-chaos-report.md");
  await fs.writeFile(reportPath, `${markdown}\n`, "utf8");
  console.log(`gateway smoke report: ${reportPath}`);

  if (scenarios.some((item) => item.status !== "PASS")) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

