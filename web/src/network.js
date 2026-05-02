import * as d3 from "d3";
import { getDisplayName } from "./displayNames";

function nodeColor(type) {
  if (type === "guardian") return "#c9a84c";
  if (type === "crew") return "#8e8e8e";
  return "#ffffff";
}

function safeNodeId(text) {
  return String(text || "node").replace(/[^a-zA-Z0-9_-]/g, "_");
}

function compactSpeech(text) {
  const trimmed = String(text || "").replace(/\s+/g, " ").trim();
  if (!trimmed) return "";
  if (trimmed.length <= 100) return trimmed;
  return trimmed.slice(-100);
}

function splitSpeechLines(text, maxLineChars = 24, maxLines = 4) {
  const raw = compactSpeech(text);
  if (!raw) return [""];
  const lines = [];
  for (let i = 0; i < raw.length; i += maxLineChars) {
    lines.push(raw.slice(i, i + maxLineChars));
    if (lines.length >= maxLines) break;
  }
  if (raw.length > maxLineChars * maxLines) {
    const last = lines[lines.length - 1];
    lines[lines.length - 1] = `${last.slice(0, Math.max(0, last.length - 1))}…`;
  }
  return lines;
}

export function createNetwork(svgElement, agents, handlers = {}) {
  const { onSelectAgent, onClearSelection, onZoneFocusChange } = handlers;
  const width = svgElement.clientWidth || window.innerWidth;
  const height = svgElement.clientHeight || window.innerHeight;
  let selectedAgentId = null;
  let currentPhase = "idle";
  const activeAgentIds = new Set();
  let activeLeadId = null;
  let focusedZoneKey = null;
  let idleSpeechEnabled = false;
  let currentAnchor = { x: width * 0.5, y: height * 0.52 };
  let currentTransform = d3.zoomIdentity;
  let roleBuckets = {
    participants: new Set(),
    lateJoiners: new Set(),
    observers: new Set(),
    absent: new Set()
  };
  const lateJoinReadyAt = new Map();
  const scatterAssignment = new Map();
  const scatterReadyAt = new Map();
  const zonePulseUntil = new Map();

  const svg = d3.select(svgElement).attr("viewBox", `0 0 ${width} ${height}`);
  svg.on("click", () => {
    selectedAgentId = null;
    repaintSelection();
    if (onClearSelection) onClearSelection();
  });

  const viewportLayer = svg.append("g").attr("class", "viewport-layer");
  const studioLayer = viewportLayer.append("g").attr("class", "studio-bg");
  viewportLayer.append("g").attr("class", "session-layer");
  const linkLayer = viewportLayer.append("g").attr("class", "runtime-links");
  const flashLinkLayer = viewportLayer.append("g").attr("class", "flash-links");
  const nodeLayer = viewportLayer.append("g").attr("class", "node-layer");
  const speechLayer = viewportLayer.append("g").attr("class", "speech-layer");
  const defs = svg.append("defs");
  const maskId = `studio_fade_mask_${Math.random().toString(36).slice(2, 9)}`;
  const gradientId = `studio_fade_gradient_${Math.random().toString(36).slice(2, 9)}`;

  defs
    .append("radialGradient")
    .attr("id", gradientId)
    .attr("cx", "50%")
    .attr("cy", "50%")
    .attr("r", "68%")
    .attr("fx", "50%")
    .attr("fy", "50%")
    .call((g) => {
      g.append("stop").attr("offset", "0%").attr("stop-color", "#ffffff").attr("stop-opacity", 1);
      g.append("stop").attr("offset", "62%").attr("stop-color", "#ffffff").attr("stop-opacity", 1);
      g.append("stop").attr("offset", "86%").attr("stop-color", "#ffffff").attr("stop-opacity", 0.45);
      g.append("stop").attr("offset", "100%").attr("stop-color", "#000000").attr("stop-opacity", 0);
    });

  const fadeMask = defs.append("mask").attr("id", maskId).attr("maskUnits", "userSpaceOnUse");
  fadeMask
    .append("rect")
    .attr("x", 0)
    .attr("y", 0)
    .attr("width", width)
    .attr("height", height)
    .attr("fill", `url(#${gradientId})`);

  const backgroundScale = 1.025;
  const backgroundWidth = width * backgroundScale;
  const backgroundHeight = height * backgroundScale;
  const backgroundOffsetX = (width - backgroundWidth) * 0.5;
  const backgroundOffsetY = (height - backgroundHeight) * 0.5;

  studioLayer
    .append("image")
    .attr("href", "/background/studio_floorplan_v15.svg")
    .attr("x", backgroundOffsetX)
    .attr("y", backgroundOffsetY)
    .attr("width", backgroundWidth)
    .attr("height", backgroundHeight)
    .attr("preserveAspectRatio", "xMidYMid slice")
    .attr("mask", `url(#${maskId})`)
    .style("pointer-events", "none");

  const studioZones = [
    { key: "archive", label: "ARCHIVE", x: width * 0.06, y: height * 0.08, w: width * 0.24, h: height * 0.22 },
    { key: "directors", label: "DIRECTORS", x: width * 0.64, y: height * 0.08, w: width * 0.28, h: height * 0.24 },
    { key: "mainStage", label: "MAIN STAGE", x: width * 0.33, y: height * 0.32, w: width * 0.34, h: height * 0.28 },
    { key: "edit", label: "EDIT", x: width * 0.08, y: height * 0.64, w: width * 0.24, h: height * 0.22 },
    { key: "sound", label: "SOUND", x: width * 0.66, y: height * 0.64, w: width * 0.24, h: height * 0.22 }
  ];
  const zoneByKey = Object.fromEntries(
    studioZones.map((zone) => [
      zone.key,
      { x: zone.x + zone.w * 0.5, y: zone.y + zone.h * 0.5 }
    ])
  );

  function resolveZoneByViewportCenter(transform) {
    const scale = Number(transform?.k || 1);
    if (!Number.isFinite(scale) || scale <= 0) return null;
    const translateX = Number(transform?.x || 0);
    const translateY = Number(transform?.y || 0);
    const centerX = (width * 0.5 - translateX) / scale;
    const centerY = (height * 0.5 - translateY) / scale;
    const matched = studioZones.find((zone) => {
      const withinX = centerX >= zone.x && centerX <= zone.x + zone.w;
      const withinY = centerY >= zone.y && centerY <= zone.y + zone.h;
      return withinX && withinY;
    });
    return matched?.key || null;
  }

  const studioZoneSel = studioLayer
    .selectAll("g")
    .data(studioZones)
    .enter()
    .append("g")
    .attr("class", "studio-zone");

  studioZoneSel
    .append("rect")
    .attr("x", (d) => d.x)
    .attr("y", (d) => d.y)
    .attr("width", (d) => d.w)
    .attr("height", (d) => d.h)
    .attr("rx", 10)
    .attr("ry", 10);

  studioZoneSel
    .append("rect")
    .attr("class", "studio-zone-hit")
    .attr("x", (d) => d.x)
    .attr("y", (d) => d.y)
    .attr("width", (d) => d.w)
    .attr("height", (d) => d.h)
    .attr("rx", 10)
    .attr("ry", 10)
    .on("click", (event, zone) => {
      event.stopPropagation();
      zoomToZone(zone.key);
    });

  const nodes = agents.map((item) => ({
    ...item,
    homeZone: item.homeZone || (item.type === "crew" ? "archive" : "directors"),
    avatarUrl: item.avatarUrl || "",
    avatarPatternId: `avatar_${safeNodeId(item.agentId)}`,
    x: item.home.x * width,
    y: item.home.y * height
  }));

  const simulation = d3.forceSimulation(nodes)
    .force("charge", d3.forceManyBody().strength(-42))
    .force("collision", d3.forceCollide().radius(26))
    .force("x", d3.forceX((d) => getTargetForNode(d).x).strength((d) => getTargetStrength(d)))
    .force("y", d3.forceY((d) => getTargetForNode(d).y).strength((d) => getTargetStrength(d)))
    .force("bezierGather", createBezierGatherForce());

  const node = nodeLayer
    .selectAll("g")
    .data(nodes)
    .enter()
    .append("g")
    .style("cursor", "pointer")
    .on("click", (event, d) => {
      event.stopPropagation();
      selectedAgentId = d.agentId;
      repaintSelection();
      if (onSelectAgent) onSelectAgent(d);
    });

  const circles = node.append("circle")
    .attr("r", 10)
    .attr("fill", (d) => (d.avatarUrl ? "none" : nodeColor(d.type)))
    .attr("stroke", (d) => (d.avatarUrl ? "none" : "rgba(201, 168, 76, 0.5)"))
    .attr("stroke-width", (d) => (d.avatarUrl ? 0 : 1));

  const avatarImages = node.append("image")
    .attr("class", "agent-avatar-image")
    .attr("href", (d) => d.avatarUrl || "")
    .attr("x", -11)
    .attr("y", -11)
    .attr("width", 22)
    .attr("height", 22)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .attr("opacity", (d) => (d.avatarUrl ? 1 : 0))
    .style("pointer-events", "none");

  node
    .append("text")
    .attr("class", "agent-label agent-label-zh")
    .attr("x", 0)
    .attr("y", 24)
    .attr("text-anchor", "middle")
    .text((d) => getDisplayName(d).zh);

  node
    .append("text")
    .attr("class", "agent-label agent-label-en")
    .attr("x", 0)
    .attr("y", 35)
    .attr("text-anchor", "middle")
    .text((d) => getDisplayName(d).en);

  const speechGroup = speechLayer
    .selectAll("g")
    .data(nodes)
    .enter()
    .append("g")
    .attr("class", "agent-speech")
    .attr("opacity", 0)
    .attr("display", "none")
    .style("pointer-events", "none");

  speechGroup
    .append("rect")
    .attr("class", "agent-speech-bg")
    .attr("x", 14)
    .attr("y", -34)
    .attr("width", 98)
    .attr("height", 22)
    .attr("rx", 8)
    .attr("ry", 8);

  speechGroup
    .append("path")
    .attr("class", "agent-speech-tail")
    .attr("d", "M22,-12 L18,-6 L28,-12");

  speechGroup
    .append("text")
    .attr("class", "agent-speech-text")
    .attr("x", 20)
    .attr("y", -19)
    .text("");

  const speechByAgent = new Map();
  const speechTimerByAgent = new Map();
  const speechTextByAgent = new Map();
  let currentSpeakerAgentId = null;
  speechGroup.each((d, index, groups) => {
    speechByAgent.set(d.agentId, d3.select(groups[index]));
    speechTextByAgent.set(d.agentId, "");
  });

  const runtimeLinks = linkLayer
    .selectAll("line")
    .data(nodes)
    .enter()
    .append("line")
    .attr("class", "runtime-link")
    .attr("x1", currentAnchor.x)
    .attr("y1", currentAnchor.y)
    .attr("x2", (d) => d.x)
    .attr("y2", (d) => d.y)
    .attr("opacity", 0);

  simulation.on("tick", () => {
    node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    speechGroup.attr("transform", (d) => `translate(${d.x},${d.y})`);
    runtimeLinks
      .attr("x1", currentAnchor.x)
      .attr("y1", currentAnchor.y)
      .attr("x2", (d) => d.x)
      .attr("y2", (d) => d.y);
    repaintNodeStates();
    repaintRuntimeLinks();
  });

  const zoomBehavior = d3.zoom()
    .scaleExtent([0.78, 2.6])
    .on("zoom", (event) => {
      currentTransform = event.transform;
      viewportLayer.attr("transform", currentTransform.toString());
      const effectiveZoneKey = resolveZoneByViewportCenter(currentTransform);
      if (onZoneFocusChange) onZoneFocusChange(effectiveZoneKey, currentTransform.k);
    });

  svg.call(zoomBehavior).on("wheel", (event) => {
    if (focusedZoneKey && event.deltaY > 0) {
      resetCamera();
    }
  });

  function repaintSelection() {
    circles
      .attr("stroke-width", (d) => (d.avatarUrl ? 0 : d.agentId === selectedAgentId ? 2.4 : 1))
      .attr("stroke", (d) => {
        if (d.avatarUrl) return "none";
        return d.agentId === selectedAgentId ? "rgba(201, 168, 76, 1)" : "rgba(201, 168, 76, 0.5)";
      });
  }

  function repaintNodeStates() {
    circles
      .attr("r", (d) => {
        const isActive = activeAgentIds.has(d.agentId);
        if (d.agentId === activeLeadId) return 13;
        if (isActive) return 11.5;
        return 10;
      })
      .attr("fill", (d) => {
        if (d.avatarUrl) return "none";
        if (d.agentId === activeLeadId) return "#f0cd71";
        if (activeAgentIds.has(d.agentId)) return "#dbc28a";
        return nodeColor(d.type);
      })
      .attr("stroke", (d) => (d.avatarUrl ? "none" : "rgba(201, 168, 76, 0.5)"))
      .attr("stroke-width", (d) => {
        if (d.avatarUrl) return 0;
        if (d.agentId === selectedAgentId) return 2.4;
        return 1;
      })
      .attr("opacity", (d) => {
        if (currentPhase === "idle") return 1;
        if (activeAgentIds.size === 0) return 1;
        if (d.avatarUrl) return 0;
        if (activeAgentIds.has(d.agentId)) return 1;
        if (roleBuckets.absent.has(d.agentId)) return 0.5;
        return 0.72;
      });

    avatarImages
      .attr("x", (d) => {
        const isActive = activeAgentIds.has(d.agentId);
        const size = d.agentId === activeLeadId ? 32 : isActive ? 27 : 24;
        return -size / 2;
      })
      .attr("y", (d) => {
        const isActive = activeAgentIds.has(d.agentId);
        const size = d.agentId === activeLeadId ? 32 : isActive ? 27 : 24;
        return -size / 2;
      })
      .attr("width", (d) => {
        const isActive = activeAgentIds.has(d.agentId);
        if (d.agentId === activeLeadId) return 32;
        if (isActive) return 27;
        return 24;
      })
      .attr("height", (d) => {
        const isActive = activeAgentIds.has(d.agentId);
        if (d.agentId === activeLeadId) return 32;
        if (isActive) return 27;
        return 24;
      })
      .attr("opacity", (d) => {
        if (!d.avatarUrl) return 0;
        if (currentPhase === "idle" || activeAgentIds.size === 0) return 1;
        if (activeAgentIds.has(d.agentId)) return 1;
        return roleBuckets.absent.has(d.agentId) ? 0.54 : 0.78;
      });

    node
      .selectAll(".agent-label")
      .attr("opacity", (d) => {
        if (currentPhase === "idle" || activeAgentIds.size === 0) return 0.85;
        return activeAgentIds.has(d.agentId) ? 1 : 0.68;
      });
  }

  function repaintRuntimeLinks() {
    runtimeLinks
      .attr("stroke", (d) => (d.agentId === activeLeadId ? "rgba(201, 168, 76, 0.72)" : "rgba(201, 168, 76, 0.35)"))
      .attr("stroke-width", (d) => (d.agentId === activeLeadId ? 1.5 : 1))
      .attr("stroke-dasharray", "4 8")
      .attr("opacity", (d) => (activeAgentIds.has(d.agentId) && currentPhase !== "idle" ? 0.95 : 0));
  }

  function getTargetStrength(node) {
    if (currentPhase === "idle") return 0.08;
    if ((currentPhase === "forming" || currentPhase === "discuss") && (node.type === "director" || node.type === "guardian")) {
      return 0.2;
    }
    if (!activeAgentIds.size) return 0.16;
    if (activeAgentIds.has(node.agentId)) return 0.24;
    return 0.06;
  }

  function isLateJoinPending(agentId) {
    const readyAt = lateJoinReadyAt.get(agentId);
    if (!readyAt) return false;
    return Date.now() < readyAt;
  }

  function homeZoneCenter(node) {
    return zoneByKey[node.homeZone] || { x: node.home.x * width, y: node.home.y * height };
  }

  function getScatterTarget(node) {
    const readyAt = scatterReadyAt.get(node.agentId) || 0;
    if (Date.now() < readyAt) return homeZoneCenter(node);
    const zoneKey = scatterAssignment.get(node.agentId) || node.homeZone || "directors";
    return withOrbit(zoneByKey[zoneKey] || homeZoneCenter(node), node.agentId, 36);
  }

  function getTargetForNode(node) {
    if (currentPhase === "idle") {
      return { x: node.home.x * width, y: node.home.y * height };
    }

    if (currentPhase === "scatter") {
      return getScatterTarget(node);
    }

    if (currentPhase === "collect" || currentPhase === "analyze") {
      if (!activeAgentIds.has(node.agentId)) return withOrbit(homeZoneCenter(node), node.agentId, 22);
      if (node.type === "crew") return withOrbit(zoneByKey.archive, node.agentId, 28);
      return withOrbit(zoneByKey.directors, node.agentId, 36);
    }

    if (currentPhase === "discuss" || currentPhase === "forming") {
      const isDirectorOrGuardian = node.type === "director" || node.type === "guardian";
      if (isDirectorOrGuardian) {
        const isLate = roleBuckets.lateJoiners.has(node.agentId);
        const inParticipants = roleBuckets.participants.has(node.agentId);
        const isActive = activeAgentIds.has(node.agentId);
        const shouldJoinMainStage = inParticipants || isActive;
        if (!shouldJoinMainStage) {
          return withOrbit(homeZoneCenter(node), node.agentId, 24);
        }
        if (isLate && isLateJoinPending(node.agentId)) {
          return withOrbit(zoneByKey.mainStage, node.agentId, 120);
        }
        return withOrbit(zoneByKey.mainStage, node.agentId, node.agentId === activeLeadId ? 18 : 62);
      }
      if (roleBuckets.lateJoiners.has(node.agentId) && isLateJoinPending(node.agentId)) {
        return withOrbit(homeZoneCenter(node), node.agentId, 24);
      }
      if (!activeAgentIds.has(node.agentId)) return withOrbit(homeZoneCenter(node), node.agentId, 24);
      return withOrbit(zoneByKey.mainStage, node.agentId, node.agentId === activeLeadId ? 18 : 60);
    }

    if (currentPhase === "edit") {
      if (!activeAgentIds.has(node.agentId)) return withOrbit(homeZoneCenter(node), node.agentId, 24);
      if (node.name.includes("剪辑")) return withOrbit(zoneByKey.edit, node.agentId, 20);
      if (node.name.includes("配乐")) return withOrbit(zoneByKey.sound, node.agentId, 28);
      return withOrbit(zoneByKey.mainStage, node.agentId, 72);
    }

    if (currentPhase === "render" || currentPhase === "deliver") {
      if (!activeAgentIds.has(node.agentId)) return withOrbit(homeZoneCenter(node), node.agentId, 24);
      if (node.type === "crew") {
        const slot = node.name.includes("配乐") ? zoneByKey.sound : zoneByKey.edit;
        return withOrbit(slot, node.agentId, 26);
      }
      return withOrbit(zoneByKey.mainStage, node.agentId, 90);
    }

    return { x: node.home.x * width, y: node.home.y * height };
  }

  function withOrbit(center, seedText, radius) {
    const seed = hash(seedText);
    const angle = (seed % 360) * (Math.PI / 180);
    return {
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius
    };
  }

  function hash(text) {
    let value = 0;
    for (let i = 0; i < text.length; i += 1) {
      value = (value * 31 + text.charCodeAt(i)) >>> 0;
    }
    return value;
  }

  function repaintPhase() {
    studioZoneSel
      .select("rect")
      .transition()
      .duration(260)
      .attr("fill", "transparent")
      .attr("stroke", "transparent");
  }

  function zoomToZone(zoneKey, scale = 1.9) {
    const zoneMeta = studioZones.find((zone) => zone.key === zoneKey);
    if (!zoneMeta) return;
    focusedZoneKey = zoneKey;
    const cx = zoneMeta.x + zoneMeta.w * 0.5;
    const cy = zoneMeta.y + zoneMeta.h * 0.5;
    const tx = width * 0.5 - cx * scale;
    const ty = height * 0.5 - cy * scale;
    svg
      .transition()
      .duration(480)
      .call(zoomBehavior.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
    repaintPhase();
  }

  function resetCamera() {
    focusedZoneKey = null;
    svg.transition().duration(420).call(zoomBehavior.transform, d3.zoomIdentity);
    repaintPhase();
  }

  function setRoleBuckets(nextBuckets) {
    roleBuckets = {
      participants: new Set(nextBuckets?.participants || []),
      lateJoiners: new Set(nextBuckets?.lateJoiners || []),
      observers: new Set(nextBuckets?.observers || []),
      absent: new Set(nextBuckets?.absent || [])
    };
    lateJoinReadyAt.clear();
    for (const id of roleBuckets.lateJoiners) {
      const delay = 500 + Math.floor(Math.random() * 7500);
      lateJoinReadyAt.set(id, Date.now() + delay);
    }
    if (currentPhase === "forming" || currentPhase === "discuss") {
      runGatherMotionForCurrentPhase();
    }
    simulation.alpha(0.7).restart();
  }

  function gather() {
    currentPhase = "forming";
    currentAnchor = zoneByKey.mainStage;
    scatterAssignment.clear();
    scatterReadyAt.clear();
    zonePulseUntil.set("mainStage", Date.now() + 1500);
    runGatherMotionForCurrentPhase();
    repaintPhase();
    simulation
      .alpha(0.9)
      .restart();
  }

  function release() {
    currentPhase = "idle";
    currentAnchor = zoneByKey.mainStage;
    roleBuckets = {
      participants: new Set(),
      lateJoiners: new Set(),
      observers: new Set(),
      absent: new Set()
    };
    scatterAssignment.clear();
    scatterReadyAt.clear();
    clearAllMotions();
    repaintPhase();
    simulation
      .alpha(0.8)
      .restart();
  }

  function triggerLateJoiner(agentId) {
    if (!roleBuckets.lateJoiners.has(agentId)) return;
    lateJoinReadyAt.set(agentId, Date.now() - 1);
    activeAgentIds.add(agentId);
    if (currentPhase === "forming" || currentPhase === "discuss") {
      runGatherMotionForCurrentPhase();
    }
    simulation.alpha(0.66).restart();
  }

  function pulseZone(zoneKey, duration = 550) {
    if (!zoneByKey[zoneKey]) return;
    zonePulseUntil.set(zoneKey, Date.now() + duration);
    repaintPhase();
    window.setTimeout(() => repaintPhase(), duration + 40);
  }

  function scatterAfterWrapup() {
    currentPhase = "scatter";
    currentAnchor = zoneByKey.mainStage;
    for (const node of nodes) {
      const destination = resolveScatterDestination(node, activeAgentIds.has(node.agentId));
      scatterAssignment.set(node.agentId, destination);
      const delay = 500 + Math.floor(Math.random() * 7500);
      scatterReadyAt.set(node.agentId, Date.now() + delay);
    }
    runScatterMotion();
    pulseZone("edit", 780);
    pulseZone("sound", 900);
    simulation.alpha(0.92).restart();
  }

  function setSelected(agentId) {
    selectedAgentId = agentId;
    repaintSelection();
  }

  function setPhase(phase) {
    currentPhase = phase || "idle";
    if (currentPhase === "collect" || currentPhase === "analyze") currentAnchor = zoneByKey.archive;
    else if (currentPhase === "edit") currentAnchor = zoneByKey.edit;
    else if (currentPhase === "render" || currentPhase === "deliver") currentAnchor = zoneByKey.sound;
    else currentAnchor = zoneByKey.mainStage;
    if (currentPhase === "collect") pulseZone("archive");
    if (currentPhase === "edit") pulseZone("edit");
    if (currentPhase === "render") pulseZone("sound");
    if (currentPhase === "forming" || currentPhase === "discuss") {
      runGatherMotionForCurrentPhase();
    } else if (currentPhase === "scatter") {
      runScatterMotion();
    } else if (currentPhase === "idle") {
      clearAllMotions();
    }
    repaintPhase();
    simulation.alpha(0.58).restart();
  }

  function setActiveAgents(agentIds, leadId = null) {
    const prevSnapshot = [...activeAgentIds].sort().join("|");
    activeAgentIds.clear();
    for (const id of agentIds || []) activeAgentIds.add(id);
    const nextSnapshot = [...activeAgentIds].sort().join("|");
    const changed = prevSnapshot !== nextSnapshot || (leadId || null) !== activeLeadId;
    activeLeadId = leadId || null;
    repaintNodeStates();
    repaintRuntimeLinks();
    if (changed) {
      if (currentPhase === "forming" || currentPhase === "discuss") {
        runGatherMotionForCurrentPhase();
      }
      simulation.alpha(Math.max(simulation.alpha(), 0.72)).restart();
    }
  }

  function showAgentSpeech(agentId, content, options = {}) {
    if (!idleSpeechEnabled && !options.force) return;
    const bubble = speechByAgent.get(agentId);
    if (!bubble) return;
    const duration = Number(options.duration || 30000);
    const append = options.append !== false;
    const previous = speechTextByAgent.get(agentId) || "";
    const incoming = String(content || "").replace(/\s+/g, " ").trim();
    const merged = append && previous ? `${previous} ${incoming}` : incoming;
    const normalized = compactSpeech(merged);
    speechTextByAgent.set(agentId, normalized);
    const lines = splitSpeechLines(normalized);
    const maxLine = lines.reduce((acc, line) => Math.max(acc, line.length), 0);
    const width = Math.max(116, Math.min(300, maxLine * 9 + 28));
    const height = Math.max(24, 10 + lines.length * 14);
    bubble.select(".agent-speech-bg").attr("width", width).attr("height", height).attr("y", -(height + 12));
    bubble.select(".agent-speech-tail").attr("d", "M25,-12 L20,-6 L30,-12");
    const text = bubble.select(".agent-speech-text");
    text.selectAll("tspan").remove();
    lines.forEach((line, idx) => {
      text
        .append("tspan")
        .attr("x", 20)
        .attr("dy", idx === 0 ? (-(height - 8)) : 14)
        .text(line);
    });

    // Keep only one active speaker bubble visible until the next speaker talks.
    if (currentSpeakerAgentId && currentSpeakerAgentId !== agentId) {
      const prevBubble = speechByAgent.get(currentSpeakerAgentId);
      if (prevBubble) {
        prevBubble.interrupt();
        prevBubble.attr("opacity", 0).attr("display", "none");
      }
      const prevTimer = speechTimerByAgent.get(currentSpeakerAgentId);
      if (prevTimer) window.clearTimeout(prevTimer);
      speechTimerByAgent.delete(currentSpeakerAgentId);
    }
    currentSpeakerAgentId = agentId;
    bubble.attr("display", null).transition().duration(180).attr("opacity", 1);

    const prevTimer = speechTimerByAgent.get(agentId);
    if (prevTimer) window.clearTimeout(prevTimer);
    const timer = window.setTimeout(() => {
      bubble
        .transition()
        .duration(220)
        .attr("opacity", 0)
        .on("end", () => bubble.attr("display", "none"));
      speechTimerByAgent.delete(agentId);
      if (currentSpeakerAgentId === agentId) currentSpeakerAgentId = null;
    }, duration);
    speechTimerByAgent.set(agentId, timer);
  }

  function clearAllSpeech() {
    for (const timer of speechTimerByAgent.values()) window.clearTimeout(timer);
    speechTimerByAgent.clear();
    for (const bubble of speechByAgent.values()) {
      bubble.interrupt();
      bubble.attr("opacity", 0).attr("display", "none");
    }
    for (const key of speechTextByAgent.keys()) speechTextByAgent.set(key, "");
    currentSpeakerAgentId = null;
  }

  function setIdleSpeechEnabled(enabled) {
    idleSpeechEnabled = Boolean(enabled);
    if (!idleSpeechEnabled) {
      clearAllSpeech();
    }
  }

  function findNodeByName(name) {
    const target = String(name || "").trim();
    if (!target) return null;
    return (
      nodes.find((nodeItem) => {
        const display = getDisplayName(nodeItem);
        return (
          nodeItem.name === target ||
          nodeItem.agentId === target ||
          display.zh === target ||
          display.en === target
        );
      }) || null
    );
  }

  function flashLink(fromName, toName, options = {}) {
    const fromNode = findNodeByName(fromName);
    const toNode = findNodeByName(toName);
    if (!fromNode || !toNode) return;
    const duration = Number(options.duration || 1800);
    const color = String(options.color || "rgba(201, 168, 76, 0.85)");
    const status = String(options.status || "calling");
    const stroke =
      status === "failed" ? "rgba(255, 130, 130, 0.9)" : status === "ok" ? "rgba(159, 211, 167, 0.9)" : color;
    const dx = toNode.x - fromNode.x;
    const dy = toNode.y - fromNode.y;
    const midX = (fromNode.x + toNode.x) / 2;
    const midY = (fromNode.y + toNode.y) / 2 - Math.min(46, Math.max(18, Math.hypot(dx, dy) * 0.18));
    const path = flashLinkLayer
      .append("path")
      .attr("class", "flash-link")
      .attr("d", `M${fromNode.x},${fromNode.y} Q${midX},${midY} ${toNode.x},${toNode.y}`)
      .attr("stroke", stroke)
      .attr("stroke-width", 2.4)
      .attr("fill", "none")
      .attr("stroke-linecap", "round")
      .attr("opacity", 0.95);
    const length = path.node()?.getTotalLength?.() || 220;
    path
      .attr("stroke-dasharray", `${length}`)
      .attr("stroke-dashoffset", `${length}`)
      .transition()
      .duration(duration)
      .ease(d3.easeLinear)
      .attr("stroke-dashoffset", "0")
      .attr("opacity", 0.15)
      .on("end", () => path.remove());
  }

  function runGatherMotionForCurrentPhase() {
    const anchor = zoneByKey.mainStage;
    for (const nodeItem of nodes) {
      const isDirectorOrGuardian = nodeItem.type === "director" || nodeItem.type === "guardian";
      const inParticipants = roleBuckets.participants.has(nodeItem.agentId);
      const isActive = activeAgentIds.has(nodeItem.agentId);
      const shouldGather = isDirectorOrGuardian ? (inParticipants || isActive) : isActive;
      if (!shouldGather) continue;
      const target = getTargetForNode(nodeItem);
      startGatherMotion(nodeItem, target, anchor);
    }
  }

  function runScatterMotion() {
    const anchor = zoneByKey.mainStage;
    for (const nodeItem of nodes) {
      const target = getScatterTarget(nodeItem);
      startGatherMotion(nodeItem, target, anchor);
    }
  }

  function clearGatherMotion(nodeItem) {
    nodeItem.motion = null;
    nodeItem.fx = null;
    nodeItem.fy = null;
  }

  function clearAllMotions() {
    for (const nodeItem of nodes) {
      clearGatherMotion(nodeItem);
    }
  }

  function startGatherMotion(nodeItem, target, anchor) {
    if (!target || !Number.isFinite(target.x) || !Number.isFinite(target.y)) return;
    const from = {
      x: Number.isFinite(nodeItem.x) ? nodeItem.x : nodeItem.home.x * width,
      y: Number.isFinite(nodeItem.y) ? nodeItem.y : nodeItem.home.y * height
    };
    const curve = buildGatherCurve(from, target, anchor || zoneByKey.mainStage, nodeItem.agentId);
    const pauseEnabled = Math.random() < 0.36;
    const pauseAt = pauseEnabled ? 0.35 + Math.random() * 0.37 : -1;
    const pauseFor = pauseEnabled ? 160 + Math.floor(Math.random() * 260) : 0;
    nodeItem.motion = {
      startedAt: performance.now(),
      duration: gatherDuration(from, target),
      curve,
      pauseAt,
      pauseFor,
      pausedAt: 0
    };
  }

  function createBezierGatherForce() {
    let motionNodes = [];
    function force() {
      const now = performance.now();
      for (const nodeItem of motionNodes) {
        if (!nodeItem.motion) continue;
        const pausedElapsed = nodeItem.motion.pausedAt
          ? now - nodeItem.motion.pausedAt
          : 0;
        if (nodeItem.motion.pausedAt && pausedElapsed < nodeItem.motion.pauseFor) {
          continue;
        }
        if (nodeItem.motion.pausedAt && pausedElapsed >= nodeItem.motion.pauseFor) {
          nodeItem.motion.startedAt += pausedElapsed;
          nodeItem.motion.pausedAt = 0;
        }
        const t = clamp((now - nodeItem.motion.startedAt) / nodeItem.motion.duration, 0, 1);
        if (
          nodeItem.motion.pauseAt > 0 &&
          !nodeItem.motion.pausedAt &&
          t >= nodeItem.motion.pauseAt &&
          t < 0.95
        ) {
          nodeItem.motion.pausedAt = now;
          continue;
        }
        const eased = easeInOutCubic(t);
        const point = cubicBezierPoint(nodeItem.motion.curve, eased);
        nodeItem.fx = point.x;
        nodeItem.fy = point.y;
        nodeItem.x = point.x;
        nodeItem.y = point.y;
        if (t >= 1) {
          clearGatherMotion(nodeItem);
        }
      }
    }
    force.initialize = (nextNodes) => {
      motionNodes = nextNodes;
    };
    return force;
  }

  function buildGatherCurve(start, end, anchor, seedText) {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const distance = Math.hypot(dx, dy) || 1;
    const normal = { x: -dy / distance, y: dx / distance };
    const bendDirection = hash(seedText) % 2 === 0 ? 1 : -1;
    const bend = clamp(distance * 0.22, 48, 140) * bendDirection;
    return {
      p0: start,
      p1: {
        x: start.x + dx * 0.24 + normal.x * bend,
        y: start.y + dy * 0.18 + normal.y * bend
      },
      p2: {
        x: anchor.x + (end.x - anchor.x) * 0.42 - normal.x * bend * 0.35,
        y: anchor.y + (end.y - anchor.y) * 0.42 - normal.y * bend * 0.35
      },
      p3: end
    };
  }

  function cubicBezierPoint(curve, t) {
    const mt = 1 - t;
    const mt2 = mt * mt;
    const t2 = t * t;
    const a = mt2 * mt;
    const b = 3 * mt2 * t;
    const c = 3 * mt * t2;
    const d = t * t2;
    return {
      x: a * curve.p0.x + b * curve.p1.x + c * curve.p2.x + d * curve.p3.x,
      y: a * curve.p0.y + b * curve.p1.y + c * curve.p2.y + d * curve.p3.y
    };
  }

  function gatherDuration(start, target) {
    const distance = Math.hypot(target.x - start.x, target.y - start.y);
    return clamp(900 + distance * 2.1, 1100, 2600);
  }

  function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - ((-2 * t + 2) ** 3) / 2;
  }

  function resolveScatterDestination(nodeItem, wasActive) {
    if (nodeItem.type === "crew") {
      return nodeItem.scatterPreference || "archive";
    }

    const personaScatter = {
      "agent-yates": { deep: "sound", casual: "sound" },
      "agent-jackson": { deep: "sound", casual: "sound" },
      "agent-curtis": { deep: "sound", casual: "sound" },
      "agent-spielberg": { deep: "sound", casual: "sound" },
      "agent-cuaron": { deep: "edit", casual: "edit" },
      "agent-burton": { deep: "edit", casual: "edit" },
      "agent-columbus": { deep: "edit", casual: "edit" },
      "agent-newell": { deep: "edit", casual: "edit" },
      "agent-rowling": { deep: "directors", casual: "directors" },
      "agent-tolkien": { deep: "directors", casual: "directors" }
    };
    const profile = personaScatter[nodeItem.agentId];
    if (!profile) return nodeItem.scatterPreference || "directors";

    if (wasActive) return profile.deep;
    if (Math.random() < 0.68) return profile.casual;
    return "directors";
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  repaintPhase();

  return {
    gather,
    release,
    setSelected,
    setPhase,
    setActiveAgents,
    setRoleBuckets,
    triggerLateJoiner,
    scatterAfterWrapup,
    pulseZone,
    zoomToZone,
    resetCamera,
    flashLink,
    showAgentSpeech,
    clearAllSpeech,
    setIdleSpeechEnabled
  };
}
