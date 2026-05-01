import { createDiscussionTurn } from "@yinanping/contracts";
import { pickPanel } from "@yinanping/agent-profiles";
import { generateDistilledDiscussionTimeline } from "./distilledDiscussionEngine.js";

function inferToneLabel(stylePreference) {
  if (stylePreference === "darkEpic") return "黑暗史诗";
  if (stylePreference === "warmHealing") return "温情治愈";
  if (stylePreference === "realism") return "文艺写实";
  if (stylePreference === "fantasyGrand") return "奇幻宏大";
  return "自动平衡";
}

function buildAgenda(session) {
  return [
    {
      id: "canon",
      title: "议题一：原著底线",
      goal: "明确哪些设定必须保留，避免改写成平行同人感。"
    },
    {
      id: "emotion",
      title: "议题二：情绪曲线",
      goal: `围绕“${session.endingDirection}”建立可共情的代价与释放。`
    },
    {
      id: "execution",
      title: "议题三：镜头执行",
      goal: "把共识落地成可拍、可剪、可交付的执行方案。"
    }
  ];
}

function rotatePanel(panel, offset) {
  if (!panel.length) return [];
  const normalized = offset % panel.length;
  return [...panel.slice(normalized), ...panel.slice(0, normalized)];
}

function buildTurnContent(session, topic, speaker, turnIndex) {
  const title = session.workTitle;
  const stance = speaker.stance || "先保证叙事可信度";
  if (topic.id === "canon") {
    if (turnIndex % 2 === 0) {
      return `我先定边界：${stance}。对于《${title}》，这条不能被“强行圆满”覆盖。`;
    }
    return `我认同保留边界，但建议把冲突写成“选择的代价”，这样改动仍然像《${title}》。`;
  }

  if (topic.id === "emotion") {
    if (turnIndex % 2 === 0) {
      return `情绪上别直接给糖，先让角色承担后果，再把“${session.endingDirection}”作为释放点。`;
    }
    return `可以，我补一层：让观众先看到失去感，再给修复动作，HE才不会显得突兀。`;
  }

  if (turnIndex % 2 === 0) {
    return "执行上我建议先出镜头清单：主冲突镜头、情绪停顿镜头、关系修复镜头三段式推进。";
  }
  return "剪辑节奏按“压抑-转折-拥抱”三拍走，音乐在最后一拍抬升，确保落地可交付。";
}

function buildTopicSummary(topic) {
  if (topic.id === "canon") return "阶段结论：保留世界观和人物代价，不做无因果逆转。";
  if (topic.id === "emotion") return "阶段结论：先痛后暖，HE建立在真实付出上。";
  return "阶段结论：采用三段式镜头与三拍节奏，直接进入制作管线。";
}

export function generateTemplateDiscussionTimeline(session) {
  const panel = pickPanel(session.stylePreference);
  const agenda = buildAgenda(session);
  const tone = inferToneLabel(session.stylePreference);
  const moderator = panel.find((member) => member.role === "guardian") || panel[0];
  const timeline = [];

  timeline.push({
    event: "system",
    stage: "briefing",
    content: `导演室已连线，共 ${panel.length} 位成员参会，风格偏好：${tone}。`
  });
  timeline.push({
    event: "system",
    stage: "briefing",
    content: `主持人 ${moderator.name} 宣布会议目标：保留原著精神，完成可执行的平行结局方案。`
  });

  for (let topicIndex = 0; topicIndex < agenda.length; topicIndex += 1) {
    const topic = agenda[topicIndex];
    const stage = `topic-${topicIndex + 1}`;
    const roundPanel = rotatePanel(panel, topicIndex);

    timeline.push({
      event: "topic",
      stage,
      title: topic.title,
      goal: topic.goal
    });

    roundPanel.forEach((speaker, idx) => {
      timeline.push({
        event: "turn",
        ...createDiscussionTurn({
          speaker: speaker.name,
          role: speaker.role,
          stage,
          content: buildTurnContent(session, topic, speaker, idx)
        })
      });
    });

    timeline.push({
      event: "summary",
      stage,
      content: buildTopicSummary(topic)
    });
  }

  timeline.push({
    event: "turn",
    ...createDiscussionTurn({
      speaker: moderator.name,
      role: moderator.role,
      stage: "finalize",
      content: `最终决议：围绕“${session.endingDirection}”执行 HE 版本，保留因果与牺牲，批准进入制作阶段。`
    })
  });
  timeline.push({
    event: "system",
    stage: "finalize",
    content: "会议闭环完成：议题、争论、结论、执行项均已归档。"
  });

  return timeline;
}

export function resolveDiscussionMode() {
  const mode = String(process.env.DISCUSSION_ENGINE_MODE || "template").trim().toLowerCase();
  if (mode === "distilled") return "distilled";
  return "template";
}

export function generateDiscussionTimeline(session) {
  const mode = resolveDiscussionMode();
  if (mode === "distilled") {
    try {
      return generateDistilledDiscussionTimeline(session);
    } catch (error) {
      const fallback = generateTemplateDiscussionTimeline(session);
      fallback.unshift({
        event: "system",
        stage: "briefing",
        content: `蒸馏模型不可用，自动回退模板引擎：${error.message}`
      });
      return fallback;
    }
  }
  return generateTemplateDiscussionTimeline(session);
}
