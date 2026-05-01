import { EventEmitter } from "node:events";

const services = new Map();
const invocationLog = [];
const gatewayEvents = new EventEmitter();
const MAX_LOG = 240;
const gatewayToken = String(process.env.GATEWAY_TOKEN || "agent-network-demo-token");

function nowTs() {
  return Date.now();
}

function withTimeout(task, timeoutMs, label) {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) return task();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`${label} timeout (${timeoutMs}ms)`));
    }, timeoutMs);
    Promise.resolve()
      .then(task)
      .then(
        (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        (error) => {
          clearTimeout(timer);
          reject(error);
        }
      );
  });
}

function normalizeCapability(capability, serviceId) {
  if (!capability || typeof capability !== "object") {
    throw new Error(`invalid capability in service ${serviceId}`);
  }
  if (!capability.capabilityId || typeof capability.capabilityId !== "string") {
    throw new Error(`capabilityId required in service ${serviceId}`);
  }
  let handler = capability.handler;
  if (typeof handler !== "function" && typeof capability.invokeUrl === "string" && capability.invokeUrl.trim()) {
    const invokeUrl = capability.invokeUrl.trim();
    handler = async (input, ctx) => {
      const res = await fetch(invokeUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Gateway-Caller": String(ctx?.caller || "unknown-caller")
        },
        body: JSON.stringify({
          capabilityId: capability.capabilityId,
          input
        })
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(json?.error?.message || `remote capability error ${res.status}`);
      }
      return json?.result ?? json;
    };
  }
  if (typeof handler !== "function") {
    throw new Error(`capability handler required (${capability.capabilityId})`);
  }
  return {
    capabilityId: capability.capabilityId,
    title: capability.title || capability.capabilityId,
    description: capability.description || "",
    timeoutMs: Number(capability.timeoutMs || 0),
    retries: Number(capability.retries || 0),
    tags: Array.isArray(capability.tags) ? capability.tags : [],
    inputSchema: capability.inputSchema || {},
    outputSchema: capability.outputSchema || {},
    handler
  };
}

export function registerGatewayService(definition, options = {}) {
  const serviceId = String(definition?.serviceId || "").trim();
  if (!serviceId) throw new Error("serviceId required");
  if (services.has(serviceId) && !options.replace) {
    throw new Error(`service already exists: ${serviceId}`);
  }
  const capabilityList = Array.isArray(definition.capabilities) ? definition.capabilities : [];
  const capabilities = capabilityList.map((item) => normalizeCapability(item, serviceId));
  services.set(serviceId, {
    serviceId,
    displayName: definition.displayName || serviceId,
    network: definition.network || "p2p",
    owner: definition.owner || "local",
    tags: Array.isArray(definition.tags) ? definition.tags : [],
    registeredAt: new Date().toISOString(),
    capabilities
  });
  return listGatewayServices().find((item) => item.serviceId === serviceId);
}

export function getGatewayToken() {
  return gatewayToken;
}

export function isGatewayTokenValid(token) {
  return String(token || "") === gatewayToken;
}

function pushInvocation(entry) {
  invocationLog.unshift(entry);
  if (invocationLog.length > MAX_LOG) invocationLog.length = MAX_LOG;
  gatewayEvents.emit("invocation", entry);
}

export function emitGatewayInvocation(entry = {}) {
  const normalized = {
    invocationId: String(entry.invocationId || `invk-${Math.random().toString(36).slice(2, 10)}`),
    parentInvocationId: entry.parentInvocationId || null,
    fallbackFromCapabilityId: String(entry.fallbackFromCapabilityId || ""),
    caller: String(entry.caller || "anet-orchestrator"),
    capabilityId: String(entry.capabilityId || "anet.generate"),
    targetServiceId: String(entry.targetServiceId || "unknown-target"),
    status: String(entry.status || "calling"),
    retriesUsed: Number(entry.retriesUsed || 0),
    durationMs: Number(entry.durationMs || 0),
    error: entry.error ? String(entry.error) : undefined,
    from: String(entry.from || entry.caller || "orchestrator"),
    to: String(entry.to || entry.targetServiceId || "unknown-target"),
    skill: String(entry.skill || ""),
    phase: String(entry.phase || ""),
    createdAt: entry.createdAt || new Date().toISOString()
  };
  pushInvocation(normalized);
  return normalized;
}

function maskGatewayToken(token) {
  if (!token) return "";
  if (token.length < 8) return `${token.slice(0, 2)}***`;
  return `${token.slice(0, 4)}***${token.slice(-2)}`;
}

function listCapabilityBindings(capabilityId, preferredServiceId = "") {
  const bindings = [];
  for (const service of services.values()) {
    for (const capability of service.capabilities) {
      if (capability.capabilityId !== capabilityId) continue;
      if (preferredServiceId && preferredServiceId !== service.serviceId) continue;
      bindings.push({ service, capability });
    }
  }
  return bindings;
}

async function invokeSingleBinding(binding, payload, attempt, invocationId, parentInvocationId) {
  const startedAt = nowTs();
  const result = await withTimeout(
    () =>
      binding.capability.handler(payload.input || {}, {
        caller: payload.caller,
        invocationId,
        parentInvocationId,
        serviceId: binding.service.serviceId,
        capabilityId: binding.capability.capabilityId,
        invoke: (nested) =>
          invokeGatewayCapability({
            ...nested,
            caller: binding.service.serviceId,
            token: gatewayToken,
            internal: true,
            parentInvocationId: invocationId
          })
      }),
    payload.timeoutMs || binding.capability.timeoutMs || 0,
    `${binding.service.serviceId}/${binding.capability.capabilityId}`
  );
  return {
    result,
    attempt,
    durationMs: nowTs() - startedAt,
    serviceId: binding.service.serviceId
  };
}

export async function invokeGatewayCapability(rawPayload) {
  const payload = {
    capabilityId: String(rawPayload?.capabilityId || "").trim(),
    caller: String(rawPayload?.caller || "unknown-caller").trim(),
    preferredServiceId: String(rawPayload?.preferredServiceId || "").trim(),
    input: rawPayload?.input ?? {},
    retries: Number(rawPayload?.options?.retries ?? rawPayload?.retries ?? 0),
    timeoutMs: Number(rawPayload?.options?.timeoutMs ?? rawPayload?.timeoutMs ?? 0),
    fallbackCapabilityId: String(rawPayload?.options?.fallbackCapabilityId || "").trim(),
    parentInvocationId: rawPayload?.parentInvocationId || null,
    fallbackFromCapabilityId: rawPayload?.fallbackFromCapabilityId || "",
    token: String(rawPayload?.token || ""),
    internal: Boolean(rawPayload?.internal)
  };

  if (!payload.capabilityId) throw new Error("capabilityId required");
  if (!payload.internal && !isGatewayTokenValid(payload.token)) {
    throw new Error("gateway token invalid");
  }

  const invocationId = `invk-${Math.random().toString(36).slice(2, 10)}`;
  const startedAt = nowTs();
  const bindings = listCapabilityBindings(payload.capabilityId, payload.preferredServiceId);
  if (!bindings.length) {
    throw new Error(`capability not found: ${payload.capabilityId}`);
  }

  let lastError = null;
  for (const binding of bindings) {
    const maxAttempts = Math.max(1, (binding.capability.retries || 0) + 1, payload.retries + 1);
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        const invokeResult = await invokeSingleBinding(
          binding,
          payload,
          attempt,
          invocationId,
          payload.parentInvocationId
        );
        const audit = {
          invocationId,
          parentInvocationId: payload.parentInvocationId,
          fallbackFromCapabilityId: payload.fallbackFromCapabilityId,
          caller: payload.caller,
          capabilityId: payload.capabilityId,
          targetServiceId: binding.service.serviceId,
          status: "ok",
          retriesUsed: Math.max(0, attempt - 1),
          durationMs: nowTs() - startedAt,
          serviceDurationMs: invokeResult.durationMs,
          createdAt: new Date().toISOString()
        };
        pushInvocation(audit);
        return {
          ok: true,
          result: invokeResult.result,
          audit
        };
      } catch (error) {
        lastError = error;
      }
    }
  }

  if (payload.fallbackCapabilityId && payload.fallbackCapabilityId !== payload.capabilityId) {
    return invokeGatewayCapability({
      capabilityId: payload.fallbackCapabilityId,
      caller: payload.caller,
      input: payload.input,
      token: gatewayToken,
      parentInvocationId: payload.parentInvocationId,
      fallbackFromCapabilityId: payload.capabilityId,
      internal: true
    });
  }

  const failureAudit = {
    invocationId,
    parentInvocationId: payload.parentInvocationId,
    fallbackFromCapabilityId: payload.fallbackFromCapabilityId,
    caller: payload.caller,
    capabilityId: payload.capabilityId,
    targetServiceId: payload.preferredServiceId || "unresolved",
    status: "failed",
    retriesUsed: Math.max(0, payload.retries),
    durationMs: nowTs() - startedAt,
    error: lastError?.message || "unknown error",
    createdAt: new Date().toISOString()
  };
  pushInvocation(failureAudit);
  throw lastError || new Error("gateway invoke failed");
}

export function listGatewayServices() {
  return [...services.values()].map((service) => ({
    serviceId: service.serviceId,
    displayName: service.displayName,
    network: service.network,
    owner: service.owner,
    tags: service.tags,
    registeredAt: service.registeredAt,
    capabilities: service.capabilities.map((capability) => ({
      capabilityId: capability.capabilityId,
      title: capability.title,
      description: capability.description,
      tags: capability.tags
    }))
  }));
}

export function listGatewayCapabilities() {
  const capabilities = [];
  for (const service of services.values()) {
    for (const capability of service.capabilities) {
      capabilities.push({
        capabilityId: capability.capabilityId,
        title: capability.title,
        description: capability.description,
        serviceId: service.serviceId,
        serviceName: service.displayName,
        tags: capability.tags,
        inputSchema: capability.inputSchema,
        outputSchema: capability.outputSchema
      });
    }
  }
  return capabilities;
}

export function listInvocations(limit = 40) {
  const max = Math.max(1, Math.min(200, Number(limit || 40)));
  return invocationLog.slice(0, max);
}

export function onGatewayInvocation(listener) {
  gatewayEvents.on("invocation", listener);
  return () => gatewayEvents.off("invocation", listener);
}

export function getGatewayMeta() {
  return {
    tokenRequired: true,
    tokenHint: maskGatewayToken(gatewayToken),
    totalServices: services.size,
    totalCapabilities: listGatewayCapabilities().length
  };
}

export function initGateway(deps) {
  if (services.size) return;
  const { generateDiscussionTimeline, startVideoJob, getJob } = deps;

  registerGatewayService({
    serviceId: "director-brain",
    displayName: "Director Brain",
    network: "p2p",
    owner: "crew-alpha",
    tags: ["discussion", "storyboard"],
    capabilities: [
      {
        capabilityId: "discussion.generateTimeline",
        title: "Generate discussion timeline",
        description: "Produce structured discussion turns for a session.",
        inputSchema: { session: "CreativeSession+sessionId" },
        outputSchema: { timeline: "DiscussionTimeline[]" },
        retries: 1,
        handler: async (input) => {
          const timeline = generateDiscussionTimeline(input.session);
          return { timeline };
        }
      }
    ]
  });

  registerGatewayService({
    serviceId: "video-lab",
    displayName: "Video Lab",
    network: "p2p",
    owner: "crew-alpha",
    tags: ["video", "render"],
    capabilities: [
      {
        capabilityId: "video.createJob",
        title: "Create video job",
        description: "Start a render pipeline job for a session.",
        inputSchema: { session: "CreativeSession+sessionId+sourceVideoPath" },
        outputSchema: { job: "VideoJob" },
        retries: 1,
        handler: async (input) => {
          const job = await startVideoJob(input.session);
          return { job };
        }
      },
      {
        capabilityId: "video.getJob",
        title: "Get video job",
        description: "Fetch current status of a video job.",
        inputSchema: { jobId: "string" },
        outputSchema: { job: "VideoJob" },
        handler: async (input) => {
          const job = getJob(input.jobId);
          if (!job) throw new Error("job not found");
          return { job };
        }
      }
    ]
  });

  registerGatewayService({
    serviceId: "audio-lab",
    displayName: "Audio Lab",
    network: "p2p",
    owner: "crew-alpha",
    tags: ["audio", "mood"],
    capabilities: [
      {
        capabilityId: "soundtrack.suggest",
        title: "Suggest soundtrack profile",
        description: "Recommend soundtrack based on style and ending direction.",
        inputSchema: { stylePreference: "string", endingDirection: "string" },
        outputSchema: { profile: "object" },
        handler: async (input) => {
          if (input?.forceFail) throw new Error("audio-lab forced failure");
          const style = String(input?.stylePreference || "auto");
          const moodMap = {
            darkEpic: "low-strings",
            warmHealing: "piano-strings",
            realism: "ambient-minimal",
            fantasyGrand: "orchestra-choir",
            auto: "adaptive-hybrid"
          };
          return {
            profile: {
              cue: moodMap[style] || "adaptive-hybrid",
              ducking: -8,
              lufsTarget: -16,
              note: `围绕结局“${String(input?.endingDirection || "")}”做情绪抬升。`
            }
          };
        }
      }
    ]
  });

  registerGatewayService({
    serviceId: "orchestrator-hub",
    displayName: "Orchestrator Hub",
    network: "p2p",
    owner: "crew-alpha",
    tags: ["orchestration", "cross-agent"],
    capabilities: [
      {
        capabilityId: "production.plan",
        title: "Compose cross-agent plan",
        description: "Invoke director and audio services to build a joined plan.",
        inputSchema: { session: "CreativeSession+sessionId" },
        outputSchema: { plan: "object" },
        handler: async (input, ctx) => {
          const discussion = await ctx.invoke({
            capabilityId: "discussion.generateTimeline",
            input: { session: input.session }
          });
          const soundtrack = await ctx.invoke({
            capabilityId: "soundtrack.suggest",
            input: {
              stylePreference: input.session?.stylePreference,
              endingDirection: input.session?.endingDirection
            },
            options: {
              fallbackCapabilityId: "discussion.generateTimeline"
            }
          });
          return {
            plan: {
              timelineTurns: Array.isArray(discussion?.result?.timeline)
                ? discussion.result.timeline.length
                : 0,
              soundtrack: soundtrack?.result?.profile || null
            }
          };
        }
      }
    ]
  });
}

