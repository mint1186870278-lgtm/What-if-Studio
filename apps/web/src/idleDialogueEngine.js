const EXECUTION_GUARD_WORDS = [
  "进入制作",
  "制作阶段",
  "镜头清单",
  "任务",
  "导出",
  "流程",
  "调度",
  "管线",
  "粗剪",
  "渲染"
];

const DEFAULT_NEXT_DELAY_RANGE = [11000, 18000];
const DEFAULT_REPLY_DELAY_RANGE = [2800, 4500];

function randomInt(min, max) {
  const start = Math.ceil(min);
  const end = Math.floor(max);
  return Math.floor(Math.random() * (end - start + 1)) + start;
}

function removeOld(history, maxSize) {
  while (history.length > maxSize) history.shift();
}

function pickRandom(items) {
  if (!items.length) return null;
  return items[Math.floor(Math.random() * items.length)];
}

function normalizeStyle(stylePreference) {
  const style = String(stylePreference || "auto");
  if (style === "darkEpic") return "darkEpic";
  if (style === "warmHealing") return "warmHealing";
  if (style === "realism") return "realism";
  if (style === "fantasyGrand") return "fantasyGrand";
  return "auto";
}

function containsExecutionWords(text) {
  const source = String(text || "");
  return EXECUTION_GUARD_WORDS.some((word) => source.includes(word));
}

function isSafeDialogue(entry) {
  if (!entry || !entry.lineA || !entry.lineB) return false;
  return !containsExecutionWords(entry.lineA) && !containsExecutionWords(entry.lineB);
}

function buildPairPool(agents) {
  const directors = (agents || []).filter((agent) => agent.type !== "crew");
  const pairs = [];
  for (let i = 0; i < directors.length; i += 1) {
    for (let j = 0; j < directors.length; j += 1) {
      if (i === j) continue;
      pairs.push([directors[i], directors[j]]);
    }
  }
  return pairs;
}

function hashText(text) {
  let value = 0;
  const source = String(text || "");
  for (let i = 0; i < source.length; i += 1) {
    value = (value * 31 + source.charCodeAt(i)) >>> 0;
  }
  return value;
}

function scoreDialogue(entry, tags, stylePreference) {
  let score = 1;
  const tones = Array.isArray(entry.tones) ? entry.tones : [];
  const entryTags = new Set(Array.isArray(entry.tags) ? entry.tags : []);
  const style = normalizeStyle(stylePreference);
  if (tones.includes(style)) score += 2;
  if (tones.includes("auto")) score += 1;
  for (const tag of tags) {
    if (entryTags.has(tag)) score += 1;
  }
  return score;
}

export function createIdleDialogueEngine(options) {
  const agents = Array.isArray(options?.agents) ? options.agents : [];
  const libraryRaw = Array.isArray(options?.dialogues) ? options.dialogues : [];
  const pairPool = buildPairPool(agents);
  const dialoguePool = libraryRaw.filter(isSafeDialogue);

  const recentPairs = [];
  const recentDialogueIds = [];
  const recentSignatures = [];
  const pairCooldown = Number(options?.pairCooldown || 8);
  const dialogueCooldown = Number(options?.dialogueCooldown || 14);
  const signatureCooldown = Number(options?.signatureCooldown || 18);

  let rounds = 0;
  let guardedDropCount = Math.max(0, libraryRaw.length - dialoguePool.length);
  let duplicateAvoidedCount = 0;
  let fallbackCount = 0;

  function pickPair() {
    if (!pairPool.length) return null;
    const candidates = pairPool.filter(([first, second]) => {
      const key = `${first.agentId}>${second.agentId}`;
      return !recentPairs.includes(key);
    });
    if (candidates.length) {
      const picked = pickRandom(candidates);
      if (candidates.length !== pairPool.length) duplicateAvoidedCount += 1;
      return picked;
    }
    fallbackCount += 1;
    return pickRandom(pairPool);
  }

  function pickDialogue(context) {
    if (!dialoguePool.length) return null;
    const stylePreference = normalizeStyle(context?.stylePreference);
    const tags = new Set(Array.isArray(context?.tags) ? context.tags : []);
    const stageOne = dialoguePool.filter((entry) => {
      const id = String(entry.id || "");
      return !recentDialogueIds.includes(id);
    });
    const stageTwo = (stageOne.length ? stageOne : dialoguePool).filter((entry) => {
      const tones = Array.isArray(entry.tones) ? entry.tones : [];
      return tones.includes("auto") || tones.includes(stylePreference);
    });
    const usable = stageTwo.length ? stageTwo : (stageOne.length ? stageOne : dialoguePool);
    const scored = usable
      .map((entry) => ({ entry, score: scoreDialogue(entry, tags, stylePreference) }))
      .sort((a, b) => b.score - a.score);
    const bestScore = scored[0]?.score || 0;
    const topCandidates = scored.filter((item) => item.score >= bestScore - 1).map((item) => item.entry);
    return pickRandom(topCandidates) || null;
  }

  function nextRound(context) {
    const pair = pickPair();
    const dialogue = pickDialogue(context);
    if (!pair || !dialogue) return null;
    const [speakerA, speakerB] = pair;
    const dialogueId = String(dialogue.id || "");
    const signature = `${speakerA.agentId}>${speakerB.agentId}#${dialogueId || hashText(`${dialogue.lineA}${dialogue.lineB}`)}`;

    if (recentSignatures.includes(signature)) {
      duplicateAvoidedCount += 1;
      fallbackCount += 1;
    }

    recentPairs.push(`${speakerA.agentId}>${speakerB.agentId}`);
    recentDialogueIds.push(dialogueId);
    recentSignatures.push(signature);
    removeOld(recentPairs, pairCooldown);
    removeOld(recentDialogueIds, dialogueCooldown);
    removeOld(recentSignatures, signatureCooldown);
    rounds += 1;

    return {
      speakerAId: speakerA.agentId,
      speakerBId: speakerB.agentId,
      lineA: String(dialogue.lineA || ""),
      lineB: String(dialogue.lineB || ""),
      replyDelayMs: randomInt(DEFAULT_REPLY_DELAY_RANGE[0], DEFAULT_REPLY_DELAY_RANGE[1]),
      nextDelayMs: randomInt(DEFAULT_NEXT_DELAY_RANGE[0], DEFAULT_NEXT_DELAY_RANGE[1]),
      dialogueId
    };
  }

  function getStats() {
    const uniqueRecent = new Set(recentSignatures).size;
    const repetitionRate = rounds <= 1 ? 0 : Number(((rounds - uniqueRecent) / rounds).toFixed(3));
    return {
      rounds,
      uniqueRecent,
      repetitionRate,
      duplicateAvoidedCount,
      fallbackCount,
      guardedDropCount
    };
  }

  return {
    nextRound,
    getStats
  };
}
