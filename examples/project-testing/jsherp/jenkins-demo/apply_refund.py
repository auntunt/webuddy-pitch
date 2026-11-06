"""Apply the explicit demo policy to the independently cloned ERP only."""
from pathlib import Path
import sys
root = Path(sys.argv[1]).resolve()
assets = Path(__file__).resolve().parent
service = root / 'jshERP-boot/src/main/java/com/jsh/erp/service/DepotHeadService.java'
s = service.read_text()
needle = 'DepotHead depotHead = JSONObject.parseObject(beanJson, DepotHead.class);'
assert s.count(needle) == 2, 'Expected the add and update entry points'
assert 'RefundReason.validate' not in s, 'Already applied'
s = s.replace(needle, needle + '\n        com.jsh.erp.utils.RefundReason.validate(depotHead);')
service.write_text(s)
(root / 'jshERP-boot/src/main/java/com/jsh/erp/utils/RefundReason.java').write_bytes((assets / 'overlay/RefundReason.java').read_bytes())
(root / 'jshERP-boot/src/test/java/com/jsh/erp/verification/RefundReasonTest.java').write_bytes((assets / 'overlay/RefundReasonTest.java').read_bytes())
view = root / 'jshERP-web/src/views/bill/modules/SaleBackModal.vue'
s = view.read_bytes().decode()
old = '''<a-textarea :rows="1" placeholder="请输入备注" v-decorator="[ 'remark' ]" style="margin-top:8px;"/>'''
new = '''<a-textarea :rows="2" placeholder="退款说明（发生退款时填写5至200个字符）" aria-label="退款说明"
                v-decorator="['remark', {rules: [{validator: (rule, value, callback) => {
                  const amount = Number(form.getFieldValue('changeAmount') || 0)
                  const length = Array.from((value || '').trim()).length
                  callback(amount !== 0 && (length &lt; 5 || length &gt; 200) ? '退款说明须为5至200个字符，不能只填空白' : undefined)
                }}]}]" style="margin-top:8px;"/>'''
assert s.count(old) == 1
view.write_bytes(s.replace(old, new.replace('\n','\r\n')).encode())
print('Applied demo refund policy; review and commit the ERP candidate before building.')
