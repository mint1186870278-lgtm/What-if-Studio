const NAME_MAP = {
  "agent-rowling": { zh: "J.K.罗琳", en: "J.K. Rowling" },
  "agent-tolkien": { zh: "J.R.R.托尔金", en: "J.R.R. Tolkien" },
  "agent-columbus": { zh: "克里斯·哥伦布", en: "Chris Columbus" },
  "agent-cuaron": { zh: "阿方索·卡隆", en: "Alfonso Cuaron" },
  "agent-newell": { zh: "迈克·纽维尔", en: "Mike Newell" },
  "agent-yates": { zh: "大卫·叶茨", en: "David Yates" },
  "agent-jackson": { zh: "彼得·杰克逊", en: "Peter Jackson" },
  "agent-burton": { zh: "蒂姆·伯顿", en: "Tim Burton" },
  "agent-spielberg": { zh: "史蒂文·斯皮尔伯格", en: "Steven Spielberg" },
  "agent-curtis": { zh: "理查德·柯蒂斯", en: "Richard Curtis" },
  "agent-editor": { zh: "剪辑师", en: "Editor" },
  "agent-composer": { zh: "配乐师", en: "Composer" },
  "agent-collector": { zh: "素材侦探", en: "Asset Collector" }
};

export function getDisplayName(agent) {
  const preset = NAME_MAP[agent.agentId];
  if (preset) return preset;
  return {
    zh: agent.name || "",
    en: agent.name || ""
  };
}

