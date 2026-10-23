# 组织工作台与交接 UI 浏览器验证

日期：2026-10-23。最终代码由主代理提交为 `911e42d`；本记录不修改仓库。

## 环境与边界

- Chrome，通过 CUA 的真实浏览器操作；独立回环地址 `http://127.0.0.1:60032`。
- 合成账号 alice / bob / charlie，合成项目 ORG、OTHER；仅 ORG-1 / ORG-2 临时任务。
- 临时数据目录：`/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/webuddy-handoff-ui-h9jfbgmt`。
- 未访问生产业务数据；未启动 8791/8793；未调用模型；未进行验收、关单或候选决策。
- 所有截图为浏览器截图 API 返回的原始 JPEG 字节，未缩放像素、转码或压缩。image-integrity.json 记录原始尺寸、字节数及 SHA-256。截图已通过 view_image 亲自打开确认。

## 实际浏览器操作与结果

1. alice 登录，打开 ORG-1，选择 bob、测试阶段，填写完整说明和材料。刷新队列及详情后，说明和材料保持不变。
2. alice 发送交接，列表与详情显示下一责任人 bob、测试阶段和基于发送事件的实际等待；任务负责人仍为 alice。
3. 发现成功后空表单绑定旧 revision 的问题，保存原始失败截图/DOM；修复并添加真实 revision 增长回归。重启服务保留合成数据，重新加载新版本后验证。
4. alice 撤回，下一责任人回到 alice，当前不在等待；再发送给 bob，成功后自动选择当前允许动作，绑定版本正确。
5. bob 登录后“待我接手”真实为 1；打开任务，填写阻塞原因并登记阻塞，列表/详情显示完整原因、下一责任人和实际等待。
6. 390×844 视口验证：body.scrollWidth、document.scrollWidth 均为 390，没有横向溢出；责任人和完整阻塞原因保留。
7. bob 恢复阻塞，核对并重绑保留的接收草稿后接收材料。待我接手降为 0，空态明确不代表完成；当前不在等待，技术未启动、人工未请求、工单状态 new。
8. bob 将材料交给 charlie，明确目标为交付阶段。charlie 登录后待我接手为 1、交付阶段计数为 1。
9. charlie 填写完整原因并退回。下一责任人回到 bob；charlie 待我接手为 0；任务负责人仍 alice、复核人仍 charlie、工单状态仍 new。
10. 最终版本将最近处理说明直接显示，退回原因无需展开历史即可查看；完整历史仍保留。重启服务保留同一合成数据，重新加载最终代码并截图。
11. 最终 390px 详情显示完整责任人和退回原因；合成需求中的 script 文本被转义，需求容器实际 script 元素数为 0；浏览器 warning/error 日志为空。

## 回归与保留证据

- `python3 -m unittest discover -s tests -p test_ui_handoffs.py`：21 项通过。
- `git diff --check`：通过。
- 其他此前定向测试：test_ui_memory.py 15 项、test_ui_library.py 25 项、test_ui_learning.py 22 项通过。
- 最终全量由主代理对精确提交独立执行，本记录不将定向测试等同全量。
- before-fix-success-old-binding.jpg / before-fix-dom.txt：保留真实浏览器发现的旧版本时序错误。
- synthetic-db-proof.json：只读合成库证据；3 次交接、8 个动作事件（send、withdraw、send、block、resume、receive、send、return），最终状态 returned。两任务均 new 且负责人 alice；候选决策数量为 0。
- source-sha256.json：4 个 UI / 测试文件内容摘要。

## 建议审阅截图

- final-desktop-viewport.jpg：桌面工作台总览。
- final-desktop-detail.jpg：桌面责任人、完整退回原因及需求。
- final-mobile-390-reason.jpg：390px 责任人、完整退回原因及人工/技术状态。
- final-desktop-full.jpg / final-mobile-390-full.jpg：原始完整页面截图。
- desktop-blocked-full.jpg / mobile-390-blocked-full.jpg：真实阻塞阶段。

## 资源清理

- 关闭本次创建的 Chrome 页签 210946577；确认页签列表中已不存在。其他用户页签未关闭。
- 视口覆盖已恢复默认桌面尺寸后关闭页签。
- 结束本次临时服务 PID 16950；`lsof -nP -iTCP:60032 -sTCP:LISTEN` 无监听结果（exit 1）。
- 保留合成临时数据及外部证据用于复核，不删除或改动业务数据。

## 实际覆盖界限

浏览器完成测试材料接收、阻塞/恢复、交付材料退回和发送方撤回；未知网络结果、冲突重绑、并发切换旧响应抑制及成员失效等由真实 shipped JavaScript 的 Node 回归覆盖。本轮不声称浏览器实际注入了断网或服务器崩溃，也不将交接接收视为业务验收。
