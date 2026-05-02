export function createEmptyRoleBuckets() {
  return {
    participants: new Set(),
    lateJoiners: new Set(),
    observers: new Set(),
    absent: new Set()
  };
}

export function inferTagsFromSession(payload) {
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

export function pickRoleBuckets(agents, payload) {
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
    if (!mapped) continue;
    for (const agentId of mapped) mandatoryJoiners.add(agentId);
  }

  function resolveInterestScore(agent) {
    const agentTags = new Set(agent.interestTags || []);
    let score = 0;
    for (const tag of tags) {
      if (agentTags.has(tag)) score += 0.42;
    }
    if (agent.type === "guardian" && tags.has("adaptation")) score += 0.42;
    if (agent.type === "director" && tags.has("romance") && agentTags.has("romance")) score += 0.2;
    if (agent.type === "director" && tags.has("epic") && agentTags.has("epic")) score += 0.2;
    score += Math.random() * 0.16;
    return Math.min(1, score);
  }

  for (const agent of agents) {
    const isCrew = agent.type === "crew";
    const isDirectorOrGuardian = agent.type === "guardian" || agent.type === "director";

    if (isCrew) {
      participants.add(agent.agentId);
      continue;
    }

    if (!isDirectorOrGuardian) {
      absent.add(agent.agentId);
      continue;
    }

    const mustJoin = mandatoryJoiners.has(agent.agentId);
    const interestScore = resolveInterestScore(agent);

    if (mustJoin || interestScore >= 0.72) {
      participants.add(agent.agentId);
      continue;
    }

    if (interestScore >= 0.45) {
      observers.add(agent.agentId);
      continue;
    }

    if (interestScore >= 0.2) {
      observers.add(agent.agentId);
      continue;
    }

    absent.add(agent.agentId);
  }

  // Keep randomness, but guarantee a minimum visible cast
  // (director/guardian) will move toward main stage on startup.
  const minStageCast = 4;
  const minImmediateStageCast = 3;
  const stagedCount = [...participants].filter((agentId) => {
    const agent = agents.find((item) => item.agentId === agentId);
    return agent?.type === "director" || agent?.type === "guardian";
  }).length;
  const shortfall = Math.max(0, minStageCast - stagedCount);
  if (shortfall > 0) {
    const candidatePool = agents.filter(
      (agent) =>
        (agent.type === "director" || agent.type === "guardian") &&
        !participants.has(agent.agentId)
    );
    const shuffled = [...candidatePool].sort(() => Math.random() - 0.5);
    const picks = shuffled.slice(0, shortfall);
    for (const agent of picks) {
      observers.delete(agent.agentId);
      absent.delete(agent.agentId);
      participants.add(agent.agentId);
    }
  }

  // Ensure at least 3 director/guardian are immediately active (participants),
  // otherwise users will see links but no one moving to main stage.
  const immediateStageCount = [...participants].filter((agentId) => {
    const agent = agents.find((item) => item.agentId === agentId);
    return agent?.type === "director" || agent?.type === "guardian";
  }).length;
  const immediateShortfall = Math.max(0, minImmediateStageCast - immediateStageCount);
  if (immediateShortfall > 0) {
    const reserveCandidates = agents.filter(
      (agent) =>
        (agent.type === "director" || agent.type === "guardian") &&
        !participants.has(agent.agentId)
    );
    const shuffledCandidates = [...reserveCandidates].sort(() => Math.random() - 0.5);
    for (const agent of shuffledCandidates.slice(0, immediateShortfall)) {
      observers.delete(agent.agentId);
      absent.delete(agent.agentId);
      participants.add(agent.agentId);
    }
  }

  return { participants, lateJoiners: new Set(), observers, absent };
}
