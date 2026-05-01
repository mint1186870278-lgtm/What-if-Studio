const envBase = String(import.meta.env.VITE_API_BASE || "").trim();
const inferredBase =
  typeof window !== "undefined" ? `${window.location.protocol}//${window.location.hostname}:3567` : "http://localhost:3567";
const API_BASE = envBase || inferredBase;

async function parseApiError(res, fallbackMessage) {
  try {
    const data = await res.json();
    if (data?.error?.message) return data.error.message;
    if (data?.error && typeof data.error === "string") return data.error;
    if (data?.message) return data.message;
  } catch (_error) {
    // Ignore non-JSON error responses and fall back to generic text.
  }
  return fallbackMessage;
}

export async function createSession(payload) {
  const res = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error(await parseApiError(res, "创建会话失败"));
  return res.json();
}

export async function streamDiscussion(sessionId, onTurn) {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/discussion/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" }
  });
  if (!res.ok || !res.body) {
    throw new Error(await parseApiError(res, "讨论流打开失败"));
  }

  const decoder = new TextDecoder();
  const reader = res.body.getReader();
  let buffer = "";

  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const raw of events) {
      const line = raw.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6));
      onTurn(payload);
    }
  }
}

export async function createVideoJob(sessionId, sourceVideoPath) {
  const res = await fetch(`${API_BASE}/api/video-jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId, sourceVideoPath })
  });
  if (!res.ok) throw new Error(await parseApiError(res, "视频任务创建失败"));
  return res.json();
}

export async function fetchAgents() {
  const res = await fetch(`${API_BASE}/api/agents`);
  if (!res.ok) throw new Error(await parseApiError(res, "角色列表加载失败"));
  const data = await res.json();
  return Array.isArray(data?.agents) ? data.agents : [];
}

export function watchVideoJob(jobId, onEvent) {
  const source = new EventSource(`${API_BASE}/api/video-jobs/${jobId}/events`);
  source.addEventListener("job-event", (event) => {
    onEvent(JSON.parse(event.data));
  });
  source.addEventListener("complete", (event) => {
    onEvent(JSON.parse(event.data));
    source.close();
  });
  source.onerror = () => {
    onEvent({ event: "error", message: "任务事件流中断，请稍后重试。" });
    source.close();
  };
  return () => source.close();
}

export async function fetchGatewayCapabilities() {
  const res = await fetch(`${API_BASE}/api/gateway/capabilities`);
  if (!res.ok) throw new Error(await parseApiError(res, "能力列表加载失败"));
  const data = await res.json();
  return Array.isArray(data?.capabilities) ? data.capabilities : [];
}

export async function fetchGatewayInvocations(limit = 24) {
  const res = await fetch(`${API_BASE}/api/gateway/invocations?limit=${limit}`);
  if (!res.ok) throw new Error(await parseApiError(res, "调用日志加载失败"));
  const data = await res.json();
  return Array.isArray(data?.invocations) ? data.invocations : [];
}

export function watchGatewayInvocations(onEvent) {
  const source = new EventSource(`${API_BASE}/api/gateway/invocations/events`);
  source.addEventListener("invocation", (event) => {
    onEvent(JSON.parse(event.data));
  });
  source.onerror = () => {
    onEvent({ event: "error", message: "网关调用流中断，正在等待重连。" });
  };
  return () => source.close();
}
