import cors from "cors";
import express from "express";
import fs from "node:fs/promises";
import path from "node:path";
import { parseCreativeSession } from "@yinanping/contracts";
import { getAgents } from "./agentCatalog.js";
import { generateDiscussionTimeline } from "./discussionEngine.js";
import {
  emitGatewayInvocation,
  getGatewayToken,
  getGatewayMeta,
  initGateway,
  isGatewayTokenValid,
  invokeGatewayCapability,
  listGatewayCapabilities,
  listGatewayServices,
  listInvocations,
  onGatewayInvocation,
  registerGatewayService
} from "./gateway.js";
import { getJob, listArtifactRoot, startVideoJob, subscribeJob } from "./videoPipeline.js";
import { getSessionStorePath, loadSessions, saveSessions } from "./sessionStore.js";

const app = express();
const port = Number(process.env.PORT || 3567);
const corsOrigin = String(process.env.CORS_ORIGIN || "").trim();
const anetBase = String(process.env.ANET_BASE || "http://127.0.0.1:3998").replace(/\/+$/, "");

let sessions = new Map();
const uploadedVideoFiles = new Map();
const UPLOAD_ROOT = path.resolve(process.cwd(), "tmp-uploads");

app.use(cors({ origin: corsOrigin || true }));
app.use(express.json());
app.use((req, _res, next) => {
  req.requestId = `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
  next();
});

function logEvent(event, payload = {}) {
  console.log(
    JSON.stringify({
      ts: new Date().toISOString(),
      event,
      ...payload
    })
  );
}

function sendError(res, req, status, code, message, details = null) {
  res.status(status).json({
    error: {
      code,
      message,
      details
    },
    requestId: req.requestId
  });
}

function readGatewayToken(req) {
  const headerToken = String(req.headers["x-gateway-token"] || "").trim();
  if (headerToken) return headerToken;
  const bodyToken = String(req.body?.token || "").trim();
  if (bodyToken) return bodyToken;
  return getGatewayToken();
}

function sanitizeUploadName(rawName) {
  const normalized = String(rawName || "").trim() || "upload.mp4";
  const safe = normalized.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_");
  return path.basename(safe);
}

async function anetJsonFetch(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data?.error?.message || data?.message || `anet request failed: ${res.status}`);
  }
  return data;
}

async function discoverAgent(skill) {
  const data = await anetJsonFetch(`${anetBase}/api/svc/discover?skill=${encodeURIComponent(skill)}`);
  const peers = Array.isArray(data) ? data : Array.isArray(data?.peers) ? data.peers : [];
  if (!peers.length) throw new Error(`no peer discovered for skill: ${skill}`);
  return peers[0];
}

function extractCallBody(payload) {
  if (!payload || typeof payload !== "object") return {};
  if (payload.body && typeof payload.body === "object") return payload.body;
  if (payload.result && typeof payload.result === "object") return payload.result;
  return payload;
}

async function callAnetSkill({ skill, payload, requestId = "", caller = "studio-web-live" }) {
  const startedAt = Date.now();
  const callingEntry = emitGatewayInvocation({
    caller,
    capabilityId: `anet.skill.${skill}`,
    targetServiceId: "discovering",
    status: "calling",
    skill,
    from: caller,
    to: `skill:${skill}`
  });
  try {
    const target = await discoverAgent(skill);
    emitGatewayInvocation({
      invocationId: callingEntry.invocationId,
      caller,
      capabilityId: `anet.skill.${skill}`,
      targetServiceId: String(target?.name || "unknown-target"),
      status: "calling",
      skill,
      from: caller,
      to: String(target?.name || "unknown-target")
    });
    const data = await anetJsonFetch(`${anetBase}/api/svc/call`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        peer_id: target.peer_id,
        service: target.name,
        path: "/generate",
        method: "POST",
        body: payload
      })
    });
    const body = extractCallBody(data);
    emitGatewayInvocation({
      invocationId: callingEntry.invocationId,
      caller,
      capabilityId: `anet.skill.${skill}`,
      targetServiceId: String(target?.name || "unknown-target"),
      status: "ok",
      durationMs: Date.now() - startedAt,
      skill,
      from: caller,
      to: String(target?.name || "unknown-target")
    });
    logEvent("anet.call_ok", { requestId, skill, target: target?.name, durationMs: Date.now() - startedAt });
    return { skill, targetName: String(target?.name || ""), body };
  } catch (error) {
    emitGatewayInvocation({
      invocationId: callingEntry.invocationId,
      caller,
      capabilityId: `anet.skill.${skill}`,
      targetServiceId: "unresolved",
      status: "failed",
      durationMs: Date.now() - startedAt,
      error: error.message,
      skill,
      from: caller,
      to: "unresolved"
    });
    logEvent("anet.call_failed", { requestId, skill, message: error.message });
    throw error;
  }
}

async function runAnetCreativeRound(session, requestId = "") {
  const payload = {
    topic: session?.workTitle || "",
    ending: session?.endingDirection || "",
    style: session?.stylePreference || "auto",
    scene: session?.endingDirection || "",
    tone: session?.stylePreference || "balanced"
  };
  const skillOrder = ["director", "composer", "editor", "collector"];
  const settled = await Promise.allSettled(
    skillOrder.map((skill) => callAnetSkill({ skill, payload, requestId, caller: "studio-web-live" }))
  );
  return settled
    .map((item, idx) => ({ item, skill: skillOrder[idx] }))
    .filter(({ item }) => item.status === "fulfilled")
    .map(({ item, skill }) => {
      const result = String(item.value?.body?.result || item.value?.body?.text || "").trim();
      return { skill, result };
    })
    .filter((item) => item.result);
}

function persistSessions(reason) {
  saveSessions(sessions)
    .then(() => {
      logEvent("sessions.persisted", { reason, total: sessions.size });
    })
    .catch((error) => {
      logEvent("sessions.persist_failed", { reason, message: error.message });
    });
}

function toArtifactUrl(artifactPath) {
  const rel = path.relative(listArtifactRoot(), artifactPath);
  if (rel.startsWith("..")) return "";
  const normalized = rel.split(path.sep).join("/");
  return `/api/artifacts/${normalized}`;
}

function decorateArtifact(artifact) {
  if (!artifact || typeof artifact !== "object") return artifact;
  const pathValue = typeof artifact.path === "string" ? artifact.path : "";
  const url = pathValue ? toArtifactUrl(pathValue) : "";
  return {
    ...artifact,
    publicUrl: url
  };
}

function decorateJob(job) {
  if (!job) return job;
  const artifacts = Array.isArray(job.artifacts) ? job.artifacts.map(decorateArtifact) : [];
  return {
    ...job,
    artifacts
  };
}

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, service: "yinanping-api" });
});

app.use("/api/artifacts", express.static(listArtifactRoot()));

app.get("/api/agents", (_req, res) => {
  res.json({ agents: getAgents() });
});

app.get("/api/gateway/meta", (_req, res) => {
  res.json({ gateway: getGatewayMeta() });
});

app.get("/api/gateway/services", (_req, res) => {
  res.json({ services: listGatewayServices() });
});

app.get("/api/gateway/capabilities", (_req, res) => {
  res.json({ capabilities: listGatewayCapabilities() });
});

app.get("/api/gateway/invocations", (req, res) => {
  const limit = Number(req.query.limit || 40);
  res.json({ invocations: listInvocations(limit) });
});

app.get("/api/gateway/invocations/events", (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  const heartbeat = setInterval(() => {
    res.write(`event: heartbeat\n`);
    res.write(`data: ${JSON.stringify({ event: "heartbeat", ts: Date.now() })}\n\n`);
  }, 15000);

  const unsubscribe = onGatewayInvocation((entry) => {
    res.write(`event: invocation\n`);
    res.write(`data: ${JSON.stringify(entry)}\n\n`);
  });

  req.on("close", () => {
    clearInterval(heartbeat);
    unsubscribe();
  });
});

app.post("/api/gateway/register", (req, res) => {
  try {
    const token = readGatewayToken(req);
    if (!isGatewayTokenValid(token)) {
      sendError(res, req, 401, "GATEWAY_TOKEN_INVALID", "gateway token invalid");
      return;
    }
    const service = registerGatewayService(req.body?.service || req.body, {
      replace: Boolean(req.body?.replace)
    });
    logEvent("gateway.service_registered", {
      serviceId: service.serviceId,
      requestId: req.requestId
    });
    res.status(201).json({ service });
  } catch (error) {
    sendError(res, req, 400, "GATEWAY_REGISTER_FAILED", error.message);
  }
});

app.post("/api/gateway/invoke", async (req, res) => {
  try {
    const capabilityId = String(req.body?.capabilityId || "").trim();
    const caller = String(req.body?.caller || "external-caller").trim();
    const preferredServiceId = String(req.body?.preferredServiceId || "").trim();
    const token = readGatewayToken(req);
    const options = req.body?.options && typeof req.body.options === "object" ? req.body.options : {};
    const invoked = await invokeGatewayCapability({
      capabilityId,
      caller,
      preferredServiceId,
      token,
      input: req.body?.input || {},
      options
    });
    res.json(invoked);
  } catch (error) {
    sendError(res, req, 400, "GATEWAY_INVOKE_FAILED", error.message);
  }
});

app.post("/api/sessions", (req, res) => {
  try {
    const payload = parseCreativeSession(req.body || {});
    const sessionId = `sess-${Math.random().toString(36).slice(2, 8)}`;
    const session = { sessionId, ...payload, createdAt: Date.now(), sourceVideoPath: "" };
    sessions.set(sessionId, session);
    persistSessions("session_created");
    logEvent("session.created", { sessionId, requestId: req.requestId });
    res.status(201).json({ session });
  } catch (error) {
    sendError(res, req, 400, "INVALID_SESSION_PAYLOAD", error.message);
  }
});

app.post("/api/uploads", express.raw({ type: () => true, limit: "800mb" }), async (req, res) => {
  try {
    const body = req.body;
    const bytes = Buffer.isBuffer(body) ? body : null;
    if (!bytes || !bytes.length) {
      sendError(res, req, 400, "UPLOAD_EMPTY", "upload body is empty");
      return;
    }
    const rawNameHeader = String(req.headers["x-file-name"] || "");
    const decodedName = rawNameHeader ? decodeURIComponent(rawNameHeader) : "upload.mp4";
    const originalName = sanitizeUploadName(decodedName);
    const ext = path.extname(originalName) || ".mp4";
    const uploadId = `upload-${Math.random().toString(36).slice(2, 10)}`;
    await fs.mkdir(UPLOAD_ROOT, { recursive: true });
    const storedPath = path.join(UPLOAD_ROOT, `${uploadId}${ext.toLowerCase()}`);
    await fs.writeFile(storedPath, bytes);
    uploadedVideoFiles.set(uploadId, {
      uploadId,
      path: storedPath,
      originalName,
      bytes: bytes.length,
      mimeType: String(req.headers["content-type"] || "application/octet-stream"),
      createdAt: Date.now()
    });
    res.status(201).json({
      upload: {
        uploadId,
        originalName,
        size: bytes.length
      }
    });
  } catch (error) {
    sendError(res, req, 400, "UPLOAD_FAILED", error.message);
  }
});

app.post("/api/sessions/:id/discussion/stream", async (req, res) => {
  const session = sessions.get(req.params.id);
  if (!session) {
    sendError(res, req, 404, "SESSION_NOT_FOUND", "session not found");
    return;
  }
  logEvent("discussion.stream_started", { sessionId: session.sessionId, requestId: req.requestId });

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  const heartbeat = setInterval(() => {
    res.write(`event: heartbeat\n`);
    res.write(`data: ${JSON.stringify({ event: "heartbeat", ts: Date.now() })}\n\n`);
  }, 15000);
  let aborted = false;
  req.on("aborted", () => {
    aborted = true;
    clearInterval(heartbeat);
  });
  res.on("close", () => {
    aborted = true;
    clearInterval(heartbeat);
  });

  let timeline = [];
  let anetRound = [];
  try {
    anetRound = await runAnetCreativeRound(session, req.requestId);
  } catch (_error) {
    // Ignore here; each skill call is individually logged and streamed via gateway events.
  }
  try {
    const invoked = await invokeGatewayCapability({
      capabilityId: "discussion.generateTimeline",
      caller: "studio-web-live",
      token: readGatewayToken(req),
      input: { session }
    });
    timeline = Array.isArray(invoked?.result?.timeline) ? invoked.result.timeline : [];
  } catch (error) {
    logEvent("gateway.discussion_fallback", {
      sessionId: session.sessionId,
      message: error.message,
      requestId: req.requestId
    });
    timeline = generateDiscussionTimeline(session);
  }
  if (anetRound.length) {
    const notes = anetRound
      .map((item) => `${item.skill}: ${item.result.slice(0, 180)}`)
      .join(" | ");
    timeline.unshift({
      event: "system",
      stage: "briefing",
      content: `ANet 节点建议已同步：${notes}`
    });
  }

  for (const item of timeline) {
    if (aborted) return;
    const eventName = item.event || "turn";
    res.write(`event: ${eventName}\n`);
    res.write(`data: ${JSON.stringify(item)}\n\n`);
    const stepDelay = eventName === "turn" ? 560 : 360;
    await new Promise((r) => setTimeout(r, stepDelay));
  }
  res.write(`event: done\n`);
  res.write(`data: ${JSON.stringify({ event: "done", sessionId: session.sessionId })}\n\n`);
  clearInterval(heartbeat);
  res.end();
});

app.post("/api/video-jobs", async (req, res) => {
  const { sessionId, sourceVideoPath = "", sourceVideoUploadId = "" } = req.body || {};
  const session = sessions.get(sessionId);
  if (!session) {
    sendError(res, req, 404, "SESSION_NOT_FOUND", "session not found");
    return;
  }
  const uploadId = String(sourceVideoUploadId || "").trim();
  if (uploadId) {
    const upload = uploadedVideoFiles.get(uploadId);
    if (!upload) {
      sendError(res, req, 404, "UPLOAD_NOT_FOUND", "upload not found");
      return;
    }
    session.sourceVideoPath = upload.path;
  } else {
    session.sourceVideoPath = String(sourceVideoPath || "");
  }
  persistSessions("session_video_path_updated");
  let job;
  try {
    const invoked = await invokeGatewayCapability({
      capabilityId: "video.createJob",
      caller: "studio-web-live",
      token: readGatewayToken(req),
      input: { session }
    });
    job = invoked?.result?.job;
  } catch (error) {
    logEvent("gateway.video_job_fallback", {
      sessionId,
      message: error.message,
      requestId: req.requestId
    });
    job = await startVideoJob(session);
  }
  logEvent("video_job.created", { sessionId, jobId: job.jobId, requestId: req.requestId });
  res.status(201).json({ job });
});

app.get("/api/video-jobs/:id", (req, res) => {
  const job = getJob(req.params.id);
  if (!job) {
    sendError(res, req, 404, "JOB_NOT_FOUND", "job not found");
    return;
  }
  res.json({ job: decorateJob(job) });
});

app.get("/api/video-jobs/:id/events", (req, res) => {
  const job = getJob(req.params.id);
  if (!job) {
    sendError(res, req, 404, "JOB_NOT_FOUND", "job not found");
    return;
  }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  const heartbeat = setInterval(() => {
    res.write(`event: heartbeat\n`);
    res.write(`data: ${JSON.stringify({ event: "heartbeat", ts: Date.now() })}\n\n`);
  }, 15000);

  const unsubscribe = subscribeJob(req.params.id, (payload) => {
    if (payload.event === "progress") {
      res.write(`event: job-event\n`);
      res.write(`data: ${JSON.stringify(payload)}\n\n`);
      return;
    }
    const result = decorateArtifact(payload.result);
    const artifacts = Array.isArray(payload.artifacts) ? payload.artifacts.map(decorateArtifact) : [];
    res.write(`event: complete\n`);
    res.write(`data: ${JSON.stringify({ ...payload, result, artifacts })}\n\n`);
    unsubscribe();
    clearInterval(heartbeat);
    res.end();
  });

  req.on("close", () => {
    clearInterval(heartbeat);
    unsubscribe();
  });
});

async function bootstrap() {
  try {
    sessions = await loadSessions();
    logEvent("sessions.loaded", { total: sessions.size, storePath: getSessionStorePath() });
  } catch (error) {
    logEvent("sessions.load_failed", { message: error.message, storePath: getSessionStorePath() });
    sessions = new Map();
  }
  initGateway({
    generateDiscussionTimeline,
    startVideoJob,
    getJob
  });
  logEvent("gateway.ready", {
    services: listGatewayServices().length,
    capabilities: listGatewayCapabilities().length
  });

  app.listen(port, () => {
    logEvent("server.started", {
      baseUrl: `http://localhost:${port}`,
      corsOrigin: corsOrigin || "*"
    });
  });
}

bootstrap();
