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
  uploadVideoSource,
  watchGatewayInvocations,
  watchVideoJob
} from "./api";
import { getDisplayName } from "./displayNames";
import { createIdleDialogueEngine } from "./idleDialogueEngine";
import { createEmptyRoleBuckets, inferTagsFromSession, pickRoleBuckets } from "./roleBuckets";

const IDLE_SPEECH_DURATION_MS = 3200;
const IDLE_REPLY_GAP_MS = 3000;

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

        <label class="field-label" for="source-video-file">上传素材视频（可选）</label>
        <input id="source-video-file" name="sourceVideoFile" type="file" accept="video/*" />
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

      <aside id="network-call-panel" class="network-call-panel is-collapsed">
        <div class="network-call-head">
          <span class="network-call-title">Agent Network</span>
          <div class="network-call-actions">
            <span id="network-call-status" class="network-call-status">SYNCING</span>
            <button
              type="button"
              id="network-call-toggle"
              class="network-call-toggle"
              aria-expanded="false"
              aria-label="展开 Agent Network 面板"
            >
              展开
            </button>
          </div>
        </div>
        <div class="network-call-meta" id="network-call-meta">加载能力目录中…</div>
        <div class="network-call-feed" id="network-call-feed"></div>
      </aside>

      <div id="live-overlay" class="live-overlay is-hidden">
        <div class="live-overlay-header">
          <span class="live-dot"></span>
          <span class="live-title" id="live-title">PRODUCTION IN PROGRESS</span>
          <button type="button" id="retry-stream-btn" class="ghost-btn is-hidden">重试流连接</button>
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
          <header class="result-head">
            <div class="result-head-left">
              <span class="result-status-dot" aria-hidden="true"></span>
              <span id="result-title" class="result-title">平行结局已完成</span>
            </div>
            <div class="result-head-right">
              <span id="result-work-name" class="result-work-name">意难平剧组</span>
              <button type="button" id="result-close-btn" class="result-close-btn" aria-label="关闭结果弹窗">&times;</button>
            </div>
          </header>
          <div id="result-media" class="result-media is-hidden"></div>
          <section class="result-notes">
            <div class="result-notes-head">CREW NOTES</div>
            <div id="result-notes-list" class="result-notes-list"></div>
          </section>
          <footer class="result-actions">
            <div class="result-actions-left">
              <button type="button" id="download-share-btn" class="ghost-btn result-ghost-btn">下载 / 分享</button>
            </div>
            <button type="button" id="restart-btn" class="result-primary-btn">重新制作</button>
          </footer>
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
const resultTitle = document.querySelector("#result-title");
const resultWorkName = document.querySelector("#result-work-name");
const resultCloseBtn = document.querySelector("#result-close-btn");
const resultMedia = document.querySelector("#result-media");
const resultNotesList = document.querySelector("#result-notes-list");
const downloadShareBtn = document.querySelector("#download-share-btn");
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
const networkCallPanel = document.querySelector("#network-call-panel");
const networkCallFeed = document.querySelector("#network-call-feed");
const networkCallMeta = document.querySelector("#network-call-meta");
const networkCallStatus = document.querySelector("#network-call-status");
const networkCallToggle = document.querySelector("#network-call-toggle");
const phaseTimeline = document.querySelector("#phase-timeline");
const loadDemoBtn = document.querySelector("#load-demo-btn");
const overlayToggleBtn = document.querySelector("#overlay-toggle-btn");
const zoomDirectorsBtn = document.querySelector("#zoom-directors-btn");
const zoomResetBtn = document.querySelector("#zoom-reset-btn");
const sourceVideoFileInput = document.querySelector("#source-video-file");
const idleDialogueWarning = document.querySelector("#idle-dialogue-warning");
const retryStreamBtn = document.querySelector("#retry-stream-btn");

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
let gatewayReconnectTimer = null;
let gatewayInvocationItems = [];
let streamRetryAction = null;
let currentRoleBuckets = createEmptyRoleBuckets();
let idleSpeechVisibleByZoom = false;
let latestResultPayload = null;
let latestSessionTitle = "";
let latestDiscussionTranscript = [];

function setNetworkCallPanelCollapsed(collapsed) {
  networkCallPanel?.classList.toggle("is-collapsed", collapsed);
  if (!networkCallToggle) return;
  networkCallToggle.textContent = collapsed ? "展开" : "收起";
  networkCallToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  networkCallToggle.setAttribute("aria-label", collapsed ? "展开 Agent Network 面板" : "折叠 Agent Network 面板");
}

function isKeyGatewayInvocation(item) {
  const status = String(item?.status || "").toLowerCase();
  const durationMs = Number(item?.durationMs || 0);
  return status === "failed" || status === "error" || Boolean(item?.fallbackFromCapabilityId) || durationMs >= 1200;
}

function formatGatewayStatus(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "ok") return "成功";
  if (normalized === "failed" || normalized === "error") return "失败";
  if (normalized === "calling") return "调用中";
  return normalized || "unknown";
}

function renderGatewayInvocations() {
  const recentItems = gatewayInvocationItems.slice(0, 16);
  const keyItems = recentItems.filter((item) => isKeyGatewayInvocation(item)).slice(0, 2);
  const items = keyItems.length ? keyItems : recentItems.slice(0, 2);
  if (!items.length) {
    networkCallFeed.innerHTML = `<div class="network-call-empty">暂无关键事件</div>`;
    return;
  }
  networkCallFeed.innerHTML = items
    .map((item) => {
      const normalizedStatus = String(item.status || "").toLowerCase();
      const statusClass = normalizedStatus === "failed" || normalizedStatus === "error" ? "is-failed" : "is-ok";
      const fallbackBadge = item.fallbackFromCapabilityId
        ? `<span class="network-call-badge">fallback</span>`
        : "";
      const capability = escapeHtml(item.capabilityId || "unknown-capability");
      const caller = escapeHtml(item.caller || "unknown");
      const target = escapeHtml(item.targetServiceId || "unresolved");
      const statusLabel = formatGatewayStatus(item.status);
      return `
        <article class="network-call-item ${statusClass}">
          <div class="network-call-capability">${capability}</div>
          <div class="network-call-route">${caller} → ${target}</div>
          <div class="network-call-foot">
            <span>${statusLabel} · ${Number(item.durationMs || 0)}ms</span>
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

function clearStreamRetryAction() {
  streamRetryAction = null;
  retryStreamBtn.classList.add("is-hidden");
  retryStreamBtn.textContent = "重试流连接";
}

function setStreamRetryAction(label, action) {
  streamRetryAction = typeof action === "function" ? action : null;
  retryStreamBtn.textContent = label || "重试流连接";
  retryStreamBtn.classList.toggle("is-hidden", !streamRetryAction);
}

function startGatewayTraceStream() {
  if (stopGatewayWatch) stopGatewayWatch();
  stopGatewayWatch = watchGatewayInvocations(
    (event) => {
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
    },
    {
      onDisconnect: () => {
        if (gatewayReconnectTimer) return;
        gatewayReconnectTimer = window.setTimeout(() => {
          gatewayReconnectTimer = null;
          startGatewayTraceStream();
        }, 2000);
      }
    }
  );
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

const STRICT_AVATAR_BY_AGENT_ID = {
  "agent-burton": "/mock/avatars/director-burton.png",
  "agent-columbus": "/mock/avatars/director-columbus.png",
  "agent-cuaron": "/mock/avatars/director-cuaron.png",
  "agent-curtis": "/mock/avatars/director-curtis.png",
  "agent-jackson": "/mock/avatars/director-jackson.png",
  "agent-newell": "/mock/avatars/director-newell.png",
  "agent-spielberg": "/mock/avatars/director-spielberg.png",
  "agent-yates": "/mock/avatars/director-yates.png",
  "agent-rowling": "/mock/avatars/guardian-rowling.png",
  "agent-tolkien": "/mock/avatars/guardian-tolkien.png"
};

async function resolveAvatarUrl(agent) {
  const strictAvatar = STRICT_AVATAR_BY_AGENT_ID[String(agent?.agentId || "")];
  if (strictAvatar) return strictAvatar;
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
  idleSpeechVisibleByZoom = false;
  latestDiscussionTranscript = [];
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
  networkHandle?.setIdleSpeechEnabled(false);
  queueText.textContent = "LIVE";
  clearStreamRetryAction();
  lastPhaseSection = "";
  ensureDiscussionSection("briefing");
  renderSystemLine("导演组就位，讨论系统启动。");
}

function closeLive() {
  sessionRunning = false;
  activeChatChannel = "idle";
  idleSpeechVisibleByZoom = false;
  liveOverlay.classList.remove("is-fading");
  liveOverlay.classList.add("is-hidden");
  queueText.textContent = "STANDBY";
  clearStreamRetryAction();
  networkHandle?.setIdleSpeechEnabled(false);
}

function hideResultOverlay() {
  resultOverlay.classList.add("is-hidden");
}

function clearResultOverlay() {
  hideResultOverlay();
  resultMedia.classList.add("is-hidden");
  resultMedia.innerHTML = "";
  resultNotesList.innerHTML = "";
  latestResultPayload = null;
}

function resetSessionUiToIdle() {
  if (unsubscribeJob) unsubscribeJob();
  clearStreamRetryAction();
  closeLive();
  toggleOverlayCollapsed(false);
  idleBanner.classList.remove("is-hidden");
  spotlightCard.classList.remove("is-hidden");
  hideAgentDetail();
  queueText.textContent = "STANDBY";
  activeAgentIds.clear();
  setRoleBuckets(createEmptyRoleBuckets());
  if (networkHandle) {
    networkHandle.setActiveAgents([]);
    networkHandle.setPhase("idle");
  }
  liveFeed.innerHTML = "";
  startIdleChatter();
}

function buildCrewNotes() {
  const participantIds = Array.from(currentRoleBuckets.participants || []).slice(0, 3);
  const picked = participantIds
    .map((id) => allAgents.find((agent) => agent.agentId === id))
    .filter(Boolean);
  if (picked.length) return picked;
  return allAgents.slice(0, 3);
}

function renderCrewNotes() {
  const notes = buildCrewNotes();
  if (!notes.length) {
    resultNotesList.innerHTML = `<div class="result-note-card"><div class="result-note-text">暂无导演组点评。</div></div>`;
    return;
  }
  resultNotesList.innerHTML = notes
    .map((agent) => {
      const display = getDisplayName(agent);
      const initial = escapeHtml((display.zh || display.en || "?").slice(0, 1));
      const noteText = escapeHtml(agent.stance || "本轮结局已生成，可继续迭代。");
      const avatarHtml = agent?.avatarUrl
        ? `<img class="result-note-avatar-image" src="${escapeHtml(agent.avatarUrl)}" alt="${escapeHtml(
            display.zh || display.en || "匿名成员"
          )}">`
        : `<span class="result-note-avatar-placeholder" aria-hidden="true">${initial}</span>`;
      return `
        <article class="result-note-card">
          <div class="result-note-avatar">${avatarHtml}</div>
          <div class="result-note-body">
            <div class="result-note-name">${escapeHtml(display.zh || display.en || "匿名成员")}</div>
            <p class="result-note-text">${noteText}</p>
          </div>
        </article>
      `;
    })
    .join("");
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

function setRoleBuckets(bucketSets) {
  currentRoleBuckets = bucketSets;
  if (!networkHandle) return;
  networkHandle.setRoleBuckets({
    participants: [...bucketSets.participants],
    lateJoiners: [],
    observers: [...bucketSets.observers],
    absent: [...bucketSets.absent]
  });
}

function ensureActiveFromBuckets() {
  activeAgentIds.clear();
  for (const id of currentRoleBuckets.participants) activeAgentIds.add(id);
}

function countStageAuthorsAndDirectors(bucketSets) {
  let total = 0;
  for (const id of bucketSets.participants) {
    const agent = allAgents.find((item) => item.agentId === id);
    if (agent?.type === "guardian" || agent?.type === "director") total += 1;
  }
  return total;
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
  if (
    sessionRunning ||
    activeChatChannel !== "idle" ||
    !idleSpeechVisibleByZoom ||
    !allAgents.length ||
    !networkHandle ||
    !idleDialogueEngine
  ) {
    return null;
  }
  const stylePreferenceInput = document.querySelector("#style-preference");
  const round = idleDialogueEngine.nextRound({
    stylePreference: String(stylePreferenceInput?.value || "auto"),
    tags: inferIdleTagsFromForm()
  });
  if (!round) return null;
  networkHandle.showAgentSpeech(round.speakerAId, round.lineA, { duration: IDLE_SPEECH_DURATION_MS });
  if (idleFollowupTimer) window.clearTimeout(idleFollowupTimer);
  const followupDelayMs = IDLE_SPEECH_DURATION_MS + IDLE_REPLY_GAP_MS;
  idleFollowupTimer = window.setTimeout(() => {
    if (sessionRunning || !networkHandle) return;
    networkHandle.showAgentSpeech(round.speakerBId, round.lineB, { duration: IDLE_SPEECH_DURATION_MS });
  }, followupDelayMs);
  reportIdleStats();
  return round.nextDelayMs;
}

function runIdleChatterCycle() {
  if (sessionRunning || activeChatChannel !== "idle" || !idleSpeechVisibleByZoom) return;
  const nextDelayMs = renderIdleDialogueTurn();
  const delay = Number.isFinite(nextDelayMs) ? nextDelayMs : 9000;
  idleChatterTimer = window.setTimeout(runIdleChatterCycle, delay);
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
  if (networkHandle) networkHandle.clearAllSpeech();
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

retryStreamBtn.addEventListener("click", async () => {
  if (!streamRetryAction) return;
  const action = streamRetryAction;
  clearStreamRetryAction();
  try {
    await action();
  } catch (error) {
    renderSystemLine(`重试失败：${error.message}`);
  }
});

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
    if (!hit) continue;
    if (!currentRoleBuckets.participants.has(hit.agentId)) {
      continue;
    }
    activeAgentIds.add(hit.agentId);
  }
  const ids = Array.from(activeAgentIds);
  const leadCandidateId = allAgents.find((agent) => agent.name === leadName)?.agentId || null;
  const leadId = leadCandidateId && currentRoleBuckets.participants.has(leadCandidateId) ? leadCandidateId : null;
  networkHandle.setActiveAgents(ids, leadId);
}

function isParticipantAgentId(agentId) {
  if (!agentId) return false;
  return currentRoleBuckets.participants.has(agentId);
}

function showResult(result) {
  latestResultPayload = result || null;
  resultTitle.textContent = "平行结局已完成";
  resultWorkName.textContent = latestSessionTitle || "意难平剧组";
  renderCrewNotes();

  const publicUrl = String(result?.publicUrl || "");
  const hasPlayableMp4 =
    publicUrl &&
    (result?.type === "video-mp4" ||
      result?.type === "video-mp4-fallback" ||
      publicUrl.toLowerCase().endsWith(".mp4"));
  if (hasPlayableMp4) {
    resultMedia.classList.remove("is-hidden");
    resultMedia.innerHTML = `
      <video controls preload="metadata" src="${escapeHtml(publicUrl)}"></video>
      <a href="${escapeHtml(publicUrl)}" target="_blank" rel="noreferrer">在新窗口打开视频</a>
    `;
  } else {
    resultMedia.classList.remove("is-hidden");
    resultMedia.innerHTML = `
      <div class="result-video-placeholder" role="status" aria-live="polite">
        <span>VIDEO PLAYER</span>
        <small>当前暂无可播放视频，请重新制作或稍后重试。</small>
      </div>
    `;
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
  networkCallMeta.textContent = `已发现 ${gatewayCapabilities.length} 个可调用能力 · 仅显示最近 2 条关键事件`;
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
      if (!zoneKey) {
        detailStage.textContent = activeAgentIds.size ? "当前状态：参与本轮任务" : "当前状态：空闲";
        updateIdleSpeechByZoom(null, zoomScale);
        return;
      }
      detailStage.textContent = `当前视角：${zoneKey.toUpperCase()} (${zoomScale.toFixed(2)}x)`;
      updateIdleSpeechByZoom(zoneKey, zoomScale);
    }
  });
  networkHandle.setIdleSpeechEnabled(false);
  startSpotlight();
  setRoleBuckets(createEmptyRoleBuckets());
}

inputOverlay.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(inputOverlay);

  const candidate = {
    workTitle: String(formData.get("workTitle") || "").trim(),
    endingDirection: String(formData.get("endingDirection") || "").trim(),
    stylePreference: String(formData.get("stylePreference") || "auto")
  };
  const rawSourceVideoFile = formData.get("sourceVideoFile");
  const sourceVideoFile =
    rawSourceVideoFile instanceof File && rawSourceVideoFile.size > 0 ? rawSourceVideoFile : null;

  let payload;
  try {
    payload = parseCreativeSession(candidate);
  } catch (error) {
    alert(`输入校验失败：${error.message}`);
    return;
  }

  toggleOverlayCollapsed(true);
  latestSessionTitle = payload.workTitle || "未命名作品";
  spotlightCard.classList.add("is-hidden");
  setRoleBuckets(pickRoleBuckets(allAgents, payload));
  ensureActiveFromBuckets();
  networkHandle.gather();
  networkHandle.setPhase("forming");
  networkHandle.setActiveAgents([...activeAgentIds]);
  openLive(payload.workTitle);
  markTimelinePhase("collect");
  renderSystemLine("会话创建中…");
  renderSystemLine(`主舞台核心成员 ${countStageAuthorsAndDirectors(currentRoleBuckets)} 位。`);

  try {
    const { session } = await createSession(payload);
    renderSystemLine(`会话已创建：${session.sessionId}`);
    renderSystemLine("导演与原著守门人讨论中…");
    networkHandle.pulseZone("mainStage");
    networkHandle.setPhase("discuss");
    markTimelinePhase("discuss");

    try {
      await streamDiscussion(session.sessionId, (turn) => {
        if (!sessionRunning || activeChatChannel !== "live") return;
        if (turn.event === "turn") {
          const speakerAgent = allAgents.find((agent) => agent.name === turn.speaker);
          const speakerAgentId = speakerAgent?.agentId || "";
          const speakerInParticipants = isParticipantAgentId(speakerAgentId);
          if (!speakerInParticipants) {
            return;
          }
          ensureDiscussionSection(turn.stage);
          renderMessageLine(turn.speaker, turn.content);
          latestDiscussionTranscript.push(`${resolveSpeakerDisplayName(turn.speaker)}：${turn.content}`);
          updateActiveAgentsFromNames([turn.speaker], turn.speaker);
          if (speakerAgent) networkHandle.showAgentSpeech(speakerAgent.agentId, turn.content, { duration: 3600, force: true });
        } else if (turn.event === "topic") {
          ensureDiscussionSection(turn.stage);
          renderSystemLine(`${turn.title}｜${turn.goal}`);
          latestDiscussionTranscript.push(`系统｜${turn.title}：${turn.goal}`);
        } else if (turn.event === "system") {
          ensureDiscussionSection(turn.stage);
          renderSystemLine(turn.content);
          latestDiscussionTranscript.push(`系统：${turn.content}`);
        } else if (turn.event === "summary") {
          ensureDiscussionSection(turn.stage);
          renderSummaryLine(turn.content);
          latestDiscussionTranscript.push(`总结：${turn.content}`);
        } else if (turn.event === "done") {
          renderSummaryLine("讨论结论已达成，剧组进入制作管线。");
          latestDiscussionTranscript.push("系统：讨论结论已达成，剧组进入制作管线。");
          renderSectionLine("pipeline");
        }
      });
    } catch (discussionError) {
      setStreamRetryAction("重试讨论流（重新开机）", async () => {
        inputOverlay.requestSubmit();
      });
      throw new Error(`讨论流中断：${discussionError.message}`);
    }

    let sourceVideoRef = "";
    if (sourceVideoFile) {
      renderSystemLine(`素材上传中：${sourceVideoFile.name}`);
      const { upload } = await uploadVideoSource(sourceVideoFile);
      renderSystemLine(`素材上传完成：${upload.originalName}`);
      sourceVideoRef = { uploadId: upload.uploadId };
    }
    const { job } = await createVideoJob(session.sessionId, sourceVideoRef);
    renderSystemLine(`视频任务已创建：${job.jobId}`);
    networkHandle.setPhase("collect");
    markTimelinePhase("collect");

    const attachVideoStream = () => {
      if (unsubscribeJob) unsubscribeJob();
      unsubscribeJob = watchVideoJob(
        job.jobId,
        (evt) => {
          if (evt.event === "progress") {
            const phase = mapPhaseByProgressText(`${evt.phase}: ${evt.message}`);
            if (lastPhaseSection !== phase) {
              renderSectionLine(phaseLabel(phase));
              lastPhaseSection = phase;
            }
            renderSystemLine(`${evt.phase}: ${evt.message}`);
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
            liveOverlay.classList.add("is-fading");
            setTimeout(() => {
              closeLive();
              spotlightCard.classList.remove("is-hidden");
              showResult(evt.result);
            }, 1400);
            return;
          }
          if (evt.event === "error") {
            renderSystemLine(evt.message || "任务事件流中断。");
            setStreamRetryAction("重连任务流", async () => {
              renderSystemLine("正在重连任务流…");
              attachVideoStream();
            });
          }
        },
        {
          onDisconnect: () => {
            setStreamRetryAction("重连任务流", async () => {
              renderSystemLine("正在重连任务流…");
              attachVideoStream();
            });
          }
        }
      );
    };
    attachVideoStream();
  } catch (error) {
    renderSystemLine(`任务失败：${error.message}`);
    networkHandle.release();
    resetSessionUiToIdle();
    queueText.textContent = "ERROR";
  }
});

restartBtn.addEventListener("click", () => {
  clearResultOverlay();
  resetSessionUiToIdle();
});

resultCloseBtn.addEventListener("click", () => {
  hideResultOverlay();
});

downloadShareBtn.addEventListener("click", async () => {
  const publicUrl = String(latestResultPayload?.publicUrl || "");
  if (!publicUrl) {
    alert("当前暂无可下载或分享的视频链接。");
    return;
  }
  const safeUrl = publicUrl.trim();
  const anchor = document.createElement("a");
  anchor.href = safeUrl;
  anchor.download = `${latestSessionTitle || "parallel-ending"}.mp4`;
  anchor.target = "_blank";
  anchor.rel = "noreferrer";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);

  let copied = false;
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(safeUrl);
      copied = true;
    } catch {
      copied = false;
    }
  }
  if (copied) renderSystemLine("视频链接已复制到剪贴板，可直接分享。");
});

resultOverlay.addEventListener("click", (event) => {
  if (event.target === resultOverlay) hideResultOverlay();
});

window.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (resultOverlay.classList.contains("is-hidden")) return;
  hideResultOverlay();
});

detailClose.addEventListener("click", hideAgentDetail);
overlayToggleBtn.addEventListener("click", () => toggleOverlayCollapsed());
zoomDirectorsBtn.addEventListener("click", () => networkHandle?.zoomToZone("directors"));
zoomResetBtn.addEventListener("click", () => networkHandle?.resetCamera());
networkCallToggle?.addEventListener("click", () => {
  const collapsed = networkCallPanel?.classList.contains("is-collapsed");
  setNetworkCallPanelCollapsed(!collapsed);
});
loadDemoBtn.addEventListener("click", () => {
  const workTitleInput = document.querySelector("#work-title");
  const endingDirectionInput = document.querySelector("#ending-direction");
  const stylePreferenceInput = document.querySelector("#style-preference");
  workTitleInput.value = "哈利波特与凤凰社";
  endingDirectionInput.value = "小天狼星在神秘事务司被救下，最终和哈利拥抱和解。";
  stylePreferenceInput.value = "warmHealing";
  sourceVideoFileInput.value = "";
});

bootstrap();
