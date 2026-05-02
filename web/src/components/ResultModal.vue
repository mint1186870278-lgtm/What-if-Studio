<template>
  <section v-if="result.visible" class="result-overlay" @click.self="$emit('close')">
    <article class="result-panel">
      <header class="result-head">
        <div class="result-head-left">
          <span class="result-status-dot" aria-hidden="true"></span>
          <span class="result-title">{{ result.title }}</span>
        </div>
        <div class="result-head-right">
          <span class="result-work-name">{{ result.workName }}</span>
          <button type="button" class="result-close-btn" aria-label="关闭结果弹窗" @click="$emit('close')">
            &times;
          </button>
        </div>
      </header>
      <div class="result-media">
        <template v-if="result.hasPlayableMp4">
          <video controls preload="metadata" :src="result.mediaUrl"></video>
          <a :href="result.mediaUrl" target="_blank" rel="noreferrer">在新窗口打开视频</a>
        </template>
        <div v-else class="result-video-placeholder" role="status" aria-live="polite">
          <span>VIDEO PLAYER</span>
          <small>当前暂无可播放视频，请重新制作或稍后重试。</small>
        </div>
      </div>
      <section class="result-notes">
        <div class="result-notes-head">CREW NOTES</div>
        <div class="result-notes-list">
          <div v-for="note in result.notes" :key="note.id" class="result-note-card">
            <div class="result-note-avatar">
              <img v-if="note.avatarUrl" class="result-note-avatar-image" :src="note.avatarUrl" :alt="note.name" />
              <span v-else class="result-note-avatar-placeholder">{{ note.fallback }}</span>
            </div>
            <div class="result-note-body">
              <div class="result-note-name">{{ note.name }}</div>
              <p class="result-note-text">{{ note.text }}</p>
            </div>
          </div>
        </div>
      </section>
      <footer class="result-actions">
        <div class="result-actions-left">
          <button type="button" class="ghost-btn result-ghost-btn" @click="$emit('download-share')">下载 / 分享</button>
        </div>
        <button type="button" class="result-primary-btn" @click="$emit('restart')">重新制作</button>
      </footer>
    </article>
  </section>
</template>

<script setup>
defineProps({
  result: { type: Object, required: true }
});

defineEmits(["close", "download-share", "restart"]);
</script>
