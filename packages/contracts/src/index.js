const STYLE_SET = new Set(["auto", "darkEpic", "warmHealing", "realism", "fantasyGrand"]);
const PHASE_SET = new Set(["collect", "analyze", "discuss", "edit", "render", "deliver"]);
const STATUS_SET = new Set(["pending", "running", "done", "failed"]);
const ZONE_SET = new Set(["archive", "directors", "mainStage", "edit", "sound"]);

function ensureString(value, fieldName) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${fieldName} 必填`);
  }
  return value.trim();
}

function optionalStringArray(value, fieldName) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item) => typeof item === "string" && item.trim())
    .map((item) => item.trim());
}

function optionalNumber(value, fallback = 0) {
  if (typeof value !== "number" || Number.isNaN(value)) return fallback;
  return value;
}

export function parseCreativeSession(raw) {
  const workTitle = ensureString(raw.workTitle, "workTitle");
  const endingDirection = ensureString(raw.endingDirection, "endingDirection");
  const stylePreference = typeof raw.stylePreference === "string" ? raw.stylePreference : "auto";

  if (!STYLE_SET.has(stylePreference)) {
    throw new Error("stylePreference 无效");
  }

  return {
    workTitle,
    endingDirection,
    stylePreference
  };
}

export function createDiscussionTurn(raw) {
  const speaker = ensureString(raw.speaker, "speaker");
  const role = ensureString(raw.role, "role");
  const content = ensureString(raw.content, "content");
  const stage = ensureString(raw.stage, "stage");
  return {
    speaker,
    role,
    content,
    stage,
    ts: Date.now()
  };
}

export function createVideoJob(raw) {
  if (!PHASE_SET.has(raw.phase)) throw new Error("phase 无效");
  if (!STATUS_SET.has(raw.status)) throw new Error("status 无效");
  return {
    jobId: ensureString(raw.jobId, "jobId"),
    sessionId: ensureString(raw.sessionId, "sessionId"),
    phase: raw.phase,
    status: raw.status,
    artifacts: Array.isArray(raw.artifacts) ? raw.artifacts : [],
    error: raw.error || ""
  };
}

export function parseAgentProfile(raw) {
  const profile = {
    agentId: ensureString(raw.agentId, "agentId"),
    name: ensureString(raw.name, "name"),
    type: ensureString(raw.type, "type"),
    stance: typeof raw.stance === "string" ? raw.stance : "",
    avatarUrl: typeof raw.avatarUrl === "string" ? raw.avatarUrl : "",
    homeZone: ZONE_SET.has(raw.homeZone) ? raw.homeZone : (raw.type === "crew" ? "archive" : "directors"),
    interestTags: optionalStringArray(raw.interestTags, "interestTags"),
    scatterPreference: ZONE_SET.has(raw.scatterPreference) ? raw.scatterPreference : "directors",
    lateJoinProbability: Math.max(0, Math.min(1, optionalNumber(raw.lateJoinProbability, 0)))
  };
  return profile;
}

export const schemaHints = {
  CreativeSession: {
    workTitle: "string",
    endingDirection: "string",
    stylePreference: "auto|darkEpic|warmHealing|realism|fantasyGrand"
  },
  DiscussionTurn: {
    speaker: "string",
    role: "guardian|director|crew",
    content: "string",
    stage: "briefing|topic-1|topic-2|topic-3|finalize",
    ts: "number"
  },
  VideoJob: {
    jobId: "string",
    sessionId: "string",
    phase: "collect|analyze|discuss|edit|render|deliver",
    status: "pending|running|done|failed",
    artifacts: "array",
    error: "string"
  },
  AgentProfile: {
    agentId: "string",
    name: "string",
    type: "guardian|director|crew",
    avatarUrl: "string",
    homeZone: "archive|directors|mainStage|edit|sound",
    interestTags: "string[]",
    scatterPreference: "archive|directors|mainStage|edit|sound",
    lateJoinProbability: "number(0..1)"
  }
};
