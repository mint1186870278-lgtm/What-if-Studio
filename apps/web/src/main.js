import "./style.css";
import { parseCreativeSession } from "@yinanping/contracts";
import { createNetwork } from "./network";
import {
  createSession,
  createVideoJob,
  fetchAgents,
  fetchGatewayCapabilities,
  fetchGatewayInvocations,
  streamDiscussion,
  watchGatewayInvocations,
  watchVideoJob
} from "./api";
import { getDisplayName } from "./displayNames";
import { createIdleDialogueEngine } from "./idleDialogueEngine";

const app = document.querySelector("#app");

app.innerHTML = `
  <div class="app-shell app-shell--stage-only">
    <div id="network-stage" class="network-stage">
      <svg class="network-svg"></svg>

      <form class="input-overlay" id="input-overlay">
        <div class="input-overlay-head">
          <div class="card-kicker">YINANPING STUDIO</div>
          <button type="button" id="overlay-toggle-btn" class="ghost-btn overlay-toggle-btn">收起</button>
        </div>
        <h1>意难平剧组</h1>
        <p class="card-summary">无限画布浏览模式已开启，可先逛房间再开机。</p>
        <p class="card-summary card-summary-soft">建议演示题材：哈利波特 / 甄嬛传 / 漫威宇宙。</p>

        <label class="field-label" for="work-title">作品名称</label>
        <input id="work-title" name="workTitle" placeholder="例如：哈利波特与凤凰社" required />

        <label class="field-label" for="ending-direction">你想要的结局</label>
        <textarea id="ending-direction" name="endingDirection" placeholder="例如：小天狼星被救下，哈利和他拥抱收尾" required></textarea>

        <label class="field-label" for="style-preference">导演风格偏好</label>
        <select id="style-preference" name="stylePreference">
          <option value="auto">AI 自动决定</option>
          <option value="darkEpic">偏黑暗史诗</option>
          <option value="warmHealing">偏温情治愈</option>
          <option value="realism">偏文艺写实</option>
          <option value="fantasyGrand">偏奇幻宏大</option>
        </select>

        <label class="field-label" for="source-video-path">素材视频路径（可选）</label>
        <input
          id="source-video-path"
          name="sourceVideoPath"
          placeholder="例如：D:\\clips\\trailer.mp4（不填将回退占位成片）"
        />
        <p id="idle-dialogue-warning" class="card-summary card-summary-soft form-warning is-hidden">
          闲聊语料加载失败，已降级为基础闲聊模式。
        </p>

        <div class="quick-actions">
          <button type="button" id="load-demo-btn" class="ghost-btn">加载示例</button>
          <button type="submit">开机 →</button>
        </div>
      </form>

      <div id="browse-controls" class="browse-controls">
        <button type="button" id="zoom-directors-btn" class="ghost-btn">导演室特写</button>
        <button type="button" id="zoom-reset-btn" class="ghost-btn">返回全景</button>
      </div>

      <div id="idle-banner" class="idle-banner">
        <div class="idle-pulse"></div>
        <span>浏览模式：你可以随时缩放逛剧组</span>
        <span class="idle-sub">点击 DIRECTORS 可窥视导演室闲聊，准备好再开机</span>
      </div>

      <div id="queue-indicator" class="queue-indicator">
        <span class="queue-dot"></span>
        <span id="queue-text">STANDBY</span>
      </div>

      <aside id="network-call-panel" class="network-call-panel">
        <div class="network-call-head">
          <span class="network-call-title">Agent Network</span>
          <span id="network-call-status" class="network-call-status">SYNCING</span>
        </div>
        <div class="network-call-meta" id="network-call-meta">加载能力目录中…</div>
        <div class="network-call-feed" id="network-call-feed"></div>
      </aside>

      <div id="live-overlay" class="live-overlay is-hidden">
        <div class="live-overlay-header">
          <span class="live-dot"></span>
          <span class="live-title" id="live-title">PRODUCTION IN PROGRESS</span>
        </div>
        <div class="phase-timeline" id="phase-timeline">
          <span data-phase="collect">collect</span>
          <span data-phase="analyze">analyze</span>
          <span data-phase="discuss">discuss</span>
          <span data-phase="edit">edit</span>
          <span data-phase="render">render</span>
          <span data-phase="deliver">deliver</span>
        </div>
        <div class="live-feed" id="live-feed"></div>
      </div>

      <div id="spotlight-card" class="spotlight-card">
        <div class="spotlight-kicker">CREW SPOTLIGHT</div>
        <div class="spotlight-name" id="spotlight-name"></div>
        <div class="spotlight-subname" id="spotlight-subname"></div>
        <div class="spotlight-role" id="spotlight-role"></div>
        <div class="spotlight-summary" id="spotlight-summary"></div>
      </div>

      <div id="agent-detail-overlay" class="agent-detail-overlay is-hidden">
        <button class="agent-detail-close" id="agent-detail-close" type="button">&times;</button>
        <div class="agent-detail-name" id="detail-name"></div>
        <div class="agent-detail-subname" id="detail-subname"></div>
        <div class="agent-detail-role" id="detail-role"></div>
        <div class="agent-detail-stage" id="detail-stage">当前状态：等待调度</div>
        <div class="agent-detail-summary" id="detail-summary"></div>
      </div>

      <section id="result-overlay" class="result-overlay is-hidden">
        <article class="result-panel">
          <h3>平行结局已完成</h3>
          <div id="result-media" class="result-media is-hidden"></div>
          <pre id="result-body"></pre>
          <button type="button" id="restart-btn">重新制作</button>
        </article>
      </section>
    </div>
  </div>
`;

const stage = document.querySelector(".network-svg");
const inputOverlay = document.querySelector("#input-overlay");
const idleBanner = document.querySelector("#idle-banner");
const liveOverlay = document.querySelector("#live-overlay");
const liveFeed = document.querySelector("#live-feed");
const liveTitle = document.querySelector("#live-title");
const resultOverlay = document.querySelector("#result-overlay");
const resultBody = document.querySelector("#result-body");
const resultMedia = document.querySelector("#result-media");
const restartBtn = document.querySelector("#restart-btn");
const spotlightCard = document.querySelector("#spotlight-card");
const spotlightName = document.querySelector("#spotlight-name");
const spotlightSubname = document.querySelector("#spotlight-subname");
const spotlightRole = document.querySelector("#spotlight-role");
const spotlightSummary = document.querySelector("#spotlight-summary");
const detailOverlay = document.querySelector("#agent-detail-overlay");
const detailName = document.querySelector("#detail-name");
const detailSubname = document.querySelector("#detail-subname");
const detailRole = document.querySelector("#detail-role");
const detailStage = document.querySelector("#detail-stage");
const detailSummary = document.querySelector("#detail-summary");
const detailClose = document.querySelector("#agent-detail-close");
const queueText = document.querySelector("#queue-text");
const networkCallFeed = document.querySelector("#network-call-feed");
const networkCallMeta = document.querySelector("#network-call-meta");
const networkCallStatus = document.querySelector("#network-call-status");
const phaseTimeline = document.querySelector("#phase-timeline");
const loadDemoBtn = document.querySelector("#load-demo-btn");
const overlayToggleBtn = document.querySelector("#overlay-toggle-btn");
const zoomDirectorsBtn = document.querySelector("#zoom-directors-btn");
const zoomResetBtn = document.querySelector("#zoom-reset-btn");
const sourceVideoPathInput = document.querySelector("#source-video-path");
const idleDialogueWarning = document.querySelector("#idle-dialogue-warning");

let networkHandle;
let unsubscribeJob = null;
let spotlightTimer = null;
let spotlightPinned = false;
let allAgents = [];
const activeAgentIds = new Set();
let lastPhaseSection = "";
let idleChatterTimer = null;
let idleFollowupTimer = null;
let idleDialogueEngine = null;
let lastIdleStatsSnapshot = null;
let overlayCollapsed = false;
let sessionRunning = false;
let activeChatChannel = "idle";
let stopGatewayWatch = null;
let gatewayInvocationItems = [];
let currentRoleBuckets = {
  participants: new Set(),
  lateJoiners: new Set(),
  observers: new Set(),
  absent: new Set()
};

function renderGatewayInvocations() {
  const items = gatewayInvocationItems.slice(0, 10);
  if (!items.length) {
    networkCallFeed.innerHTML = `<div class="network-call-empty">暂无跨 Agent 调用</div>`;
    return;
  }
  networkCallFeed.innerHTML = items
    .map((item) => {
      const statusClass = item.status === "ok" ? "is-ok" : "is-failed";
      const fallbackBadge = item.fallbackFromCapabilityId
        ? `<span class="network-call-badge">fallback from ${escapeHtml(item.fallbackFromCapabilityId)}</span>`
        : "";
      return `
        <article class="network-call-item ${statusClass}">
          <div class="network-call-route">${escapeHtml(item.caller || "unknown")} → ${escapeHtml(item.targetServiceId || "unresolved")}</div>
          <div class="network-call-capability">${escapeHtml(item.capabilityId || "unknown-capability")}</div>
          <div class="network-call-foot">
            <span>${escapeHtml(item.status || "unknown")} · ${Number(item.durationMs || 0)}ms</span>
            ${fallbackBadge}
          </div>
        </article>
      `;
    })
    .join("");
}

function pushGatewayInvocation(item) {
  if (!item || typeof item !== "object") return;
  gatewayInvocationItems = [item, ...gatewayInvocationItems].slice(0, 40);
  renderGatewayInvocations();
}

function startGatewayTraceStream() {
  if (stopGatewayWatch) stopGatewayWatch();
  stopGatewayWatch = watchGatewayInvocations((event) => {
    if (event?.event === "error") {
      networkCallStatus.textContent = "DEGRADED";
      networkCallStatus.classList.add("is-failed");
      return;
    }
    networkCallStatus.textContent = "LIVE";
    networkCallStatus.classList.remove("is-failed");
    const from = String(event?.from || event?.caller || "").trim();
    const to = String(event?.to || event?.targetServiceId || "").trim();
    if (from && to && networkHandle?.flashLink) {
      networkHandle.flashLink(from, to, {
        status: String(event?.status || ""),
        duration: event?.status === "calling" ? 1500 : 1200
      });
    }
    pushGatewayInvocation(event);
  });
}

function escapeHtml(text) {
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

function buildAvatarNameCandidates(agent) {
  const display = getDisplayName(agent || {});
  const names = new Set();
  const pushName = (value) => {
    const text = String(value || "").trim();
    if (text) names.add(text);
  };

  pushName(display.zh);
  pushName(display.en);
  pushName(agent?.name);

  if (display.zh && display.en) {
    names.add(`${display.zh}, ${display.en}`);
    names.add(`${display.zh},${display.en}`);
    names.add(`${display.en}, ${display.zh}`);
  }

  const exts = ["png", "jpg", "jpeg", "webp", "svg"];
  const urls = [];
  for (const name of names) {
    const encoded = encodeURIComponent(name);
    for (const ext of exts) {
      urls.push(`/mock/avatars/${encoded}.${ext}`);
    }
  }
  return urls;
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
  const fromConfig = buildAvatarCandidates(agent?.avatarUrl);
  const fromName = buildAvatarNameCandidates(agent);
  const candidates = [...new Set([...fromConfig, ...fromName])];
  for (const candidate of candidates) {
    // Prefer real portrait files (png/jpg/webp) when available.
    // Falls back to the original configured file.
    if (await probeImage(candidate)) return candidate;
  }
  return "";
}

async function normalizeAgentAvatars(agents) {
  return Promise.all(
    agents.map(async (agent) => ({
      ...agent,
      avatarUrl: await resolveAvatarUrl(agent)
    }))
  );
}

function renderSystemLine(text) {
  const el = document.createElement("div");
  el.className = "live-summary";
  el.innerHTML = `<span class="live-summary-label">系统</span><span>${escapeHtml(text)}</span>`;
  liveFeed.appendChild(el);
  liveFeed.scrollTop = liveFeed.scrollHeight;
}

function renderSectionLine(title) {
  const el = document.createElement("div");
  el.className = "live-section";
  el.innerHTML = `<span>${escapeHtml(title)}</span>`;
  liveFeed.appendChild(el);
  liveFeed.scrollTop = liveFeed.scrollHeight;
}

function renderSummaryLine(text) {
  const el = document.createElement("div");
  el.className = "live-summary live-summary-final";
  el.innerHTML = `<span class="live-summary-label">总结</span><span>${escapeHtml(text)}</span>`;
  liveFeed.appendChild(el);
  liveFeed.scrollTop = liveFeed.scrollHeight;
}

function discussionSectionLabel(stage) {
  if (stage === "briefing") return "briefing";
  if (stage === "topic-1") return "topic 1 · 原著底线";
  if (stage === "topic-2") return "topic 2 · 情绪曲线";
  if (stage === "topic-3") return "topic 3 · 镜头执行";
  if (stage === "finalize") return "finalize";
  return "discussion";
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
  for (const agent of allAgents) {
    const display = getDisplayName(agent);
    if (agent.name === raw || display.en === raw || display.zh === raw) {
      return display.zh || raw;
    }
  }
  return raw;
}

function findAgentBySpeaker(speaker) {
  const raw = String(speaker || "").trim();
  if (!raw) return null;
  for (const agent of allAgents) {
    const display = getDisplayName(agent);
    if (agent.name === raw || display.en === raw || display.zh === raw) {
      return agent;
    }
  }
  return null;
}

function renderMessageLine(speaker, content) {
  const agent = findAgentBySpeaker(speaker);
  const name = agent ? getDisplayName(agent).zh : resolveSpeakerDisplayName(speaker);
  const avatarHtml = agent?.avatarUrl
    ? `<img class="live-msg-avatar live-msg-avatar-image" src="${escapeHtml(agent.avatarUrl)}" alt="${escapeHtml(name)}">`
    : `<div class="live-msg-avatar live-msg-avatar-placeholder">${escapeHtml((name || "?").slice(0, 1))}</div>`;
  const bubble = document.createElement("div");
  bubble.className = "live-msg";
  bubble.innerHTML = `
    ${avatarHtml}
    <div class="live-msg-body">
      <span class="live-msg-name">${escapeHtml(name)}</span>
      <span class="live-msg-text">${escapeHtml(content)}</span>
    </div>
  `;
  liveFeed.appendChild(bubble);
  requestAnimationFrame(() => bubble.classList.add("is-visible"));
  liveFeed.scrollTop = liveFeed.scrollHeight;
}

function openLive(question) {
  sessionRunning = true;
  activeChatChannel = "live";
  liveTitle.textContent = `片场直播 | ${question}`;
  liveFeed.innerHTML = "";
  liveFeed.insertAdjacentHTML(
    "beforeend",
    `<div class="live-topic-card"><div class="live-topic-q">${escapeHtml(question)}</div></div>`
  );
  liveOverlay.classList.remove("is-fading");
  liveOverlay.classList.remove("is-hidden");
  idleBanner.classList.add("is-hidden");
  stopIdleChatter();
  queueText.textContent = "LIVE";
  lastPhaseSection = "";
  ensureDiscussionSection("briefing");
  renderSystemLine("导演组就位，讨论系统启动。");
}

function closeLive() {
  sessionRunning = false;
  activeChatChannel = "idle";
  liveOverlay.classList.remove("is-fading");
  liveOverlay.classList.add("is-hidden");
  queueText.textContent = "STANDBY";
  startIdleChatter();
}

function roleLabel(type) {
  if (type === "guardian") return "原著守门人";
  if (type === "crew") return "制作组";
  return "执行导演";
}

function toggleOverlayCollapsed(force) {
  overlayCollapsed = typeof force === "boolean" ? force : !overlayCollapsed;
  inputOverlay.classList.toggle("is-collapsed", overlayCollapsed);
  overlayToggleBtn.textContent = overlayCollapsed ? "展开" : "收起";
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

function pickRoleBuckets(payload) {
  const tags = inferTagsFromSession(payload);
  const participants = new Set();
  const lateJoiners = new Set();
  const observers = new Set();
  const absent = new Set();

  for (const agent of allAgents) {
    const agentTags = new Set(agent.interestTags || []);
    const strongMatch = [...tags].some((tag) => agentTags.has(tag));
    const isCrew = agent.type === "crew";
    const lateJoinProbability = Number(agent.lateJoinProbability || 0);

    if (strongMatch || isCrew) {
      if (!isCrew && Math.random() < lateJoinProbability) lateJoiners.add(agent.agentId);
      else participants.add(agent.agentId);
      continue;
    }

    if (agent.type === "guardian" || agent.type === "director") {
      if (Math.random() < 0.58) observers.add(agent.agentId);
      else absent.add(agent.agentId);
    } else {
      absent.add(agent.agentId);
    }
  }

  return { participants, lateJoiners, observers, absent };
}

function setRoleBuckets(bucketSets) {
  currentRoleBuckets = bucketSets;
  if (!networkHandle) return;
  networkHandle.setRoleBuckets({
    participants: [...bucketSets.participants],
    lateJoiners: [...bucketSets.lateJoiners],
    observers: [...bucketSets.observers],
    absent: [...bucketSets.absent]
  });
}

function ensureActiveFromBuckets() {
  activeAgentIds.clear();
  for (const id of currentRoleBuckets.participants) activeAgentIds.add(id);
}

function inferIdleTagsFromForm() {
  const workTitleInput = document.querySelector("#work-title");
  const endingDirectionInput = document.querySelector("#ending-direction");
  const stylePreferenceInput = document.querySelector("#style-preference");
  const pseudoSession = {
    workTitle: String(workTitleInput?.value || "").trim(),
    endingDirection: String(endingDirectionInput?.value || "").trim(),
    stylePreference: String(stylePreferenceInput?.value || "auto")
  };
  return [...inferTagsFromSession(pseudoSession)];
}

function reportIdleStats() {
  if (!idleDialogueEngine) return;
  const stats = idleDialogueEngine.getStats();
  if (!stats) return;
  const changed =
    !lastIdleStatsSnapshot ||
    stats.rounds !== lastIdleStatsSnapshot.rounds ||
    stats.repetitionRate !== lastIdleStatsSnapshot.repetitionRate;
  if (!changed || stats.rounds === 0 || stats.rounds % 5 !== 0) return;
  lastIdleStatsSnapshot = stats;
  console.log(
    `[idle-dialogue] rounds=${stats.rounds} repeatRate=${stats.repetitionRate} duplicateAvoided=${stats.duplicateAvoidedCount} fallback=${stats.fallbackCount}`
  );
}

function renderIdleDialogueTurn() {
  if (sessionRunning || activeChatChannel !== "idle" || !allAgents.length || !networkHandle || !idleDialogueEngine) return null;
  const stylePreferenceInput = document.querySelector("#style-preference");
  const round = idleDialogueEngine.nextRound({
    stylePreference: String(stylePreferenceInput?.value || "auto"),
    tags: inferIdleTagsFromForm()
  });
  if (!round) return null;
  networkHandle.showAgentSpeech(round.speakerAId, round.lineA, { duration: 3400 });
  if (idleFollowupTimer) window.clearTimeout(idleFollowupTimer);
  idleFollowupTimer = window.setTimeout(() => {
    if (sessionRunning || !networkHandle) return;
    networkHandle.showAgentSpeech(round.speakerBId, round.lineB, { duration: 3400 });
  }, round.replyDelayMs);
  reportIdleStats();
  return round.nextDelayMs;
}

function runIdleChatterCycle() {
  if (sessionRunning || activeChatChannel !== "idle") return;
  const nextDelayMs = renderIdleDialogueTurn();
  const delay = Number.isFinite(nextDelayMs) ? nextDelayMs : 9000;
  idleChatterTimer = window.setTimeout(runIdleChatterCycle, delay);
}

function startIdleChatter() {
  if (sessionRunning || activeChatChannel !== "idle") return;
  if (idleChatterTimer) window.clearTimeout(idleChatterTimer);
  runIdleChatterCycle();
}

function stopIdleChatter() {
  if (idleChatterTimer) window.clearTimeout(idleChatterTimer);
  if (idleFollowupTimer) window.clearTimeout(idleFollowupTimer);
  idleChatterTimer = null;
  idleFollowupTimer = null;
  if (networkHandle) networkHandle.clearAllSpeech();
}

function updateSpotlight(agent) {
  if (!agent || spotlightPinned) return;
  const name = getDisplayName(agent);
  spotlightName.textContent = name.zh;
  spotlightSubname.textContent = name.en;
  spotlightRole.textContent = roleLabel(agent.type);
  spotlightSummary.textContent = agent.stance || "等待分配任务。";
}

function startSpotlight() {
  if (spotlightTimer) window.clearInterval(spotlightTimer);
  if (!allAgents.length) return;
  updateSpotlight(allAgents[0]);
  spotlightTimer = window.setInterval(() => {
    if (spotlightPinned) return;
    const idx = Math.floor(Math.random() * allAgents.length);
    updateSpotlight(allAgents[idx]);
  }, 9000);
}

function showAgentDetail(agent) {
  spotlightPinned = true;
  spotlightCard.classList.add("is-hidden");
  const name = getDisplayName(agent);
  detailName.textContent = name.zh;
  detailSubname.textContent = name.en;
  detailRole.textContent = roleLabel(agent.type);
  detailStage.textContent = activeAgentIds.has(agent.agentId) ? "当前状态：参与本轮任务" : "当前状态：空闲";
  detailSummary.textContent = agent.stance || "暂无描述";
  detailOverlay.classList.remove("is-hidden");
  if (networkHandle) networkHandle.setSelected(agent.agentId);
}

function hideAgentDetail() {
  spotlightPinned = false;
  detailOverlay.classList.add("is-hidden");
  spotlightCard.classList.remove("is-hidden");
  if (networkHandle) networkHandle.setSelected(null);
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

function markTimelinePhase(phase) {
  const labels = phaseTimeline.querySelectorAll("span");
  labels.forEach((label) => {
    label.classList.toggle("is-active", label.dataset.phase === phase);
  });
}

function updateActiveAgentsFromNames(names, leadName = null) {
  if (!allAgents.length || !networkHandle) return;
  for (const name of names || []) {
    const hit = allAgents.find((agent) => agent.name === name);
    if (hit) {
      if (currentRoleBuckets.lateJoiners.has(hit.agentId)) {
        networkHandle.triggerLateJoiner(hit.agentId);
        currentRoleBuckets.participants.add(hit.agentId);
        currentRoleBuckets.lateJoiners.delete(hit.agentId);
      }
      activeAgentIds.add(hit.agentId);
    }
  }
  const ids = Array.from(activeAgentIds);
  const leadId = allAgents.find((agent) => agent.name === leadName)?.agentId || null;
  networkHandle.setActiveAgents(ids, leadId);
}

function showResult(result) {
  const publicUrl = String(result?.publicUrl || "");
  const hasPlayableMp4 =
    publicUrl &&
    (result?.type === "video-mp4" ||
      result?.type === "video-mp4-fallback" ||
      publicUrl.toLowerCase().endsWith(".mp4"));
  const summary = [
    `类型: ${result?.type || "placeholder"}`,
    `标题: ${result?.title || "未命名作品"}`,
    publicUrl ? `播放地址: ${publicUrl}` : "",
    "",
    result?.text || "当前为占位成片，可接入真实视频渲染后替换。"
  ]
    .filter(Boolean)
    .join("\n");
  resultBody.textContent = summary;
  if (hasPlayableMp4) {
    resultMedia.classList.remove("is-hidden");
    resultMedia.innerHTML = `
      <video controls preload="metadata" src="${escapeHtml(publicUrl)}"></video>
      <a href="${escapeHtml(publicUrl)}" target="_blank" rel="noreferrer">在新窗口打开视频</a>
    `;
  } else {
    resultMedia.classList.add("is-hidden");
    resultMedia.innerHTML = "";
  }
  resultOverlay.classList.remove("is-hidden");
}

async function loadIdleDialogueLibrary() {
  try {
    const res = await fetch("/mock/idle-directors-dialogues.json");
    if (!res.ok) throw new Error(`status ${res.status}`);
    const data = await res.json();
    return { dialogues: Array.isArray(data) ? data : [], degraded: false };
  } catch (error) {
    console.warn("idle dialogue library load failed, fallback to empty pool", error);
    return { dialogues: [], degraded: true };
  }
}

async function bootstrap() {
  const [fetchedAgents, idleDialogueResult, gatewayCapabilities, gatewayInvocations] = await Promise.all([
    fetchAgents().catch(async () => {
      const fallback = await fetch("/mock/agents.json").then((res) => res.json());
      return Array.isArray(fallback) ? fallback : [];
    }),
    loadIdleDialogueLibrary(),
    fetchGatewayCapabilities().catch(() => []),
    fetchGatewayInvocations(16).catch(() => [])
  ]);
  const agents = await normalizeAgentAvatars(fetchedAgents);
  gatewayInvocationItems = Array.isArray(gatewayInvocations) ? gatewayInvocations : [];
  renderGatewayInvocations();
  networkCallMeta.textContent = `已发现 ${gatewayCapabilities.length} 个可调用能力`;
  networkCallStatus.textContent = "LIVE";
  networkCallStatus.classList.remove("is-failed");
  startGatewayTraceStream();
  allAgents = agents;
  if (idleDialogueResult.degraded) {
    idleDialogueWarning?.classList.remove("is-hidden");
  }
  idleDialogueEngine = createIdleDialogueEngine({
    agents,
    dialogues: idleDialogueResult.dialogues,
    pairCooldown: 8,
    dialogueCooldown: 16,
    signatureCooldown: 20
  });
  networkHandle = createNetwork(stage, agents, {
    onSelectAgent: (agent) => showAgentDetail(agent),
    onClearSelection: () => hideAgentDetail(),
    onZoneFocusChange: (zoneKey, zoomScale) => {
      if (!zoneKey || zoomScale < 1.05) {
        detailStage.textContent = activeAgentIds.size ? "当前状态：参与本轮任务" : "当前状态：空闲";
        return;
      }
      detailStage.textContent = `当前视角：${zoneKey.toUpperCase()} (${zoomScale.toFixed(2)}x)`;
    }
  });
  startSpotlight();
  setRoleBuckets({
    participants: new Set(),
    lateJoiners: new Set(),
    observers: new Set(),
    absent: new Set()
  });
  startIdleChatter();
}

inputOverlay.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(inputOverlay);

  const candidate = {
    workTitle: String(formData.get("workTitle") || "").trim(),
    endingDirection: String(formData.get("endingDirection") || "").trim(),
    stylePreference: String(formData.get("stylePreference") || "auto")
  };
  const sourceVideoPath = String(formData.get("sourceVideoPath") || "").trim();

  let payload;
  try {
    payload = parseCreativeSession(candidate);
  } catch (error) {
    alert(`输入校验失败：${error.message}`);
    return;
  }

  toggleOverlayCollapsed(true);
  spotlightCard.classList.add("is-hidden");
  setRoleBuckets(pickRoleBuckets(payload));
  ensureActiveFromBuckets();
  networkHandle.gather();
  networkHandle.setPhase("forming");
  networkHandle.setActiveAgents([...activeAgentIds]);
  openLive(payload.workTitle);
  markTimelinePhase("collect");
  renderSystemLine("会话创建中…");
  renderSystemLine(`参与导演 ${currentRoleBuckets.participants.size} 位，迟到候选 ${currentRoleBuckets.lateJoiners.size} 位。`);

  try {
    const { session } = await createSession(payload);
    renderSystemLine(`会话已创建：${session.sessionId}`);
    renderSystemLine("导演与原著守门人讨论中…");
    networkHandle.pulseZone("mainStage");
    networkHandle.setPhase("discuss");
    markTimelinePhase("discuss");

    await streamDiscussion(session.sessionId, (turn) => {
      if (!sessionRunning || activeChatChannel !== "live") return;
      if (turn.event === "turn") {
        ensureDiscussionSection(turn.stage);
        renderMessageLine(turn.speaker, turn.content);
        updateActiveAgentsFromNames([turn.speaker], turn.speaker);
        const speaker = allAgents.find((agent) => agent.name === turn.speaker);
        if (speaker) networkHandle.showAgentSpeech(speaker.agentId, turn.content, { duration: 3600 });
      } else if (turn.event === "topic") {
        ensureDiscussionSection(turn.stage);
        renderSystemLine(`${turn.title}｜${turn.goal}`);
      } else if (turn.event === "system") {
        ensureDiscussionSection(turn.stage);
        renderSystemLine(turn.content);
      } else if (turn.event === "summary") {
        ensureDiscussionSection(turn.stage);
        renderSummaryLine(turn.content);
      } else if (turn.event === "done") {
        renderSummaryLine("讨论结论已达成，剧组进入制作管线。");
        renderSectionLine("pipeline");
      }
    });

    const { job } = await createVideoJob(session.sessionId, sourceVideoPath);
    renderSystemLine(`视频任务已创建：${job.jobId}`);
    networkHandle.setPhase("collect");
    markTimelinePhase("collect");

    unsubscribeJob = watchVideoJob(job.jobId, (evt) => {
      if (evt.event === "progress") {
        const phase = mapPhaseByProgressText(`${evt.phase}: ${evt.message}`);
        if (lastPhaseSection !== phase) {
          renderSectionLine(phaseLabel(phase));
          lastPhaseSection = phase;
        }
        renderSystemLine(`${evt.phase}: ${evt.message}`);
        networkHandle.setPhase(phase);
        markTimelinePhase(phase === "forming" ? "collect" : phase);
      } else if (evt.event === "complete") {
        renderSummaryLine("制作完成，正在回放平行结局。");
        markTimelinePhase("deliver");
        networkHandle.scatterAfterWrapup();
        networkHandle.setActiveAgents([]);
        window.setTimeout(() => networkHandle.release(), 7600);
        liveOverlay.classList.add("is-fading");
        setTimeout(() => {
          closeLive();
          spotlightCard.classList.remove("is-hidden");
          showResult(evt.result);
        }, 1400);
      } else if (evt.event === "error") {
        renderSystemLine(evt.message || "任务事件流中断。");
      }
    });
  } catch (error) {
    renderSystemLine(`任务失败：${error.message}`);
    networkHandle.release();
    networkHandle.setActiveAgents([]);
    setRoleBuckets({
      participants: new Set(),
      lateJoiners: new Set(),
      observers: new Set(),
      absent: new Set()
    });
    toggleOverlayCollapsed(false);
    idleBanner.classList.remove("is-hidden");
    spotlightCard.classList.remove("is-hidden");
    queueText.textContent = "ERROR";
  }
});

restartBtn.addEventListener("click", () => {
  if (unsubscribeJob) unsubscribeJob();
  resultOverlay.classList.add("is-hidden");
  resultMedia.classList.add("is-hidden");
  resultMedia.innerHTML = "";
  toggleOverlayCollapsed(false);
  idleBanner.classList.remove("is-hidden");
  spotlightCard.classList.remove("is-hidden");
  hideAgentDetail();
  queueText.textContent = "STANDBY";
  activeChatChannel = "idle";
  activeAgentIds.clear();
  setRoleBuckets({
    participants: new Set(),
    lateJoiners: new Set(),
    observers: new Set(),
    absent: new Set()
  });
  if (networkHandle) {
    networkHandle.setActiveAgents([]);
    networkHandle.setPhase("idle");
  }
  liveFeed.innerHTML = "";
  startIdleChatter();
});

detailClose.addEventListener("click", hideAgentDetail);
overlayToggleBtn.addEventListener("click", () => toggleOverlayCollapsed());
zoomDirectorsBtn.addEventListener("click", () => networkHandle?.zoomToZone("directors"));
zoomResetBtn.addEventListener("click", () => networkHandle?.resetCamera());
loadDemoBtn.addEventListener("click", () => {
  const workTitleInput = document.querySelector("#work-title");
  const endingDirectionInput = document.querySelector("#ending-direction");
  const stylePreferenceInput = document.querySelector("#style-preference");
  workTitleInput.value = "哈利波特与凤凰社";
  endingDirectionInput.value = "小天狼星在神秘事务司被救下，最终和哈利拥抱和解。";
  stylePreferenceInput.value = "warmHealing";
  sourceVideoPathInput.value = "";
});

bootstrap();
