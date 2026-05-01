import fs from "node:fs/promises";
import path from "node:path";

const STORE_PATH = process.env.SESSION_STORE_PATH
  ? path.resolve(process.env.SESSION_STORE_PATH)
  : path.resolve(process.cwd(), "tmp-data", "sessions.json");

export function getSessionStorePath() {
  return STORE_PATH;
}

export async function loadSessions() {
  try {
    const raw = await fs.readFile(STORE_PATH, "utf8");
    const parsed = JSON.parse(raw);
    const list = Array.isArray(parsed?.sessions) ? parsed.sessions : [];
    const map = new Map();
    for (const item of list) {
      if (!item || typeof item.sessionId !== "string" || !item.sessionId) continue;
      map.set(item.sessionId, item);
    }
    return map;
  } catch (error) {
    if (error?.code === "ENOENT") return new Map();
    throw error;
  }
}

export async function saveSessions(sessions) {
  const list = [...sessions.values()];
  await fs.mkdir(path.dirname(STORE_PATH), { recursive: true });
  await fs.writeFile(STORE_PATH, JSON.stringify({ sessions: list }, null, 2), "utf8");
}
