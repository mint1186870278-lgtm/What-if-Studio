<template>
  <div class="app-shell app-shell--stage-only">
    <div id="network-stage" class="network-stage">
      <svg ref="stageRef" class="network-svg"></svg>

      <SessionForm
        :form="form"
        :collapsed="ui.overlayCollapsed"
        :idle-dialogue-warning="ui.idleDialogueWarning"
        :selected-file-name="selectedFileName"
        @submit="startSession"
        @toggle="toggleOverlayCollapsed"
        @load-demo="loadDemo"
        @file-change="setSourceVideoFile"
      />

      <BrowseControls @zoom-directors="zoomToDirectors" @zoom-reset="resetCamera" />
      <IdleBanner :visible="ui.idleBannerVisible" />
      <QueueIndicator :text="ui.queueText" />

      <LiveOverlay
        :visible="ui.liveVisible"
        :fading="ui.liveFading"
        :title="ui.liveTitle"
        :phases="phases"
        :active-phase="ui.activePhase"
        :items="liveItems"
        :retry-visible="ui.retryVisible"
        :retry-label="ui.retryLabel"
        @retry="retryStream"
        @feed-ready="setLiveFeedRef"
      />

      <AgentPanels
        :spotlight-visible="ui.spotlightVisible"
        :spotlight="spotlight"
        :detail="detail"
        @close-detail="hideAgentDetail"
      />

      <ResultModal
        :result="result"
        @close="hideResultOverlay"
        @download-share="downloadShare"
        @restart="restart"
      />

      <ScriptReviewModal
        :review="scriptReview"
        @confirm="confirmGenerate"
        @cancel="cancelGenerate"
        @backdrop="onScriptBackdropClick"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { createNetwork } from "./network";
import {
  createProject,
  fetchAgents,
  getProject,
  streamProjectDiscussion,
  streamProjectGeneration,
  uploadVideoSource,
  updateProject
} from "./api";
import { idleDialogues } from "./data/idleDialogues";
import { displayAgent, normalizeAgentAvatars } from "./utils/studioFormat";

const IDLE_SPEECH_DURATION_MS = 3200;
const IDLE_REPLY_GAP_MS = 3000;
const DISCUSSION_PLAYBACK_MIN_DELAY_MS = 520;
const DISCUSSION_PLAYBACK_MAX_DELAY_MS = 1300;
const EXECUTION_GUARD_WORDS = ["进入制作", "制作阶段", "镜头清单", "任务", "导出", "流程", "调度", "管线", "粗剪", "渲染"];
const IDLE_NEXT_DELAY_RANGE = [11000, 18000];

function asNonEmptyText(value, fieldLabel) {
  const text = String(value || "").trim();
  if (!text) throw new Error(`${fieldLabel}不能为空`);
  return text;
}

function parseCreativeSession(candidate) {
  const payload = candidate && typeof candidate === "object" ? candidate : {};
  const stylePreference = String(payload.stylePreference || "auto").trim();
  if (!new Set(["auto", "darkEpic", "warmHealing", "realism", "fantasyGrand"]).has(stylePreference)) {
    throw new Error("导演风格偏好不合法");
  }
  return {
    workTitle: asNonEmptyText(payload.workTitle, "作品名称"),
    endingDirection: asNonEmptyText(payload.endingDirection, "结局方向"),
    stylePreference
  };
}

function createEmptyRoleBuckets() {
  return {
    participants: new Set(),
    lateJoiners: new Set(),
    observers: new Set(),
    absent: new Set()
  };
}

function inferTagsFromSession(payload) {
  const text = `${payload.workTitle} ${payload.endingDirection}`.toLowerCase();
  const tags = new Set();
  if (text.includes("爱") || text.includes("拥抱") || text.includes("团圆")) tags.add("romance");
  if (text.includes("战争") || text.includes("史诗") || text.includes("救世")) tags.add("epic");
  if (text.includes("魔法") || text.includes("奇幻") || text.includes("龙")) tags.add("fantasy");
  if (text.includes("原著") || text.includes("改编") || text.includes("设定")) tags.add("adaptation");
  if (payload.stylePreference === "fantasyGrand") tags.add("fantasy");
  if (payload.stylePreference === "darkEpic") tags.add("epic");
  if (payload.stylePreference === "warmHealing") tags.add("romance");
  if (!tags.size) tags.add("drama");
  return tags;
}

function pickRoleBuckets(nextAgents, payload) {
  const tags = inferTagsFromSession(payload);
  const participants = new Set();
  const observers = new Set();
  const absent = new Set();
  const mustJoinByTag = new Map([
    ["romance", new Set(["agent-curtis"])],
    ["epic", new Set(["agent-jackson"])],
    ["adaptation", new Set(["agent-rowling", "agent-tolkien"])]
  ]);
  const mandatoryJoiners = new Set();
  for (const tag of tags) {
    const mapped = mustJoinByTag.get(tag);
    if (mapped) for (const agentId of mapped) mandatoryJoiners.add(agentId);
  }

  function interestScore(agent) {
    const agentTags = new Set(agent.interestTags || []);
    let score = 0;
    for (const tag of tags) if (agentTags.has(tag)) score += 0.42;
    if (agent.type === "guardian" && tags.has("adaptation")) score += 0.42;
    if (agent.type === "director" && tags.has("romance") && agentTags.has("romance")) score += 0.2;
    if (agent.type === "director" && tags.has("epic") && agentTags.has("epic")) score += 0.2;
    return Math.min(1, score + Math.random() * 0.16);
  }

  for (const agent of nextAgents) {
    if (agent.type === "crew") {
      participants.add(agent.agentId);
      continue;
    }
    if (agent.type !== "guardian" && agent.type !== "director") {
      absent.add(agent.agentId);
      continue;
    }
    const score = interestScore(agent);
    if (mandatoryJoiners.has(agent.agentId) || score >= 0.72) participants.add(agent.agentId);
    else if (score >= 0.2) observers.add(agent.agentId);
    else absent.add(agent.agentId);
  }

  const stagedCount = [...participants].filter((agentId) => {
    const agent = nextAgents.find((item) => item.agentId === agentId);
    return agent?.type === "director" || agent?.type === "guardian";
  }).length;
  const shortfall = Math.max(0, 4 - stagedCount);
  if (shortfall > 0) {
    const candidates = nextAgents
      .filter((agent) => (agent.type === "director" || agent.type === "guardian") && !participants.has(agent.agentId))
      .sort(() => Math.random() - 0.5)
      .slice(0, shortfall);
    for (const agent of candidates) {
      observers.delete(agent.agentId);
      absent.delete(agent.agentId);
      participants.add(agent.agentId);
    }
  }

  return { participants, lateJoiners: new Set(), observers, absent };
}

function randomInt(min, max) {
  const start = Math.ceil(min);
  const end = Math.floor(max);
  return Math.floor(Math.random() * (end - start + 1)) + start;
}

function containsExecutionWords(text) {
  const source = String(text || "");
  return EXECUTION_GUARD_WORDS.some((word) => source.includes(word));
}

function buildIdleDialoguePool() {
  return idleDialogues
    .filter((entry) => Array.isArray(entry) && entry.length >= 2)
    .map(([lineA, lineB]) => [String(lineA || "").trim(), String(lineB || "").trim()])
    .filter(([lineA, lineB]) => lineA && lineB && !containsExecutionWords(lineA) && !containsExecutionWords(lineB));
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function calcPlaybackDelay(text, fallback = 760) {
  const length = String(text || "").trim().length;
  if (!length) return fallback;
  return Math.max(
    DISCUSSION_PLAYBACK_MIN_DELAY_MS,
    Math.min(DISCUSSION_PLAYBACK_MAX_DELAY_MS, Math.floor(380 + length * 18))
  );
}

function emptyDetail() {
  return {
    agent: null,
    name: "",
    subname: "",
    role: "",
    stage: "当前状态：等待调度",
    summary: ""
  };
}

function emptyScriptReview() {
  return {
    visible: false,
    content: "",
    progress: "等待生成",
    videoUrl: "",
    canGenerate: true,
    generateVisible: true,
    openedAtMs: 0
  };
}

function emptyResult() {
  return {
    visible: false,
    title: "平行结局已完成",
    workName: "意难平剧组",
    mediaUrl: "",
    hasPlayableMp4: false,
    notes: [],
    payload: null
  };
}

function setProjectQuery(projectId) {
  const url = new URL(window.location.href);
  if (projectId) url.searchParams.set("project", projectId);
  else url.searchParams.delete("project");
  window.history.replaceState({}, "", url.toString());
}

function mapPhaseByProgressText(text) {
  if (text.includes("collect") || text.includes("素材")) return "collect";
  if (text.includes("analyze") || text.includes("分析")) return "analyze";
  if (text.includes("discuss") || text.includes("讨论")) return "discuss";
  if (text.includes("edit") || text.includes("剪辑")) return "edit";
  if (text.includes("render") || text.includes("导出")) return "render";
  return "forming";
}

function phaseLabel(phase) {
  if (phase === "collect") return "collect";
  if (phase === "analyze") return "analyze";
  if (phase === "discuss") return "discuss";
  if (phase === "edit") return "edit";
  if (phase === "render") return "render";
  if (phase === "deliver") return "deliver";
  return "runtime";
}

function discussionSectionLabel(stage) {
  if (stage === "briefing") return "briefing";
  if (stage === "topic-1") return "topic 1 · 原著底线";
  if (stage === "topic-2") return "topic 2 · 情绪曲线";
  if (stage === "topic-3") return "topic 3 · 镜头执行";
  if (stage === "finalize") return "finalize";
  return "discussion";
}
import AgentPanels from "./components/AgentPanels.vue";
import BrowseControls from "./components/BrowseControls.vue";
import IdleBanner from "./components/IdleBanner.vue";
import LiveOverlay from "./components/LiveOverlay.vue";
import QueueIndicator from "./components/QueueIndicator.vue";
import ResultModal from "./components/ResultModal.vue";
import ScriptReviewModal from "./components/ScriptReviewModal.vue";
import SessionForm from "./components/SessionForm.vue";

const stageRef = ref(null);
const liveFeedRef = ref(null);

const form = reactive({
  workTitle: "",
  endingDirection: "",
  stylePreference: "auto",
  sourceVideoFile: null
});

const ui = reactive({
  overlayCollapsed: false,
  idleDialogueWarning: false,
  idleBannerVisible: true,
  queueText: "STANDBY",
  liveVisible: false,
  liveFading: false,
  liveTitle: "PRODUCTION IN PROGRESS",
  activePhase: "",
  spotlightVisible: true,
  spotlightPinned: false,
  retryVisible: false,
  retryLabel: "重试流连接"
});

const liveItems = ref([]);
const agents = ref([]);
const activeAgentIds = reactive(new Set());
const currentRoleBuckets = ref(createEmptyRoleBuckets());
const spotlight = reactive({
  name: "",
  subname: "",
  role: "",
  summary: ""
});
const detail = reactive(emptyDetail());
const scriptReview = reactive(emptyScriptReview());
const result = reactive(emptyResult());

let networkHandle = null;
let spotlightTimer = null;
let idleChatterTimer = null;
let idleFollowupTimer = null;
let idleDialoguePool = [];
const recentIdleDialogueKeys = [];
let idleSpeechVisibleByZoom = false;
let sessionRunning = false;
let activeChatChannel = "idle";
let streamRetryAction = null;
let latestSessionTitle = "";
let latestDiscussionTranscript = [];
let activeProjectId = null;
let latestGeneratedScript = "";
let lastPhaseSection = "";
let discussionPlaybackQueue = [];
let discussionPlaybackDone = false;
let resolveGenerateConfirm = null;
let rejectGenerateConfirm = null;
const discussionChunkBySpeaker = new Map();

const phases = ["collect", "analyze", "discuss", "edit", "render", "deliver"];
const selectedFileName = computed(() => form.sourceVideoFile?.name || "");

function scrollLiveFeed() {
  nextTick(() => {
    const el = liveFeedRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

function addLiveItem(item) {
  liveItems.value.push({ id: `${Date.now()}-${Math.random()}`, ...item });
  scrollLiveFeed();
}

function renderSystemLine(text) {
  addLiveItem({ kind: "system", label: "系统", text });
}

function renderSectionLine(title) {
  addLiveItem({ kind: "section", title });
}

function renderSummaryLine(text) {
  addLiveItem({ kind: "summary", label: "总结", text });
}

function renderMessageLine(speaker, content) {
  const agent = findAgentBySpeaker(speaker);
  const name = agent ? agent.name : resolveSpeakerDisplayName(speaker);
  addLiveItem({
    kind: "message",
    speaker: name,
    content,
    avatarUrl: agent?.avatarUrl || "",
    avatarFallback: (name || "?").slice(0, 1)
  });
}

function ensureDiscussionSection(stage) {
  const section = discussionSectionLabel(stage);
  if (lastPhaseSection === section) return;
  renderSectionLine(section);
  lastPhaseSection = section;
}

function resolveSpeakerDisplayName(speaker) {
  const raw = String(speaker || "").trim();
  if (!raw) return "未知";
  for (const agent of agents.value) if (agent.name === raw || agent.agentId === raw) return agent.name || raw;
  return raw;
}

function findAgentBySpeaker(speaker) {
  const raw = String(speaker || "").trim();
  if (!raw) return null;
  return (
    agents.value.find((agent) => {
      return agent.agentId === raw || agent.name === raw;
    }) || null
  );
}

function setStreamRetryAction(label, action) {
  streamRetryAction = typeof action === "function" ? action : null;
  ui.retryLabel = label || "重试流连接";
  ui.retryVisible = Boolean(streamRetryAction);
}

function clearStreamRetryAction() {
  streamRetryAction = null;
  ui.retryVisible = false;
  ui.retryLabel = "重试流连接";
}

async function retryStream() {
  if (!streamRetryAction) return;
  const action = streamRetryAction;
  clearStreamRetryAction();
  try {
    await action();
  } catch (error) {
    renderSystemLine(`重试失败：${error.message}`);
  }
}

function openLive(question) {
  sessionRunning = true;
  activeChatChannel = "live";
  idleSpeechVisibleByZoom = false;
  latestDiscussionTranscript = [];
  liveItems.value = [{ id: "topic", kind: "topic", text: question }];
  ui.liveTitle = `片场直播 | ${question}`;
  ui.liveFading = false;
  ui.liveVisible = true;
  ui.idleBannerVisible = false;
  ui.queueText = "LIVE";
  clearStreamRetryAction();
  stopIdleChatter();
  networkHandle?.setIdleSpeechEnabled(false);
  scrollLiveFeed();
}

function closeLive() {
  ui.liveVisible = false;
  ui.liveFading = false;
  ui.idleBannerVisible = true;
  ui.queueText = "STANDBY";
  ui.activePhase = "";
  sessionRunning = false;
  activeChatChannel = "idle";
  lastPhaseSection = "";
}

function openScriptReview(scriptText) {
  Object.assign(scriptReview, {
    visible: true,
    content: scriptText || "暂无脚本",
    progress: "讨论完成，等待确认生成视频",
    videoUrl: "",
    canGenerate: true,
    generateVisible: true,
    openedAtMs: Date.now()
  });
}

function closeScriptReview() {
  scriptReview.visible = false;
}

function waitForGenerateConfirm() {
  return new Promise((resolve, reject) => {
    resolveGenerateConfirm = resolve;
    rejectGenerateConfirm = reject;
  });
}

function confirmGenerate() {
  const resolve = resolveGenerateConfirm;
  resolveGenerateConfirm = null;
  rejectGenerateConfirm = null;
  if (resolve) resolve(true);
}

function cancelGenerate() {
  closeScriptReview();
  const reject = rejectGenerateConfirm;
  resolveGenerateConfirm = null;
  rejectGenerateConfirm = null;
  if (reject) reject(new Error("已取消生成"));
}

function onScriptBackdropClick() {
  if (Date.now() - scriptReview.openedAtMs < 300) return;
  cancelGenerate();
}

function buildCrewNotes() {
  const participantIds = [...currentRoleBuckets.value.participants].filter((agentId) => isParticipantAgentId(agentId));
  return participantIds
    .map((agentId) => agents.value.find((agent) => agent.agentId === agentId))
    .filter(Boolean)
    .slice(0, 3)
    .map((agent) => {
      return {
        id: agent.agentId,
        name: agent.name || "",
        avatarUrl: agent.avatarUrl || "",
        fallback: (agent.name || "?").slice(0, 1),
        text: agent.stance || "参与本次平行结局制作。"
      };
    });
}

function showResult(nextResult) {
  const publicUrl = String(nextResult?.publicUrl || "");
  const hasPlayableMp4 =
    publicUrl &&
    (nextResult?.type === "video-mp4" ||
      nextResult?.type === "video-mp4-fallback" ||
      publicUrl.toLowerCase().endsWith(".mp4"));
  Object.assign(result, {
    visible: true,
    title: "平行结局已完成",
    workName: latestSessionTitle || "意难平剧组",
    mediaUrl: publicUrl,
    hasPlayableMp4,
    notes: buildCrewNotes(),
    payload: nextResult || null
  });
}

function hideResultOverlay() {
  result.visible = false;
}

function clearResultOverlay() {
  Object.assign(result, emptyResult());
}

function resetSessionUiToIdle() {
  closeLive();
  ui.spotlightVisible = true;
  ui.idleBannerVisible = true;
  ui.overlayCollapsed = false;
  clearStreamRetryAction();
  networkHandle?.release();
  networkHandle?.setActiveAgents([]);
  activeAgentIds.clear();
  currentRoleBuckets.value = createEmptyRoleBuckets();
  networkHandle?.setRoleBuckets(currentRoleBuckets.value);
}

function keepErrorState(message) {
  sessionRunning = false;
  activeChatChannel = "live";
  renderSystemLine(`发生错误：${message}`);
  ui.queueText = "ERROR";
  ui.liveVisible = true;
  ui.liveFading = false;
  ui.idleBannerVisible = false;
}

function markTimelinePhase(phase) {
  ui.activePhase = phase;
}

function toggleOverlayCollapsed(force) {
  ui.overlayCollapsed = typeof force === "boolean" ? force : !ui.overlayCollapsed;
}

function setRoleBuckets(bucketSets) {
  currentRoleBuckets.value = bucketSets;
  networkHandle?.setRoleBuckets({
    participants: bucketSets.participants,
    lateJoiners: bucketSets.lateJoiners,
    observers: bucketSets.observers,
    absent: bucketSets.absent
  });
}

function ensureActiveFromBuckets() {
  activeAgentIds.clear();
  for (const id of currentRoleBuckets.value.participants) activeAgentIds.add(id);
}

function countStageAuthorsAndDirectors(bucketSets) {
  let total = 0;
  for (const id of bucketSets.participants) {
    const agent = agents.value.find((item) => item.agentId === id);
    if (agent?.type === "guardian" || agent?.type === "director") total += 1;
  }
  return total;
}

function pickIdleDialogue() {
  if (!idleDialoguePool.length) return null;
  const candidates = idleDialoguePool.filter(([lineA, lineB]) => {
    const key = `${lineA}|${lineB}`;
    return !recentIdleDialogueKeys.includes(key);
  });
  const picked = candidates.length
    ? candidates[Math.floor(Math.random() * candidates.length)]
    : idleDialoguePool[Math.floor(Math.random() * idleDialoguePool.length)];
  const key = `${picked[0]}|${picked[1]}`;
  recentIdleDialogueKeys.push(key);
  while (recentIdleDialogueKeys.length > 14) recentIdleDialogueKeys.shift();
  return picked;
}

function pickIdlePair() {
  const directors = agents.value.filter((agent) => agent.type !== "crew");
  if (directors.length < 2) return null;
  const speakerA = directors[Math.floor(Math.random() * directors.length)];
  const others = directors.filter((agent) => agent.agentId !== speakerA.agentId);
  return [speakerA, others[Math.floor(Math.random() * others.length)]];
}

function renderIdleDialogueTurn() {
  if (
    sessionRunning ||
    activeChatChannel !== "idle" ||
    !idleSpeechVisibleByZoom ||
    !agents.value.length ||
    !networkHandle
  ) {
    return null;
  }
  const pair = pickIdlePair();
  const dialogue = pickIdleDialogue();
  if (!pair || !dialogue) return null;
  const [speakerA, speakerB] = pair;
  const [lineA, lineB] = dialogue;
  networkHandle.showAgentSpeech(speakerA.agentId, lineA, { duration: IDLE_SPEECH_DURATION_MS });
  if (idleFollowupTimer) window.clearTimeout(idleFollowupTimer);
  idleFollowupTimer = window.setTimeout(() => {
    if (sessionRunning || !networkHandle) return;
    networkHandle.showAgentSpeech(speakerB.agentId, lineB, { duration: IDLE_SPEECH_DURATION_MS });
  }, IDLE_SPEECH_DURATION_MS + IDLE_REPLY_GAP_MS);
  return randomInt(IDLE_NEXT_DELAY_RANGE[0], IDLE_NEXT_DELAY_RANGE[1]);
}

function runIdleChatterCycle() {
  if (sessionRunning || activeChatChannel !== "idle" || !idleSpeechVisibleByZoom) return;
  const nextDelayMs = renderIdleDialogueTurn();
  idleChatterTimer = window.setTimeout(runIdleChatterCycle, Number.isFinite(nextDelayMs) ? nextDelayMs : 9000);
}

function startIdleChatter() {
  if (sessionRunning || activeChatChannel !== "idle" || !idleSpeechVisibleByZoom) return;
  if (idleChatterTimer) window.clearTimeout(idleChatterTimer);
  runIdleChatterCycle();
}

function stopIdleChatter() {
  if (idleChatterTimer) window.clearTimeout(idleChatterTimer);
  if (idleFollowupTimer) window.clearTimeout(idleFollowupTimer);
  idleChatterTimer = null;
  idleFollowupTimer = null;
  networkHandle?.clearAllSpeech();
}

function updateIdleSpeechByZoom(zoneKey) {
  const nextVisible = !sessionRunning && zoneKey === "directors";
  if (nextVisible === idleSpeechVisibleByZoom) return;
  idleSpeechVisibleByZoom = nextVisible;
  networkHandle?.setIdleSpeechEnabled(nextVisible);
  if (nextVisible) startIdleChatter();
  else stopIdleChatter();
}

function updateSpotlight(agent) {
  if (!agent || ui.spotlightPinned) return;
  const display = displayAgent(agent);
  spotlight.name = display.name;
  spotlight.subname = "";
  spotlight.role = display.role;
  spotlight.summary = display.summary;
}

function startSpotlight() {
  if (spotlightTimer) window.clearInterval(spotlightTimer);
  if (!agents.value.length) return;
  updateSpotlight(agents.value[0]);
  spotlightTimer = window.setInterval(() => {
    if (ui.spotlightPinned) return;
    updateSpotlight(agents.value[Math.floor(Math.random() * agents.value.length)]);
  }, 9000);
}

function showAgentDetail(agent) {
  ui.spotlightPinned = true;
  ui.spotlightVisible = false;
  const display = displayAgent(agent);
  detail.agent = agent;
  detail.name = display.name;
  detail.subname = "";
  detail.role = display.role;
  detail.stage = activeAgentIds.has(agent.agentId) ? "当前状态：参与本轮任务" : "当前状态：空闲";
  detail.summary = display.summary || "暂无描述";
  networkHandle?.setSelected(agent.agentId);
}

function hideAgentDetail() {
  ui.spotlightPinned = false;
  detail.agent = null;
  ui.spotlightVisible = true;
  networkHandle?.setSelected(null);
}

function updateActiveAgentsFromNames(names, leadName = null) {
  if (!agents.value.length || !networkHandle) return;
  for (const name of names || []) {
    const hit = agents.value.find((agent) => agent.name === name);
    if (!hit || !currentRoleBuckets.value.participants.has(hit.agentId)) continue;
    activeAgentIds.add(hit.agentId);
  }
  const ids = Array.from(activeAgentIds);
  const leadCandidateId = agents.value.find((agent) => agent.name === leadName)?.agentId || null;
  const leadId =
    leadCandidateId && currentRoleBuckets.value.participants.has(leadCandidateId) ? leadCandidateId : null;
  networkHandle.setActiveAgents(ids, leadId);
}

function isParticipantAgentId(agentId) {
  return Boolean(agentId && currentRoleBuckets.value.participants.has(agentId));
}

async function replayDiscussionEvent(turn) {
  if (!sessionRunning || activeChatChannel !== "live") return;
  if (turn.event === "turn_chunk" || turn.type === "turn_chunk") {
    const speaker = String(turn.speaker || "").trim();
    const chunk = String(turn.content || "");
    if (!speaker || !chunk) return;
    const speakerAgent = findAgentBySpeaker(speaker);
    const merged = `${discussionChunkBySpeaker.get(speaker) || ""}${chunk}`;
    discussionChunkBySpeaker.set(speaker, merged);
    ensureDiscussionSection(turn.stage);
    if (speakerAgent) {
      updateActiveAgentsFromNames([speakerAgent.name], speakerAgent.name);
      networkHandle.showAgentSpeech(speakerAgent.agentId, merged, {
        duration: 30000,
        force: true,
        append: false
      });
    }
    return;
  }
  if (turn.event === "turn" || turn.type === "turn") {
    const speakerAgent = findAgentBySpeaker(turn.speaker);
    const speaker = String(turn.speaker || "").trim();
    const chunkMerged = speaker ? discussionChunkBySpeaker.get(speaker) || "" : "";
    const finalContent = chunkMerged || String(turn.content || "");
    if (speaker) discussionChunkBySpeaker.delete(speaker);
    ensureDiscussionSection(turn.stage);
    renderMessageLine(turn.speaker, finalContent);
    latestDiscussionTranscript.push(`${resolveSpeakerDisplayName(turn.speaker)}：${finalContent}`);
    if (speakerAgent) {
      updateActiveAgentsFromNames([speakerAgent.name], speakerAgent.name);
      networkHandle.showAgentSpeech(speakerAgent.agentId, finalContent, {
        duration: 30000,
        force: true,
        append: false
      });
    }
    await sleep(calcPlaybackDelay(finalContent, 900));
    return;
  }
  if (turn.event === "topic" || turn.type === "topic") {
    ensureDiscussionSection(turn.stage);
    renderSystemLine(`${turn.title}｜${turn.goal}`);
    latestDiscussionTranscript.push(`系统｜${turn.title}：${turn.goal}`);
    await sleep(calcPlaybackDelay(`${turn.title}${turn.goal}`, 780));
    return;
  }
  if (turn.event === "system" || turn.type === "system") {
    ensureDiscussionSection(turn.stage);
    renderSystemLine(turn.content);
    latestDiscussionTranscript.push(`系统：${turn.content}`);
    await sleep(calcPlaybackDelay(turn.content, 700));
    return;
  }
  if (turn.event === "summary" || turn.type === "summary") {
    ensureDiscussionSection(turn.stage);
    renderSummaryLine(turn.content);
    latestDiscussionTranscript.push(`总结：${turn.content}`);
    await sleep(calcPlaybackDelay(turn.content, 820));
    return;
  }
  if (turn.event === "done" || turn.type === "done") {
    renderSummaryLine("讨论结论已达成，剧组进入制作管线。");
    latestDiscussionTranscript.push("系统：讨论结论已达成，剧组进入制作管线。");
    renderSectionLine("pipeline");
    await sleep(640);
  }
}

async function replayDiscussionEvents() {
  while (!discussionPlaybackDone || discussionPlaybackQueue.length > 0) {
    if (!sessionRunning || activeChatChannel !== "live") return;
    if (!discussionPlaybackQueue.length) {
      await sleep(50);
      continue;
    }
    const turn = discussionPlaybackQueue.shift();
    if (turn) await replayDiscussionEvent(turn);
  }
}

async function loadProjectFromQuery() {
  const url = new URL(window.location.href);
  const projectId = String(url.searchParams.get("project") || "").trim();
  if (!projectId) return;
  try {
    const project = await getProject(projectId);
    activeProjectId = String(project.id);
    if (project.name) form.workTitle = project.name;
    if (project.prompt) form.endingDirection = project.prompt;
    if (project.style_preference) form.stylePreference = project.style_preference;
    if (project.script) latestGeneratedScript = String(project.script);
  } catch {
    activeProjectId = null;
    setProjectQuery(null);
  }
}

async function bootstrap() {
  const fetchedAgents = await fetchAgents();
  agents.value = await normalizeAgentAvatars(fetchedAgents);
  ui.idleDialogueWarning = false;
  idleDialoguePool = buildIdleDialoguePool();
  if (stageRef.value) {
    networkHandle = createNetwork(stageRef.value, agents.value, {
      onSelectAgent: (agent) => showAgentDetail(agent),
      onClearSelection: () => hideAgentDetail(),
      onZoneFocusChange: (zoneKey, zoomScale) => {
        if (!zoneKey) {
          detail.stage = activeAgentIds.size ? "当前状态：参与本轮任务" : "当前状态：空闲";
          updateIdleSpeechByZoom(null, zoomScale);
          return;
        }
        detail.stage = `当前视角：${zoneKey.toUpperCase()} (${zoomScale.toFixed(2)}x)`;
        updateIdleSpeechByZoom(zoneKey, zoomScale);
      }
    });
    networkHandle.setIdleSpeechEnabled(false);
    setRoleBuckets(createEmptyRoleBuckets());
  }
  startSpotlight();
  await loadProjectFromQuery();
}

function loadDemo() {
  form.workTitle = "哈利波特与凤凰社";
  form.endingDirection = "小天狼星在神秘事务司被救下，最终和哈利拥抱和解。";
  form.stylePreference = "warmHealing";
  form.sourceVideoFile = null;
}

function setSourceVideoFile(file) {
  form.sourceVideoFile = file instanceof File && file.size > 0 ? file : null;
}

async function startSession() {
  const candidate = {
    workTitle: String(form.workTitle || "").trim(),
    endingDirection: String(form.endingDirection || "").trim(),
    stylePreference: String(form.stylePreference || "auto")
  };
  let payload;
  try {
    payload = parseCreativeSession(candidate);
  } catch (error) {
    alert(`输入校验失败：${error.message}`);
    return;
  }

  toggleOverlayCollapsed(true);
  latestSessionTitle = payload.workTitle || "未命名作品";
  ui.spotlightVisible = false;
  setRoleBuckets(pickRoleBuckets(agents.value, payload));
  ensureActiveFromBuckets();
  networkHandle.gather();
  networkHandle.setPhase("forming");
  networkHandle.setActiveAgents([...activeAgentIds]);
  openLive(payload.workTitle);
  markTimelinePhase("collect");
  renderSystemLine("会话创建中…");
  renderSystemLine(`主舞台核心成员 ${countStageAuthorsAndDirectors(currentRoleBuckets.value)} 位。`);

  try {
    if (!activeProjectId) {
      const project = await createProject({
        name: payload.workTitle,
        description: "",
        prompt: payload.endingDirection,
        style_preference: payload.stylePreference
      });
      activeProjectId = String(project.id);
      setProjectQuery(activeProjectId);
    } else {
      await updateProject(activeProjectId, {
        name: payload.workTitle,
        prompt: payload.endingDirection,
        style_preference: payload.stylePreference
      });
    }

    renderSystemLine(`工程已就绪：${activeProjectId}`);
    renderSystemLine("导演与原著守门人讨论中…");
    networkHandle.pulseZone("mainStage");
    networkHandle.setPhase("discuss");
    markTimelinePhase("discuss");

    try {
      let playbackError = null;
      discussionPlaybackQueue = [];
      discussionPlaybackDone = false;
      const playbackTask = replayDiscussionEvents();
      await streamProjectDiscussion(activeProjectId, (turn) => {
        if (turn.type === "error" || turn.event === "error") {
          playbackError = new Error(String(turn.message || turn.error || "讨论失败"));
          return;
        }
        if (turn.type === "script") {
          latestGeneratedScript = String(turn.script || "");
          return;
        }
        discussionPlaybackQueue.push(turn);
      });
      discussionPlaybackDone = true;
      await playbackTask;
      if (playbackError) throw playbackError;
    } catch (discussionError) {
      discussionPlaybackDone = true;
      setStreamRetryAction("重试讨论流（重新开机）", async () => startSession());
      throw new Error(`讨论流中断：${discussionError.message}`);
    }

    if (!latestGeneratedScript && latestDiscussionTranscript.length) {
      latestGeneratedScript = latestDiscussionTranscript.join("\n");
    }
    if (!latestGeneratedScript.trim()) {
      throw new Error("讨论未产出可用剧本，请检查 OPENAI 配置或模型响应。");
    }

    openScriptReview(latestGeneratedScript);
    await waitForGenerateConfirm();
    scriptReview.canGenerate = false;
    scriptReview.progress = "视频生成准备中…";

    if (form.sourceVideoFile) {
      renderSystemLine(`素材上传中：${form.sourceVideoFile.name}`);
      const { upload } = await uploadVideoSource(activeProjectId, form.sourceVideoFile);
      renderSystemLine(`素材上传完成：${upload.originalName}`);
    }
    renderSystemLine("视频生成流已打开。");
    networkHandle.setPhase("collect");
    markTimelinePhase("collect");

    await streamProjectGeneration(activeProjectId, (evt) => {
      if (evt.event === "progress") {
        const phase = mapPhaseByProgressText(`${evt.phase}: ${evt.message}`);
        if (lastPhaseSection !== phase) {
          renderSectionLine(phaseLabel(phase));
          lastPhaseSection = phase;
        }
        renderSystemLine(`${evt.phase}: ${evt.message}`);
        scriptReview.progress = `${evt.phase}: ${evt.message}`;
        networkHandle.setPhase(phase);
        markTimelinePhase(phase === "forming" ? "collect" : phase);
        return;
      }
      if (evt.event === "complete") {
        clearStreamRetryAction();
        renderSummaryLine("制作完成，正在回放平行结局。");
        markTimelinePhase("deliver");
        networkHandle.scatterAfterWrapup();
        networkHandle.setActiveAgents([]);
        window.setTimeout(() => networkHandle.release(), 7600);
        ui.liveFading = true;
        scriptReview.progress = "生成完成";
        const resultPayload = evt.result || {
          type: "video-mp4-fallback",
          publicUrl: evt.product || "",
        };
        const publicUrl = String(resultPayload.publicUrl || "");
        if (publicUrl) scriptReview.videoUrl = publicUrl;
        scriptReview.generateVisible = false;
        setTimeout(() => {
          closeLive();
          ui.spotlightVisible = true;
          showResult(resultPayload);
        }, 1400);
        return;
      }
      if (evt.event === "error") {
        throw new Error(evt.message || "任务事件流中断");
      }
    });
  } catch (error) {
    if (String(error?.message || "") === "已取消生成") {
      renderSystemLine("已取消本次生成。");
      resetSessionUiToIdle();
      return;
    }
    const errMsg = String(error?.message || "未知错误");
    scriptReview.progress = `失败：${errMsg}`;
    scriptReview.canGenerate = true;
    networkHandle.release();
    keepErrorState(errMsg);
  }
}

async function downloadShare() {
  const publicUrl = String(result.payload?.publicUrl || "");
  if (!publicUrl) {
    alert("当前暂无可下载或分享的视频链接。");
    return;
  }
  const anchor = document.createElement("a");
  anchor.href = publicUrl.trim();
  anchor.download = `${latestSessionTitle || "parallel-ending"}.mp4`;
  anchor.target = "_blank";
  anchor.rel = "noreferrer";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(publicUrl.trim());
      renderSystemLine("视频链接已复制到剪贴板，可直接分享。");
    } catch {
      // Clipboard permission is best-effort only.
    }
  }
}

function restart() {
  clearResultOverlay();
  resetSessionUiToIdle();
}

function zoomToDirectors() {
  networkHandle?.zoomToZone("directors");
}

function resetCamera() {
  networkHandle?.resetCamera();
}

function onEscape() {
  if (scriptReview.visible) {
    cancelGenerate();
    return;
  }
  if (result.visible) hideResultOverlay();
}

function cleanup() {
  if (spotlightTimer) window.clearInterval(spotlightTimer);
  stopIdleChatter();
}

function setLiveFeedRef(el) {
  liveFeedRef.value = el;
}

function handleKeydown(event) {
  if (event.key === "Escape") onEscape();
}

onMounted(() => {
  window.addEventListener("keydown", handleKeydown);
  bootstrap();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleKeydown);
  cleanup();
});
</script>
