<template>
  <div class="queue-indicator">
    <span class="queue-dot"></span>
    <span>{{ text }}</span>
  </div>
</template>

<script setup>
defineProps({
  text: { type: String, default: "STANDBY" }
});
</script>
