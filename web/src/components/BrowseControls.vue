<template>
  <div class="browse-controls">
    <button type="button" class="ghost-btn" @click="$emit('zoom-directors')">导演室特写</button>
    <button type="button" class="ghost-btn" @click="$emit('zoom-reset')">返回全景</button>
  </div>
</template>

<script setup>
defineEmits(["zoom-directors", "zoom-reset"]);
</script>
