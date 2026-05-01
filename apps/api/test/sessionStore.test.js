import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const tmpRoot = path.resolve(process.cwd(), "tmp-test-store");
const storePath = path.join(tmpRoot, "sessions.json");

process.env.SESSION_STORE_PATH = storePath;
const { loadSessions, saveSessions } = await import("../src/sessionStore.js");

test("saveSessions and loadSessions roundtrip", async () => {
  const sessions = new Map();
  sessions.set("sess-1", {
    sessionId: "sess-1",
    workTitle: "demo",
    endingDirection: "happy",
    stylePreference: "auto",
    sourceVideoPath: "",
    createdAt: Date.now()
  });

  await saveSessions(sessions);
  const loaded = await loadSessions();

  assert.equal(loaded.size, 1);
  assert.equal(loaded.get("sess-1")?.workTitle, "demo");
});

test("loadSessions returns empty map when file missing", async () => {
  await fs.rm(tmpRoot, { recursive: true, force: true });
  const loaded = await loadSessions();
  assert.equal(loaded.size, 0);
});
