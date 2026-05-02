function getViteEnvValue(key) {
  const env = import.meta?.env;
  if (!env || typeof env !== "object") return "";
  return String(env[key] || "").trim();
}

export function resolveApiBase() {
  const envBase = getViteEnvValue("VITE_API_BASE");
  if (envBase) return envBase.replace(/\/+$/, "");
  if (typeof window === "undefined") return "http://localhost:8000";
  // Prefer same-origin in browser so Vite proxy and production static hosting both work.
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
    if (data?.detail) return String(data.detail);
  } catch {
    // Ignore non-JSON error responses and fall back to generic text.
  }
  return fallbackMessage;
}

export async function streamProjectDiscussion(projectId, onTurn) {
  const res = await fetch(joinApiUrl(`/${projectId}/prepare`), {
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

export async function streamProjectGeneration(projectId, onEvent) {
  const res = await fetch(joinApiUrl(`/${projectId}/generate`), {
    method: "POST",
    headers: { "Content-Type": "application/json" }
  });
  if (!res.ok || !res.body) {
    throw new Error(await parseApiError(res, "视频生成流打开失败"));
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
      const mapped = payload.type ? { ...payload, event: payload.event || payload.type } : payload;
      onEvent(mapped);
    }
  }
}

export async function uploadVideoSource(projectId, file) {
  if (!(file instanceof Blob)) throw new Error("无效文件");
  const fileName = String(file.name || "upload.mp4").trim() || "upload.mp4";
  const formData = new FormData();
  formData.append("file", file, fileName);
  formData.append("asset_type", "video");
  const res = await fetch(joinApiUrl(`/${projectId}/assets`), {
    method: "POST",
    body: formData
  });
  if (!res.ok) throw new Error(await parseApiError(res, "素材上传失败"));
  const asset = await res.json();
  return { upload: { ...asset, uploadId: asset.id, originalName: asset.file_name } };
}

export async function fetchAgents() {
  const res = await fetch(joinApiUrl("/agents"));
  if (!res.ok) throw new Error(await parseApiError(res, "角色列表加载失败"));
  const data = await res.json();
  return Array.isArray(data?.agents) ? data.agents : [];
}

export async function getProject(projectId) {
  const res = await fetch(joinApiUrl(`/projects/${projectId}`));
  if (!res.ok) throw new Error(await parseApiError(res, "工程加载失败"));
  return res.json();
}

export async function createProject(payload) {
  const res = await fetch(joinApiUrl("/projects"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseApiError(res, "工程创建失败"));
  return res.json();
}

export async function updateProject(projectId, payload) {
  const res = await fetch(joinApiUrl(`/projects/${projectId}`), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseApiError(res, "工程更新失败"));
  return res.json();
}
