# 原生报告发布与本人引用的保护快照

修复a98独立审查两个P2：NATIVE-BC-CURRENT-COMMIT-01（别名NATIVE-BC-CURRENT-01）与NATIVE-BC-DECISION-FRONTIER-01（别名NATIVE-DECISION-SNAPSHOT-01）。前者在最终观测后实际退役被选中的知识仍能commit passed；后者在报告read后、个人快照前实际新增原root预留仍返回reference_verified。qualified=false不能抵消这些来源当前性错误。

## 发布点

全原件/SP核验与独立评估仍在事务外完成。最后发布沿原 Registry → Store/SQLite写事务 → lesson ledger 获取保护；在持有同一保护时重新核原registration/contract、完整attempt指纹、blocked、原稳定预封绑定及实际capture/lesson/当前授权来源。这里复用已持有事务内的原Ledger._pool读取校验，不能调用会新开事务的snapshot/inspect/reconcile。

保护lease必须覆盖真正SQLite commit，而非只覆盖_event。内部publication context只显式提交自己刚创建的learning.transaction，并在lesson锁仍持有时commit；外层learning.transaction结束时再次commit为空操作。不得把lesson锁移到SQLite写事务之前，这会与原采用事务的SQLite→lesson顺序冲突。任何验证或事件失败仍回滚当前事务，原evaluation_intent与已执行SP原件保留，不自动重跑。

此保护覆盖遵循原Store/ledger锁的正常变更，不承诺任意绕过锁的管理员磁盘改写也可原子化。报告提交后发生新变更可以使报告失效；不能把某一成功发布点说成永远有效。

## 本人引用点

最初read()取得并核完整原件的报告，随后在原Registry→Store→lesson及SQLite一致读快照内，将其完整frontier和当前原输入/知识再核一次，再读取确切本人决定/修订/原job。报告read与本人决定不能来自两个不相容的根状态。快照期间的验证为纯读取，不改attempt、预算、业务状态或人的决定，不把普通job变成native来源。

新增原交错回归仅执行已存在采用之后的late-reserve，与独立复现一致。更强的pending→applied交错在独立审查中没有实际执行，本批也不执行/声称该强场景已证。额外独立OS进程尝试真实lesson锁，在实际SQLite报告commit时必须仍被阻挡；不是仅检查RLock或argv。

本修不解除旧100M合同或改D门。新的总Token上限人类豁免将由独立前瞻合同处理，旧根/失败/暴露集合保持；有限计划/取消/超时/原00:30窗口与真人采用约束不变。真实PPT材料已给出，不再以未提供材料或另找原生API保证100M作为理由；LIVE D/原生job桥未完成仍按实披露。
