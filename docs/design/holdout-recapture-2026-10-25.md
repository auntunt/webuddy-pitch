# NATIVE-HOLDOUT-RECAPTURE-01：完整记录摘要不等于题目身份

独立579审查复现：只修改完整history中已不进入生产最后六条窗口的一条历史，重新调用原capture和Catalog.admit，工单与实际41642字节prompt相同而包装SHA不同；原训练族propose接受并产生一次合成HTTP。本问题是预封题目进入A，不是权限/预算绕过。别名REGISTERED-HOLDOUT-01是同一缺陷。qualified=false不能修复题目已经暴露。

## 最小加严

保留完整capture/history、原根、预封原文与原SHA集合。TokenBroker从私有Catalog中按原根预封rawSHA定位原始capture，绑定三种证据：租户/项目/实际工单ID的稳定身份；真正交给模型的完整messages摘要（不含允许变化的策略）；原binding/project/ticket来源摘要。包装记录中的非有效历史、池统计或其他元数据变化都不能替换这份原题目身份。

propose/judge/probe/retry在任何新登记/预留/HTTP之前检查：同一原预封任务，或完整有效模型输入相同，即拒绝训练。有效history改变仍不能把同一个预封工单改名为训练任务。合法不同训练工单、新历史以及不同的无工单训练资料仍允许；B/C预封输入必须有真实稳定工单身份。此门约束原生私有登记Broker，不声称阻止任意开发者绕过该Broker直接构造其他底层API调用。

首次成功计划与registered_plan/input/arm同事务追加唯一registered_sealed_inputs锚，早于第一次provider attempt。后续派发/guard复查原capture与锚；缺失、改动、重复或根不符拒绝。已有attempt却无原锚的旧/损坏根不能补签、重封集合或宣称未见；原历史/预算/暴露记录保留，应由真人另作调查处置。新的原生根也不因该拒绝自动获得第二份授权预算。

初次定位只枚举本私有catalog的input ID，读原目录FD/nofollow/owner-only文件并核原rawSHA，不遍历项目仓库或data。相同原capture的额外ID不改变已冻结的ID/身份。原题目找不到时拒绝，不能用新包装取代；从未尝试的根恢复确切原字节后可以重新验证。已存在原锚后只读锚中的原ID，不因新增别名重新选集合。

## 验证边界

新回归使用真实capture，不伪造输入或删减history，明确核原始与重捕获的完整有效输入相等、rawSHA不同、新attempt/HTTP为零。原失败现场保留实际1次HTTP/SP及完整输入；修后针对全部四训练阶段、变化后的有效history、合法不同训练任务/历史、无工单资料、旧根缺锚、原件缺失/恢复分别验证。guard/acceptance/原锁/MOVES及旧测试不变。真实模型调用0、LIVE D仍关闭，不把该修复或语义报告第一段宣称完整RSI/组织收益。
