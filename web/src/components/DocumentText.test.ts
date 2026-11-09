import {expect,it} from 'vitest'
import {mount} from '@vue/test-utils'
import DocumentText from './DocumentText.vue'
it('renders a complete readable delivery with table, lists, code and source link',()=>{
 const text='# 改造方案\n\n**结论**：先核对已有适配。\n\n| 步骤 | 产出 |\n| --- | --- |\n| 1. 架构识别 | 模块、ORM、SQL位置 |\n| 2. 静态扫描 | `IFNULL` 与 `a|b` |\n\n1. 检查达梦配置\n2. 汇报范围\n\n> 未执行连库验证\n\n```sql\nselect * from sys_user;\n```\n[仓库](https://github.com/jeecgboot/JeecgBoot)'
 const w=mount(DocumentText,{props:{text}})
 expect(w.findAll('tbody tr')).toHaveLength(2)
 expect(w.findAll('tbody tr')[1]!.findAll('td')).toHaveLength(2)
 expect(w.get('strong').text()).toBe('结论')
 expect(w.findAll('ol li')).toHaveLength(2)
 expect(w.get('blockquote').text()).toBe('未执行连库验证')
 expect(w.get('pre').text()).toBe('select * from sys_user;')
 expect(w.get('a').attributes('href')).toBe('https://github.com/jeecgboot/JeecgBoot')
})
it('keeps model HTML inert and does not activate unsafe links',()=>{
 const w=mount(DocumentText,{props:{text:'<img src=x onerror=alert(1)>\n\n[不安全](javascript:alert)\n\n[站点](//evil.example)'}})
 expect(w.find('img').exists()).toBe(false)
 expect(w.find('a').exists()).toBe(false)
 expect(w.text()).toContain('<img src=x onerror=alert(1)>')
})
