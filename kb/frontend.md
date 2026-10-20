# 前端与浏览器适配

信创终端的浏览器（奇安信、360 信创版、红莲花等）基本是 Chromium 内核，部分保留“IE 兼容模式”插件但不应依赖。

## 常见问题与处理

| 问题 | 识别 | 处理 |
|---|---|---|
| ActiveX/OCX 控件（打印 LODOP、读卡器、电子签章、Office 在线编辑、扫描仪） | `classid="clsid:..."`、`new ActiveXObject` | 找控件厂商的信创版本，通常是“本地服务 + WebSocket/HTTP”方式；要求目标操作系统与 CPU 上有客户端安装包 |
| IE 条件注释、`document.all`、`attachEvent`、`showModalDialog` | 规则 `FE-IE-001` | 改标准 DOM API；`showModalDialog` 改为 Promise 风格的模态框 |
| VBScript | `<script language="vbscript">` | 重写为 JavaScript |
| 老版本 jQuery/Bootstrap 插件 | 依赖清单 | 升级或保留，验证在 Chromium 下的表现 |
| 字体 | CSS `font-family: 宋体/微软雅黑` | 增加系统中文字体的回退 |
| 文件下载与打印 | 依赖 IE 特性 | 用标准下载、`window.print` 或 PDF |

## 验证

- 在目标信创终端（或同内核浏览器）上做冒烟，重点是登录、打印、导出、上传、控件调用。
- 截图对比关键页面；表单校验与日期控件常有差异。
