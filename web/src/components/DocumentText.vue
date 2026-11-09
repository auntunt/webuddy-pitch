<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ text: string }>()
const blocks = computed(() => {
  const out: { kind: string; text: string }[] = []
  let code: string[] | null = null
  for (const line of props.text.split('\n')) {
    if (line.startsWith('```')) {
      if (code) { out.push({ kind: 'code', text: code.join('\n') }); code = null }
      else code = []
    } else if (code) code.push(line)
    else if (/^#{1,6} /.test(line)) out.push({ kind: 'heading', text: line.replace(/^#+ /, '') })
    else out.push({ kind: 'text', text: line })
  }
  if (code) out.push({ kind: 'code', text: code.join('\n') })
  return out
})
</script>
<template><article class="document"><template v-for="(block,i) in blocks" :key="i"><pre v-if="block.kind === 'code'">{{ block.text }}</pre><h3 v-else-if="block.kind === 'heading'">{{ block.text }}</h3><div v-else class="line">{{ block.text || '\u00a0' }}</div></template></article></template>
<style scoped>.document { overflow-wrap:anywhere; padding:18px 0; line-height:1.85; }.document h3 { margin:20px 0 10px; font-size:17px; }.document pre { background:#f4f6f8; padding:16px; border-radius:6px; white-space:pre-wrap; font:13px/1.8 ui-monospace,monospace; }.line { white-space:pre-wrap; }</style>
