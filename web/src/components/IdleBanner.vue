<template>
  <div v-if="visible" class="idle-banner">
    <div class="idle-pulse"></div>
    <span>浏览模式：你可以随时缩放逛剧组</span>
    <span class="idle-sub">点击 DIRECTORS 可窥视导演室闲聊，准备好再开机</span>
  </div>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, default: true }
});
</script>
