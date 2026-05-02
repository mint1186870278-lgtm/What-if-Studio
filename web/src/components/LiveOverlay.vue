<template>
  <div v-if="visible" class="live-overlay" :class="{ 'is-fading': fading }">
    <div class="live-overlay-header">
      <span class="live-dot"></span>
      <span class="live-title">{{ title }}</span>
      <button v-if="retryVisible" type="button" class="ghost-btn" @click="$emit('retry')">
        {{ retryLabel }}
      </button>
    </div>
    <div class="phase-timeline">
      <span v-for="phase in phases" :key="phase" :class="{ 'is-active': activePhase === phase }">
        {{ phase }}
      </span>
    </div>
    <div ref="feedRef" class="live-feed">
      <template v-for="item in items" :key="item.id">
        <div v-if="item.kind === 'topic'" class="live-topic-card">
          <div class="live-topic-q">{{ item.text }}</div>
        </div>
        <div v-else-if="item.kind === 'section'" class="live-section">
          <span>{{ item.title }}</span>
        </div>
        <div v-else-if="item.kind === 'message'" class="live-msg is-visible">
          <img
            v-if="item.avatarUrl"
            class="live-msg-avatar live-msg-avatar-image"
            :src="item.avatarUrl"
            :alt="item.speaker"
          />
          <div v-else class="live-msg-avatar live-msg-avatar-placeholder">{{ item.avatarFallback }}</div>
          <div class="live-msg-body">
            <span class="live-msg-name">{{ item.speaker }}</span>
            <span class="live-msg-text">{{ item.content }}</span>
          </div>
        </div>
        <div v-else class="live-summary" :class="{ 'live-summary-final': item.kind === 'summary' }">
          <span class="live-summary-label">{{ item.label }}</span>
          <span>{{ item.text }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";

const props = defineProps({
  visible: { type: Boolean, default: false },
  fading: { type: Boolean, default: false },
  title: { type: String, default: "PRODUCTION IN PROGRESS" },
  phases: { type: Array, default: () => [] },
  activePhase: { type: String, default: "" },
  items: { type: Array, default: () => [] },
  retryVisible: { type: Boolean, default: false },
  retryLabel: { type: String, default: "重试流连接" }
});

const emit = defineEmits(["retry", "feed-ready"]);
const feedRef = ref(null);

onMounted(() => {
  emit("feed-ready", feedRef.value);
});

watch(
  () => props.items.length,
  () => {
    requestAnimationFrame(() => {
      if (feedRef.value) feedRef.value.scrollTop = feedRef.value.scrollHeight;
    });
  }
);
</script>
