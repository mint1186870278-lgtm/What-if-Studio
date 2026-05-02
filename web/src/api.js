function getViteEnvValue(key) {
  const env = import.meta?.env;
  if (!env || typeof env !== "object") return "";
  return String(env[key] || "").trim();
}

export function resolveApiBase() {
  const envBase = getViteEnvValue("VITE_API_BASE");
  if (envBase) return envBase.replace(/\/+$/, "");
  if (typeof window === "undefined") return "http://localhost:8000";
  // Prefer same-origin /api in browser so dev proxy and production reverse-proxy both work.
  return "";
}

const API_BASE = resolveApiBase();

function joinApiUrl(path) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (!API_BASE) return normalizedPath;
  return `${API_BASE}${normalizedPath}`;
}

function safeParseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function parseSseDataLine(rawEvent) {
  const line = String(rawEvent || "")
    .split("\n")
    .find((item) => item.startsWith("data: "));
  if (!line) return null;
  return safeParseJson(line.slice(6));
}

async function parseApiError(res, fallbackMessage) {
  try {
    const data = await res.json();
    if (data?.error?.message) return data.error.message;
    if (data?.error && typeof data.error === "string") return data.error;
    if (data?.message) return data.message;
  } catch {
    // Ignore non-JSON error responses and fall back to generic text.
  }
  return fallbackMessage;
}

export async function createSession(payload) {
  const res = await fetch(joinApiUrl("/api/sessions"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error(await parseApiError(res, "创建会话失败"));
  return res.json();
}

export async function streamDiscussion(sessionId, onTurn) {
  const res = await fetch(joinApiUrl(`/api/sessions/${sessionId}/discussion/stream`), {
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
      const payload = parseSseDataLine(raw);
      if (!payload) continue;
      onTurn(payload);
    }
  }
}

export async function createVideoJob(sessionId, sourceVideoPath) {
  const sourcePath = typeof sourceVideoPath === "string" ? sourceVideoPath : "";
  const sourceVideoUploadId =
    sourceVideoPath && typeof sourceVideoPath === "object" ? String(sourceVideoPath.uploadId || "").trim() : "";
  const res = await fetch(joinApiUrl("/api/video-jobs"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId, sourceVideoPath: sourcePath, sourceVideoUploadId })
  });
  if (!res.ok) throw new Error(await parseApiError(res, "视频任务创建失败"));
  return res.json();
}

export async function uploadVideoSource(file) {
  if (!(file instanceof Blob)) throw new Error("无效文件");
  const fileName = String(file.name || "upload.mp4").trim() || "upload.mp4";
  const res = await fetch(joinApiUrl("/api/uploads"), {
    method: "POST",
    headers: {
      "Content-Type": file.type || "application/octet-stream",
      "x-file-name": encodeURIComponent(fileName)
    },
    body: file
  });
  if (!res.ok) throw new Error(await parseApiError(res, "素材上传失败"));
  return res.json();
}

export async function fetchAgents() {
  const res = await fetch(joinApiUrl("/api/agents"));
  if (!res.ok) throw new Error(await parseApiError(res, "角色列表加载失败"));
  const data = await res.json();
  return Array.isArray(data?.agents) ? data.agents : [];
}

export function watchVideoJob(jobId, onEvent, options = {}) {
  const source = new EventSource(joinApiUrl(`/api/video-jobs/${jobId}/events`));
  source.addEventListener("job-event", (event) => {
    const payload = safeParseJson(event.data);
    if (!payload) return;
    onEvent(payload);
  });
  source.addEventListener("complete", (event) => {
    const payload = safeParseJson(event.data);
    if (payload) onEvent(payload);
    source.close();
  });
  source.onerror = () => {
    if (typeof options.onDisconnect === "function") options.onDisconnect();
    onEvent({ event: "error", message: "任务事件流中断，请稍后重试。" });
    source.close();
  };
  return () => source.close();
}

export async function fetchGatewayCapabilities() {
  const res = await fetch(joinApiUrl("/api/gateway/capabilities"));
  if (!res.ok) throw new Error(await parseApiError(res, "能力列表加载失败"));
  const data = await res.json();
  return Array.isArray(data?.capabilities) ? data.capabilities : [];
}

export async function fetchGatewayInvocations(limit = 24) {
  const res = await fetch(joinApiUrl(`/api/gateway/invocations?limit=${limit}`));
  if (!res.ok) throw new Error(await parseApiError(res, "调用日志加载失败"));
  const data = await res.json();
  return Array.isArray(data?.invocations) ? data.invocations : [];
}

export function watchGatewayInvocations(onEvent, options = {}) {
  const source = new EventSource(joinApiUrl("/api/gateway/invocations/events"));
  source.addEventListener("invocation", (event) => {
    const payload = safeParseJson(event.data);
    if (!payload) return;
    onEvent(payload);
  });
  source.onerror = () => {
    if (typeof options.onDisconnect === "function") options.onDisconnect();
    onEvent({ event: "error", message: "网关调用流中断，正在等待重连。" });
  };
  return () => source.close();
}
