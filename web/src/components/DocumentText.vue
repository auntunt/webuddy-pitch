<script setup lang="ts">
import { computed, defineComponent, h, Fragment, createTextVNode } from 'vue'
const props = defineProps<{ text: string }>()
type Block = {kind:string;text?:string;level?:number;rows?:string[][];items?:string[];ordered?:boolean;start?:number}
function cells(line:string) {
  const value=line.trim().replace(/^\|/,'').replace(/(?<!\\)\|$/,'')
  const result:string[]=[];let current='',code=false,escaped=false
  for(const char of value){
    if(escaped){current+=char==='|'?char:'\\'+char;escaped=false;continue}
    if(char==='\\'){escaped=true;continue}
    if(char==='`')code=!code
    if(char==='|'&&!code){result.push(current.trim());current=''}else current+=char
  }
  result.push((current+(escaped?'\\':'')).trim());return result
}
const blocks=computed(()=>{
  const lines=props.text.replace(/\r\n/g,'\n').split('\n'),out:Block[]=[]
  const list=/^\s*(?:(\d+)[.)]|[-+*])\s+(.+)$/
  const special=(i:number)=>/^\s*```|^#{1,6}\s|^\s*>|^\s*(?:[-*_]\s*){3,}$/.test(lines[i]||'')||list.test(lines[i]||'')||isTable(i)
  const isTable=(i:number)=>!!lines[i]?.includes('|')&&!!lines[i+1]?.includes('|')&&cells(lines[i+1]!).every(cell=>/^:?-{3,}:?$/.test(cell))
  for(let i=0;i<lines.length;){
    const line=lines[i]!
    if(!line.trim()){i++;continue}
    if(/^\s*```/.test(line)){const body:string[]=[];i++;while(i<lines.length&&!/^\s*```\s*$/.test(lines[i]!))body.push(lines[i++]!);if(i<lines.length)i++;out.push({kind:'code',text:body.join('\n')});continue}
    const heading=/^(#{1,6})\s+(.+)$/.exec(line)
    if(heading){out.push({kind:'heading',level:heading[1]!.length,text:heading[2]});i++;continue}
    if(isTable(i)){const rows=[cells(line)];i+=2;while(i<lines.length&&lines[i]!.trim()&&lines[i]!.includes('|'))rows.push(cells(lines[i++]!));out.push({kind:'table',rows});continue}
    const item=list.exec(line)
    if(item){const items:string[]=[];const ordered=!!item[1],start=Number(item[1]||1);while(i<lines.length){const match=list.exec(lines[i]!);if(!match||!!match[1]!==ordered)break;items.push(match[2]!);i++}out.push({kind:'list',items,ordered,start});continue}
    if(/^\s*>/.test(line)){const body:string[]=[];while(i<lines.length&&/^\s*>/.test(lines[i]!))body.push(lines[i++]!.replace(/^\s*>\s?/,''));out.push({kind:'quote',text:body.join('\n')});continue}
    if(/^\s*(?:[-*_]\s*){3,}$/.test(line)){out.push({kind:'rule'});i++;continue}
    const body=[line];i++;while(i<lines.length&&lines[i]!.trim()&&!special(i))body.push(lines[i++]!);out.push({kind:'paragraph',text:body.join('\n')})
  }
  return out
})
function inline(value:string):ReturnType<typeof h>[] {
  const parts:ReturnType<typeof h>[]=[]
  const pattern=/(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[[^\]\n]+\]\([^\s)]+\))/g
  let offset=0
  for(const match of value.matchAll(pattern)){
    if(match.index!>offset)parts.push(createTextVNode(value.slice(offset,match.index)))
    const text=match[0]
    if(text.startsWith('`'))parts.push(h('code',text.slice(1,-1)))
    else if(text.startsWith('**'))parts.push(h('strong',inline(text.slice(2,-2))))
    else if(text.startsWith('*'))parts.push(h('em',inline(text.slice(1,-1))))
    else {const link=/^\[([^\]]+)\]\(([^)]+)\)$/.exec(text)!;const url=link[2]!
      const safe=/^(https?:\/\/|mailto:|#|\/(?!\/)|\.\.?\/)/i.test(url)&&!/[\u0000-\u0020\\]/.test(url)
      parts.push(safe?h('a',{href:url,rel:'noopener noreferrer'},link[1]):createTextVNode(text))}
    offset=match.index!+text.length
  }
  if(offset<value.length)parts.push(createTextVNode(value.slice(offset)))
  return parts
}
const InlineText=defineComponent({props:{value:{type:String,default:''}},setup:p=>()=>h(Fragment,inline(p.value))})
</script>
<template>
  <article class="document">
    <template v-for="(block,i) in blocks" :key="i">
      <pre v-if="block.kind==='code'"><code>{{block.text}}</code></pre>
      <component :is="'h'+Math.max(2,block.level||2)" v-else-if="block.kind==='heading'"><InlineText :value="block.text"/></component>
      <div v-else-if="block.kind==='table'" class="document-table"><table><thead><tr><th v-for="(cell,c) in block.rows![0]" :key="c" scope="col"><InlineText :value="cell"/></th></tr></thead><tbody><tr v-for="(row,r) in block.rows!.slice(1)" :key="r"><td v-for="(cell,c) in row" :key="c" :data-label="block.rows![0]![c]||''"><InlineText :value="cell"/></td></tr></tbody></table></div>
      <component v-else-if="block.kind==='list'" :is="block.ordered?'ol':'ul'" :start="block.ordered?block.start:undefined"><li v-for="(item,j) in block.items" :key="j"><InlineText :value="item"/></li></component>
      <blockquote v-else-if="block.kind==='quote'"><InlineText :value="block.text"/></blockquote>
      <hr v-else-if="block.kind==='rule'"/>
      <p v-else><InlineText :value="block.text"/></p>
    </template>
  </article>
</template>
<style scoped>
.document{min-width:0;overflow-wrap:anywhere;line-height:1.85;color:var(--fg);padding:12px 0}.document>:first-child{margin-top:0}.document>:last-child{margin-bottom:0}.document h2{font-size:20px;line-height:1.5;margin:28px 0 12px}.document h3{font-size:17px;margin:24px 0 10px}.document h4,.document h5,.document h6{font-size:15px;margin:20px 0 8px}.document p{margin:12px 0;white-space:pre-line}.document ul,.document ol{padding-left:25px;margin:14px 0}.document li{padding-left:3px;margin:6px 0}.document pre{max-width:100%;overflow:auto;background:var(--bg);padding:16px;border:1px solid var(--line);border-radius:8px;white-space:pre-wrap;font:13px/1.8 ui-monospace,monospace}.document :deep(code){font-size:.92em;background:var(--bg);padding:2px 5px;border-radius:4px}.document pre code{background:none;padding:0}.document blockquote{margin:18px 0;border-left:3px solid var(--accent);padding:10px 16px;background:var(--accent-soft);white-space:pre-line}.document hr{border:0;border-top:1px solid var(--line);margin:24px 0}.document-table{margin:18px 0;border:1px solid var(--line);border-radius:8px;overflow:hidden}.document table{border-collapse:collapse;width:100%;table-layout:fixed}.document th,.document td{text-align:left;vertical-align:top;padding:12px 14px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.document th{background:var(--bg);font-weight:600}.document tr:last-child td{border-bottom:0}.document th:first-child{width:24%}.document td+td,.document th+th{border-left:1px solid var(--line)}
@media(max-width:640px){.document thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}.document table,.document tbody,.document tr,.document td{display:block;width:100%}.document tr+tr{border-top:1px solid var(--line)}.document td,.document td+td{border:0;padding:10px 14px}.document td::before{content:attr(data-label);display:block;font-size:12px;color:var(--sub);font-weight:600;margin-bottom:3px}.document h2{font-size:19px}}
</style>
