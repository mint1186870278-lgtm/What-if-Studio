<template>
  <section v-if="review.visible" class="result-overlay" @click.self="$emit('backdrop')">
    <article class="result-panel">
      <header class="result-head">
        <div class="result-head-left">
          <span class="result-status-dot" aria-hidden="true"></span>
          <span class="result-title">导演讨论剧本</span>
        </div>
        <div class="result-head-right">
          <button type="button" class="result-close-btn" aria-label="关闭弹窗" @click="$emit('cancel')">&times;</button>
        </div>
      </header>
      <div class="result-notes">
        <div class="result-notes-head">SCRIPT</div>
        <pre class="result-note-text script-review-content">{{ review.content || "暂无脚本" }}</pre>
      </div>
      <div class="result-notes">
        <div class="result-notes-head">PROGRESS</div>
        <div class="result-note-text">{{ review.progress }}</div>
      </div>
      <div v-if="review.videoUrl" class="result-media">
        <video controls preload="metadata" :src="review.videoUrl"></video>
        <a :href="review.videoUrl" target="_blank" rel="noreferrer">在新窗口打开视频</a>
      </div>
      <footer class="result-actions">
        <div class="result-actions-left"></div>
        <button
          v-if="review.generateVisible"
          type="button"
          class="result-primary-btn"
          :disabled="!review.canGenerate"
          @click="$emit('confirm')"
        >
          确认并生成视频
        </button>
      </footer>
    </article>
  </section>
</template>

<script setup>
defineProps({
  review: { type: Object, required: true }
});

defineEmits(["confirm", "cancel", "backdrop"]);
</script>
