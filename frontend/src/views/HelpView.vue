<template>
  <div class="help-view">
    <el-card>
      <template #header><span>使用手册</span></template>
      <div class="manual" v-html="html"></div>
    </el-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import manualMd from './manual.md?raw'

const html = computed(() => marked.parse(manualMd))
</script>

<style scoped>
.manual {
  line-height: 1.85;
  color: #1f2937;
}
.manual :deep(h1) {
  font-size: 22px;
  margin: 0 0 14px;
  color: #111827;
}
.manual :deep(h2) {
  font-size: 17px;
  margin: 24px 0 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #e5e7eb;
  color: #111827;
}
.manual :deep(h3) {
  font-size: 15px;
  margin: 16px 0 8px;
  color: #1f2937;
}
.manual :deep(p) {
  margin: 8px 0;
}
.manual :deep(ul),
.manual :deep(ol) {
  margin: 8px 0 8px 22px;
}
.manual :deep(li) {
  margin: 5px 0;
}
.manual :deep(code) {
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: #be185d;
}
.manual :deep(blockquote) {
  margin: 12px 0;
  padding: 8px 14px;
  border-left: 4px solid #2563eb;
  background: #eff6ff;
  color: #1e40af;
  border-radius: 4px;
}
.manual :deep(strong) {
  color: #111827;
}
.manual :deep(a) {
  color: #2563eb;
}
</style>
