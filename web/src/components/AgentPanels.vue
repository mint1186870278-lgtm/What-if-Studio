<template>
  <div v-if="spotlightVisible" class="spotlight-card">
    <div class="spotlight-kicker">CREW SPOTLIGHT</div>
    <div class="spotlight-name">{{ spotlight.name }}</div>
    <div class="spotlight-subname">{{ spotlight.subname }}</div>
    <div class="spotlight-role">{{ spotlight.role }}</div>
    <div class="spotlight-summary">{{ spotlight.summary }}</div>
  </div>

  <div v-if="detail.agent" class="agent-detail-overlay">
    <button class="agent-detail-close" type="button" @click="$emit('close-detail')">&times;</button>
    <div class="agent-detail-name">{{ detail.name }}</div>
    <div class="agent-detail-subname">{{ detail.subname }}</div>
    <div class="agent-detail-role">{{ detail.role }}</div>
    <div class="agent-detail-stage">{{ detail.stage }}</div>
    <div class="agent-detail-summary">{{ detail.summary }}</div>
  </div>
</template>

<script setup>
defineProps({
  spotlightVisible: { type: Boolean, default: true },
  spotlight: { type: Object, required: true },
  detail: { type: Object, required: true }
});

defineEmits(["close-detail"]);
</script>
