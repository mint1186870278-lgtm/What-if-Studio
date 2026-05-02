export function roleLabel(type) {
  if (type === "guardian") return "原著守门人";
  if (type === "director") return "导演";
  if (type === "crew") return "制作组";
  return "成员";
}

export function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function buildAvatarCandidates(url) {
  const raw = String(url || "").trim();
  if (!raw) return [];
  const queryIdx = raw.indexOf("?");
  const hashIdx = raw.indexOf("#");
  const tailIdx = [queryIdx, hashIdx].filter((idx) => idx >= 0).sort((a, b) => a - b)[0] ?? raw.length;
  const path = raw.slice(0, tailIdx);
  const suffix = raw.slice(tailIdx);
  const dot = path.lastIndexOf(".");
  if (dot < 0) return [raw];
  const base = path.slice(0, dot);
  const currentExt = path.slice(dot + 1).toLowerCase();
  const extPriority = ["png", "jpg", "jpeg", "webp", "svg"];
  const order = [currentExt, ...extPriority.filter((ext) => ext !== currentExt)];
  const seen = new Set();
  return order
    .map((ext) => `${base}.${ext}${suffix}`)
    .filter((candidate) => {
      if (seen.has(candidate)) return false;
      seen.add(candidate);
      return true;
    });
}

function probeImage(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(true);
    img.onerror = () => resolve(false);
    img.src = url;
  });
}

async function resolveAvatarUrl(agent) {
  const candidates = [...new Set(buildAvatarCandidates(agent?.avatarUrl))];
  for (const candidate of candidates) {
    if (await probeImage(candidate)) return candidate;
  }
  return "";
}

export async function normalizeAgentAvatars(agents) {
  return Promise.all(
    agents.map(async (agent) => ({
      ...agent,
      avatarUrl: await resolveAvatarUrl(agent)
    }))
  );
}

export function displayAgent(agent) {
  const name = String(agent?.name || "");
  return {
    name,
    role: roleLabel(agent?.type),
    summary: agent?.stance || "等待分配任务。"
  };
}
