export const guardians = [
  {
    agentId: "agent-rowling",
    name: "J.K.罗琳",
    role: "guardian",
    stance: "遵循原著精神，允许HE但必须保留代价。"
  },
  {
    agentId: "agent-tolkien",
    name: "J.R.R.托尔金",
    role: "guardian",
    stance: "救赎可以成立，但不应抹去牺牲意义。"
  }
];

export const directors = [
  {
    agentId: "agent-curtis",
    name: "理查德·柯蒂斯",
    role: "director",
    stance: "观众值得获得拥抱式结局。"
  },
  {
    agentId: "agent-yates",
    name: "David Yates",
    role: "director",
    stance: "黑暗框架中也要有戏剧代价。"
  },
  {
    agentId: "agent-cuaron",
    name: "Alfonso Cuaron",
    role: "director",
    stance: "以克制视听承载情绪。"
  }
];

export function pickPanel(stylePreference) {
  if (stylePreference === "darkEpic") {
    return [guardians[0], directors[1], directors[2]];
  }
  if (stylePreference === "warmHealing") {
    return [guardians[1], directors[0], directors[2]];
  }
  return [guardians[0], guardians[1], directors[0], directors[1]];
}
