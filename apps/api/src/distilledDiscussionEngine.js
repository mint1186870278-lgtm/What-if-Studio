import { createDiscussionTurn } from "@yinanping/contracts";
import { pickPanel } from "@yinanping/agent-profiles";

function inferTone(stylePreference) {
  if (stylePreference === "darkEpic") return "高压冲突+代价守恒";
  if (stylePreference === "warmHealing") return "先痛后暖+关系修复";
  if (stylePreference === "realism") return "克制现实+因果闭环";
  if (stylePreference === "fantasyGrand") return "奇观场面+情绪锚点";
  return "风格平衡+执行优先";
}

function buildAgenda(session) {
  return [
    {
      id: "canon",
      stage: "topic-1",
      title: "议题一：设定与角色底线",
      goal: `明确《${session.workTitle}》改写边界，确保角色行为自洽。`
    },
    {
      id: "emotion",
      stage: "topic-2",
      title: "议题二：情绪与代价",
      goal: `围绕“${session.endingDirection}”设计代价-释放曲线。`
    },
    {
      id: "execution",
      stage: "topic-3",
      title: "议题三：拍摄与交付",
      goal: "产出可执行的镜头与剪辑计划，直接对接制作链路。"
    }
  ];
}

function buildPersonaDrivenLine(session, topic, speaker, idx) {
  const stance = speaker.stance || "先保证叙事可信度";
  if (topic.id === "canon") {
    return idx % 2 === 0
      ? `${stance}。我建议把核心冲突保留在主线，不做无因果逆转。`
      : `我补充一点：让角色的选择成本可见，这样《${session.workTitle}》改写仍成立。`;
  }
  if (topic.id === "emotion") {
    return idx % 2 === 0
      ? `围绕“${session.endingDirection}”，先压抑再释放，观众才会买账。`
      : "情绪节点建议落在三拍：失去、决断、修复，避免直给式HE。";
  }
  return idx % 2 === 0
    ? "执行建议：每段保留一个情绪停顿镜头，并明确前后场景连接。"
    : "交付建议：剪辑按压抑-转折-拥抱节奏，配乐在末段抬升并留2秒余韵。";
}

function buildTopicSummary(topic) {
  if (topic.id === "canon") return "蒸馏结论：保持设定边界，角色动机不可跳步。";
  if (topic.id === "emotion") return "蒸馏结论：先展示代价，再兑现和解。";
  return "蒸馏结论：镜头、剪辑、配乐计划均可直接排产。";
}

export function generateDistilledDiscussionTimeline(session) {
  const panel = pickPanel(session.stylePreference);
  if (!panel.length) throw new Error("panel is empty");
  const agenda = buildAgenda(session);
  const lead = panel.find((member) => member.role === "guardian") || panel[0];
  const timeline = [];

  timeline.push({
    event: "system",
    stage: "briefing",
    content: `蒸馏讨论已启动，参会 ${panel.length} 人，策略：${inferTone(session.stylePreference)}。`
  });
  timeline.push({
    event: "system",
    stage: "briefing",
    content: `主持人 ${lead.name} 宣布目标：以可交付短片为终点，讨论必须输出执行项。`
  });

  for (const topic of agenda) {
    timeline.push({
      event: "topic",
      stage: topic.stage,
      title: topic.title,
      goal: topic.goal
    });
    panel.forEach((speaker, idx) => {
      timeline.push({
        event: "turn",
        ...createDiscussionTurn({
          speaker: speaker.name,
          role: speaker.role,
          stage: topic.stage,
          content: buildPersonaDrivenLine(session, topic, speaker, idx)
        })
      });
    });
    timeline.push({
      event: "summary",
      stage: topic.stage,
      content: buildTopicSummary(topic)
    });
  }

  timeline.push({
    event: "turn",
    ...createDiscussionTurn({
      speaker: lead.name,
      role: lead.role,
      stage: "finalize",
      content: `最终拍板：围绕“${session.endingDirection}”执行短片方案，允许HE但必须保留代价线索。`
    })
  });
  timeline.push({
    event: "system",
    stage: "finalize",
    content: "蒸馏讨论闭环完成：议题覆盖、执行项确认、可进入制作管线。"
  });

  return timeline;
}
