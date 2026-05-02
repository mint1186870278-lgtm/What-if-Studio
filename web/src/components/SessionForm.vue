<template>
  <form class="input-overlay" :class="{ 'is-collapsed': collapsed }" @submit.prevent="$emit('submit')">
    <div class="input-overlay-head">
      <div class="card-kicker">YINANPING STUDIO</div>
      <button type="button" class="ghost-btn overlay-toggle-btn" @click="$emit('toggle')">
        {{ collapsed ? "展开" : "收起" }}
      </button>
    </div>
    <h1>意难平剧组</h1>
    <p class="card-summary">无限画布浏览模式已开启，可先逛房间再开机。</p>

    <label class="field-label" for="work-title">作品名称</label>
    <input id="work-title" v-model="form.workTitle" name="workTitle" placeholder="例如：哈利波特与凤凰社" required />

    <label class="field-label" for="ending-direction">你想要的结局</label>
    <textarea
      id="ending-direction"
      v-model="form.endingDirection"
      name="endingDirection"
      placeholder="例如：小天狼星被救下，哈利和他拥抱收尾"
      required
    />

    <label class="field-label" for="style-preference">导演风格偏好</label>
    <select id="style-preference" v-model="form.stylePreference" name="stylePreference">
      <option value="auto">AI 自动决定</option>
      <option value="darkEpic">偏黑暗史诗</option>
      <option value="warmHealing">偏温情治愈</option>
      <option value="realism">偏文艺写实</option>
      <option value="fantasyGrand">偏奇幻宏大</option>
    </select>

    <label class="field-label" for="source-video-file">上传素材视频（可选）</label>
    <input id="source-video-file" name="sourceVideoFile" type="file" accept="video/*" @change="onFileChange" />
    <p v-if="selectedFileName" class="card-summary card-summary-soft">{{ selectedFileName }}</p>
    <p v-if="idleDialogueWarning" class="card-summary card-summary-soft form-warning">
      闲聊语料加载失败，已降级为基础闲聊模式。
    </p>

    <div class="quick-actions">
      <button type="button" class="ghost-btn" @click="$emit('load-demo')">加载示例</button>
      <button type="submit">开机 -></button>
    </div>
  </form>
</template>

<script setup>
defineProps({
  form: { type: Object, required: true },
  collapsed: { type: Boolean, default: false },
  idleDialogueWarning: { type: Boolean, default: false },
  selectedFileName: { type: String, default: "" }
});

const emit = defineEmits(["submit", "toggle", "load-demo", "file-change"]);

function onFileChange(event) {
  emit("file-change", event.target.files?.[0] || null);
}
</script>
