import { directors, guardians } from "@yinanping/agent-profiles";

const profileMap = new Map([...guardians, ...directors].map((item) => [item.agentId, item]));

function withProfile(agent) {
  const profile = profileMap.get(agent.agentId);
  return {
    ...agent,
    name: profile?.name || agent.name,
    stance: profile?.stance || agent.stance
  };
}

const roster = [
  {
    agentId: "agent-rowling",
    name: "J.K.罗琳",
    type: "guardian",
    stance: "HE可以有，但必须保留代价。",
    avatarUrl: "/mock/avatars/guardian-rowling.png",
    home: { x: 0.75, y: 0.2 },
    homeZone: "directors",
    interestTags: ["fantasy", "adaptation", "drama"],
    scatterPreference: "directors",
    lateJoinProbability: 0.25
  },
  {
    agentId: "agent-tolkien",
    name: "J.R.R.托尔金",
    type: "guardian",
    stance: "救赎成立，但不可抹去失去。",
    avatarUrl: "/mock/avatars/guardian-tolkien.png",
    home: { x: 0.8, y: 0.25 },
    homeZone: "directors",
    interestTags: ["epic", "fantasy", "adaptation"],
    scatterPreference: "directors",
    lateJoinProbability: 0.28
  },
  {
    agentId: "agent-columbus",
    name: "Chris Columbus",
    type: "director",
    stance: "让观众看到希望和团圆。",
    avatarUrl: "/mock/avatars/director-columbus.png",
    home: { x: 0.7, y: 0.28 },
    homeZone: "directors",
    interestTags: ["romance", "fantasy", "family"],
    scatterPreference: "directors",
    lateJoinProbability: 0.12
  },
  {
    agentId: "agent-cuaron",
    name: "Alfonso Cuaron",
    type: "director",
    stance: "克制镜头，情绪留给观众。",
    avatarUrl: "/mock/avatars/director-cuaron.png",
    home: { x: 0.78, y: 0.3 },
    homeZone: "directors",
    interestTags: ["drama", "realism", "adaptation"],
    scatterPreference: "edit",
    lateJoinProbability: 0.34
  },
  {
    agentId: "agent-newell",
    name: "Mike Newell",
    type: "director",
    stance: "关系修复要有冒险过程。",
    avatarUrl: "/mock/avatars/director-newell.png",
    home: { x: 0.72, y: 0.33 },
    homeZone: "directors",
    interestTags: ["drama", "epic"],
    scatterPreference: "mainStage",
    lateJoinProbability: 0.3
  },
  {
    agentId: "agent-yates",
    name: "David Yates",
    type: "director",
    stance: "黑暗叙事中挤出一线生机。",
    avatarUrl: "/mock/avatars/director-yates.png",
    home: { x: 0.82, y: 0.22 },
    homeZone: "directors",
    interestTags: ["dark", "epic", "fantasy"],
    scatterPreference: "mainStage",
    lateJoinProbability: 0.22
  },
  {
    agentId: "agent-jackson",
    name: "彼得·杰克逊",
    type: "director",
    stance: "营救必须有史诗规模。",
    avatarUrl: "/mock/avatars/director-jackson.png",
    home: { x: 0.76, y: 0.35 },
    homeZone: "directors",
    interestTags: ["epic", "fantasy"],
    scatterPreference: "sound",
    lateJoinProbability: 0.15
  },
  {
    agentId: "agent-burton",
    name: "蒂姆·伯顿",
    type: "director",
    stance: "生死边界可以被魔法扭转。",
    avatarUrl: "/mock/avatars/director-burton.png",
    home: { x: 0.68, y: 0.32 },
    homeZone: "directors",
    interestTags: ["fantasy", "dark"],
    scatterPreference: "mainStage",
    lateJoinProbability: 0.27
  },
  {
    agentId: "agent-spielberg",
    name: "斯皮尔伯格",
    type: "director",
    stance: "让亲情成为结局锚点。",
    avatarUrl: "/mock/avatars/director-spielberg.png",
    home: { x: 0.74, y: 0.38 },
    homeZone: "directors",
    interestTags: ["romance", "drama", "family"],
    scatterPreference: "directors",
    lateJoinProbability: 0.2
  },
  {
    agentId: "agent-curtis",
    name: "理查德·柯蒂斯",
    type: "director",
    stance: "观众值得一个拥抱式HE。",
    avatarUrl: "/mock/avatars/director-curtis.png",
    home: { x: 0.8, y: 0.38 },
    homeZone: "directors",
    interestTags: ["romance", "healing"],
    scatterPreference: "directors",
    lateJoinProbability: 0.1
  },
  {
    agentId: "agent-editor",
    name: "剪辑师",
    type: "crew",
    stance: "控制节奏和情绪峰值。",
    avatarUrl: "/mock/avatars/editor.svg",
    home: { x: 0.2, y: 0.75 },
    homeZone: "edit",
    interestTags: ["drama", "epic", "adaptation"],
    scatterPreference: "edit",
    lateJoinProbability: 0
  },
  {
    agentId: "agent-composer",
    name: "配乐师",
    type: "crew",
    stance: "用BGM锁定泪点。",
    avatarUrl: "/mock/avatars/composer.svg",
    home: { x: 0.78, y: 0.75 },
    homeZone: "sound",
    interestTags: ["epic", "romance", "fantasy"],
    scatterPreference: "sound",
    lateJoinProbability: 0
  },
  {
    agentId: "agent-collector",
    name: "素材侦探",
    type: "crew",
    stance: "优先补齐关键叙事镜头。",
    avatarUrl: "/mock/avatars/collector.svg",
    home: { x: 0.18, y: 0.25 },
    homeZone: "archive",
    interestTags: ["adaptation", "drama"],
    scatterPreference: "archive",
    lateJoinProbability: 0
  }
];

export function getAgents() {
  return roster.map(withProfile);
}
