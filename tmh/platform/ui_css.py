"""Styles for the platform UI. Light only on purpose: the closed-loop workbench is a white page under a navy bar."""

CSS = r"""
:root{--navy:#1D2939;--navy-rf:#2A2550;--navy2:#26334A;--navy3:#33415A;--bg:#F2F4F7;--panel:#FFFFFF;--fg:#1F2733;--mut:#667085;--line:#E4E7EC;--soft:#F5F7FA;
--blue:#1677FF;--acc2:#69B1FF;--acc:#1677FF;--blue-s:#E8F1FF;--ok:#2BA471;--ok-s:#E6F6EE;--bad:#E5484D;--bad-s:#FDECEC;--warn:#D98E04;--warn-s:#FFF5DF;--pur:#8E56E8;--pur-s:#F2EBFD;--code:#F4F6F9;
--s-new:#7D8BA1;--s-analyzing:#1677FF;--s-confirm:#8E56E8;--s-doing:#13A3A3;--s-verify:#E2589B;--s-closed:#2BA471;color-scheme:light}
*{box-sizing:border-box}html,body{height:100%}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 -apple-system,"PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
#top{height:56px;background:var(--navy);color:#fff;display:flex;align-items:center;gap:14px;padding:0 20px;position:sticky;top:0;z-index:6}
#top .brand{display:flex;align-items:center;gap:10px;font-size:18px;font-weight:700;letter-spacing:.5px;white-space:nowrap}
#top .brand svg{flex:none}
#projSel{background:var(--navy3);color:#fff;border:1px solid #46546E;border-radius:6px;padding:4px 8px;max-width:240px}
#top .sp{flex:1}
#svc{display:flex;gap:2px;padding:3px;border-radius:7px;background:rgba(255,255,255,.08);flex:none}
#svc a{color:#C9D1DC;padding:4px 12px;border-radius:5px;font-size:13px;white-space:nowrap}#svc a:hover{text-decoration:none;color:#fff}
#svc a.on{background:#fff;color:var(--navy);font-weight:600}
body.svc-reform #top{background:var(--navy-rf)}body.svc-reform #svc a.on{color:var(--navy-rf)}
#tabs .tsep{margin-left:auto;align-self:center;font-size:12px;color:var(--mut);padding-left:16px;border-left:1px solid var(--line);white-space:nowrap}
.pts{display:flex;align-items:center;gap:6px;background:var(--navy3);border:1px solid #46546E;border-radius:999px;padding:3px 12px 3px 8px;font-size:13px;cursor:pointer;white-space:nowrap}
.pts b{font-variant-numeric:tabular-nums;font-size:14px}.pts .dot{width:8px;height:8px;border-radius:50%;background:#FFC53D}
#top button{background:transparent;color:#fff;border:1px solid #46546E}#top button:hover{border-color:#8592A3}
#top button.primary{background:var(--blue);border-color:var(--blue)}
#top .me{font-size:12px;color:#AEB7C4;cursor:pointer;white-space:nowrap}
#wrap{display:flex;align-items:flex-start;min-height:calc(100% - 56px)}
#page{flex:1;min-width:0;padding:18px 22px 60px}
.sheet{background:var(--panel);border-radius:12px;box-shadow:0 1px 2px rgba(16,24,40,.05);padding:0 22px 22px}
#tabs{display:flex;gap:26px;border-bottom:1px solid var(--line);margin:0 0 18px;overflow-x:auto}
#tabs a{padding:16px 0 12px;color:var(--fg);border-bottom:2px solid transparent;white-space:nowrap}
#tabs a:hover{text-decoration:none;color:var(--blue)}#tabs a.on{color:var(--blue);border-bottom-color:var(--blue);font-weight:600}
#tabs{overflow:visible}.tmore{position:relative}.tmore>summary{list-style:none;cursor:pointer;padding:16px 0 12px;border-bottom:2px solid transparent;white-space:nowrap;color:var(--fg)}
.tmore>summary::-webkit-details-marker{display:none}.tmore>summary i{font-style:normal;font-size:11px;margin-left:4px;color:var(--mut)}
.tmore>summary:hover,.tmore.on>summary{color:var(--blue)}.tmore.on>summary{border-bottom-color:var(--blue);font-weight:600}
.tmp{position:absolute;top:100%;left:-12px;z-index:30;background:#fff;border:1px solid var(--line);border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.12);padding:8px 0;min-width:180px;display:flex;flex-direction:column}
.tmg{display:flex;flex-direction:column;padding:4px 0}.tmg+.tmg{border-top:1px solid var(--line)}.tmg span{font-size:12px;color:var(--mut);padding:4px 16px}
#tabs .tmp a{padding:8px 16px;border:0}#tabs .tmp a:hover{background:var(--soft)}#tabs .tmp a.on{border:0;background:var(--soft)}
.tmore>summary b{font-weight:inherit;display:inline-block;vertical-align:bottom;overflow:hidden;text-overflow:ellipsis}
@media (max-width:700px){#tabs{gap:12px}.tmp{left:auto;right:-8px}.tmore>summary b{max-width:3em}}
#ast{width:384px;flex:none;position:sticky;top:56px;height:calc(100vh - 56px);background:var(--panel);border-left:1px solid var(--line);display:flex;flex-direction:column}
@media (max-width:1100px){#ast{position:fixed;right:0;top:56px;z-index:7;box-shadow:-8px 0 30px rgba(16,24,40,.15)}}
@media (max-width:700px){#ast{width:100%}#top{gap:8px;padding:0 10px}#top .me,#newBtn span,#astToggle,.pts .w{display:none}#projSel{max-width:96px}#svc a{padding:4px 8px}#svc a span{display:none}#top .brand{font-size:15px}#page{padding:12px 10px 40px}.sheet{padding:0 12px 14px}}
@media (max-width:480px){#brandName{display:none}#projSel{max-width:84px}.pts{display:none!important}#top .brand svg{display:none}}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:0 0 10px}h3{font-size:14px;margin:0 0 8px}
.sub{color:var(--mut);font-size:13px}
.row{display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap}.row>*{min-width:0}.grow{flex:1}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
.grid2{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:16px}
.grid4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
@media (max-width:1000px){.grid4{grid-template-columns:repeat(2,minmax(0,1fr))}.grid2{grid-template-columns:minmax(0,1fr)}}
.kpi .n{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums}.kpi .l{color:var(--mut);font-size:13px}
.hdr{display:flex;align-items:center;gap:12px;margin:0 0 14px;flex-wrap:wrap}
button,select,input,textarea{font:inherit;color:inherit}
button{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:5px 12px;cursor:pointer}
button:hover{border-color:var(--blue);color:var(--blue)}button:disabled{opacity:.5;cursor:default}
button.primary{background:var(--blue);border-color:var(--blue);color:#fff}button.primary:hover{filter:brightness(1.08);color:#fff}
button.ghost{border-color:transparent;background:transparent}
button.danger{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 45%,var(--line))}button.danger:hover{color:var(--bad);border-color:var(--bad)}
button.okb{background:var(--ok);border-color:var(--ok);color:#fff}
select,input,textarea{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:5px 8px}
textarea{width:100%;min-height:90px;resize:vertical}input.full{width:100%}
table.t{width:100%;border-collapse:collapse;background:var(--panel)}
.t th{font-weight:600;color:var(--mut);font-size:12px;text-align:left;background:var(--soft);padding:9px 10px}
.t td{padding:9px 10px;border-top:1px solid var(--line);vertical-align:top}
.t tr.click:hover td{background:#F7FAFF;cursor:pointer}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:10px}
.key{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:var(--mut);white-space:nowrap}
.pill{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;white-space:nowrap;color:#fff}
.tag{display:inline-block;padding:0 7px;border-radius:4px;font-size:12px;background:var(--soft);color:var(--mut);white-space:nowrap;border:1px solid var(--line)}
.ev-tag{display:inline-flex;align-items:center;gap:4px;padding:1px 8px;border-radius:4px;font-size:12.5px;border:1px solid;white-space:nowrap}
.ev-tag.ok{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 45%,#fff);background:var(--ok-s)}
.ev-tag.bad{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 40%,#fff);background:var(--bad-s)}
.ev-tag.warn{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 45%,#fff);background:var(--warn-s)}
.ev-tag.info{color:var(--blue);border-color:color-mix(in srgb,var(--blue) 35%,#fff);background:var(--blue-s)}
.ev-tag.mute{color:var(--mut);border-color:var(--line);background:var(--soft)}
.pri-urgent{color:var(--bad);font-weight:700}.pri-high{color:#D4380D}.pri-low{color:var(--mut)}
/* KPI band */
.band{background:linear-gradient(135deg,var(--navy2),#2D3B55);color:#fff;border-radius:12px;padding:18px 22px}
.gauges{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
@media (max-width:900px){.gauges{grid-template-columns:repeat(2,minmax(0,1fr))}}
.gauge{display:flex;align-items:center;gap:12px;min-width:0}.gauge svg{flex:none}
.gauge .gl{font-size:14px;font-weight:600}.gauge .gs{font-size:12px;color:#AEB7C4}
.caps{display:flex;gap:26px;flex-wrap:wrap;margin-top:16px;align-items:center}
.cap{display:flex;align-items:center;gap:10px;cursor:pointer}.cap .ic{width:40px;height:40px;border-radius:9px;display:grid;place-items:center}
.cap b{font-size:22px;font-variant-numeric:tabular-nums;line-height:1.1;display:block}.cap span{font-size:12px;color:#C9D1DC}
.cap:hover b{text-decoration:underline}
.today{font-size:13px;color:#C9D1DC;margin-left:auto}
.insight{border-top:1px solid #3B4A63;margin-top:16px;padding-top:12px;font-size:13px;color:#E3E8EF;display:flex;gap:8px;align-items:center}
.insight b{color:#5CDBD3;font-weight:600;white-space:nowrap}
.viewbar{display:flex;align-items:center;gap:10px;margin:16px 0 6px;flex-wrap:wrap}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.seg button{border:0;border-radius:0;border-right:1px solid var(--line);background:var(--panel);color:var(--fg)}.seg button:last-child{border-right:0}
.seg button.on{background:var(--blue-s);color:var(--blue);font-weight:600}
.ringwrap{display:flex;justify-content:center;overflow-x:auto}
.ring{width:600px;max-width:100%;height:auto}
.ring .node{cursor:pointer}.ring .node:hover .halo{opacity:.35}
.ring .badge{cursor:pointer}
.ring text{font-family:inherit}
.ring .nl{font-size:13px;font-weight:600;fill:var(--fg)}.ring .nr{font-size:11px}
.ringhint{text-align:center;color:var(--mut);font-size:12px;margin-top:4px}
.board{display:grid;grid-template-columns:repeat(6,minmax(180px,1fr));gap:12px;overflow-x:auto;padding-bottom:8px}
.col{background:var(--soft);border-radius:10px;padding:10px;min-height:300px}
.col h3{display:flex;justify-content:space-between;align-items:center}
.col.over{outline:2px dashed var(--blue)}
.tc{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:9px 10px;margin:0 0 8px;cursor:grab}
.tc:hover{border-color:var(--blue)}.tc .tt{margin:2px 0 6px}
.meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:12px;color:var(--mut)}
/* ticket detail */
.detail{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:16px}
@media (max-width:1300px){.detail{grid-template-columns:1fr}}
.blk{border-radius:10px;padding:14px 16px;border:1px solid var(--line);background:var(--panel)}
.blk.src{background:#F7F9FC}.blk.cov{background:#FBF8FF;border-color:#ECE3FB}.blk.qa{background:#F6F9FF;border-color:#DFE9FB}.blk.mr{background:#F6FCF8;border-color:#DCF0E4}
.blk h3{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.blk h3 .num{color:var(--ok);font-size:15px}
.tags{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.fields{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px 14px}
.fields label{display:block;color:var(--mut);font-size:12px;margin-bottom:2px}.fields select,.fields input{width:100%}
.md{line-height:1.7;overflow-wrap:anywhere}.md h1,.md h2,.md h3,.md h4{margin:12px 0 6px}.md h1{font-size:17px}.md h2{font-size:15.5px}.md h3{font-size:14.5px}
.md p{margin:6px 0}.md ul,.md ol{margin:4px 0;padding-left:22px}.md code{background:var(--code);padding:0 4px;border-radius:3px;font-size:12.5px}
.md pre{background:var(--code);padding:10px;border-radius:6px;overflow:auto}.md pre code{background:none;padding:0}
.md table{border-collapse:collapse;margin:8px 0;display:block;overflow-x:auto}.md td,.md th{border:1px solid var(--line);padding:4px 8px}
.md blockquote{margin:6px 0;padding:2px 12px;border-left:3px solid var(--line);color:var(--mut)}
pre.log{background:#0F141A;color:#C9D3DE;padding:10px 12px;border-radius:8px;max-height:340px;overflow:auto;font:12px/1.5 ui-monospace,Menlo,Consolas,monospace;white-space:pre-wrap;margin:8px 0}
pre.diff{background:var(--code);padding:10px;border-radius:8px;max-height:480px;overflow:auto;font:12px/1.45 ui-monospace,Menlo,Consolas,monospace;margin:8px 0}
.diff .a{color:var(--ok)}.diff .d{color:var(--bad)}.diff .h{color:var(--blue);font-weight:600}
.tl{display:flex;flex-direction:column;gap:10px}
.ev{display:flex;gap:10px}.ev .dot{width:8px;height:8px;border-radius:50%;background:var(--line);margin-top:7px;flex:none}
.ev.comment .dot{background:var(--blue)}.ev.run-done .dot,.ev.accept .dot{background:var(--ok)}.ev.run-failed .dot,.ev.reject .dot{background:var(--bad)}
.ev .who{font-weight:600}.ev .when{color:var(--mut);font-size:12px;margin-left:6px}
.ev .cbody{background:var(--soft);border-radius:8px;padding:8px 10px;margin-top:4px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{border:1px solid var(--line);border-radius:6px;padding:4px 8px;font-size:12.5px;background:var(--panel);cursor:pointer;max-width:100%}
.chip:hover{border-color:var(--blue)}.chip.on{border-color:var(--blue);background:var(--blue-s)}.chip small{color:var(--mut)}
.flowrow{display:flex;justify-content:space-between;gap:8px;padding:7px 0;border-top:1px solid var(--line)}
.flowrow:first-child{border-top:0}.flowrow .fx{min-width:0;overflow-wrap:anywhere}.flowrow button{flex:none;white-space:nowrap}
#rel .key{white-space:normal;overflow-wrap:anywhere}
.svr{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0;font-size:13px}
.bar{height:8px;border-radius:4px;background:var(--blue)}
.bars .r{display:grid;grid-template-columns:120px 1fr 44px;gap:8px;align-items:center;font-size:13px;margin:3px 0}
.bars .r span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--mut)}
.bars .r span:last-child{text-align:right;font-variant-numeric:tabular-nums}
.stack{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--soft)}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--mut)}.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
#modal{position:fixed;inset:0;background:rgba(16,24,40,.45);display:flex;align-items:flex-start;justify-content:center;padding:6vh 16px;z-index:10;overflow:auto}
.mbox{background:var(--panel);border-radius:12px;padding:22px;width:min(760px,100%);position:relative;box-shadow:0 20px 60px rgba(0,0,0,.25)}
.mbox.wide{width:min(1100px,100%)}
.mx{position:absolute;right:12px;top:10px;border:0;background:none;font-size:22px;color:var(--mut)}
.form{display:flex;flex-direction:column;gap:10px}.form label{font-size:13px;color:var(--mut)}
#toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:var(--navy);color:#fff;padding:9px 16px;border-radius:8px;z-index:20;max-width:80vw}
.empty{color:var(--mut);padding:30px;text-align:center}
.spin{display:inline-block;width:10px;height:10px;border:2px solid var(--blue);border-right-color:transparent;border-radius:50%;animation:sp 1s linear infinite;vertical-align:-1px}
@keyframes sp{to{transform:rotate(360deg)}}
iframe.map{width:100%;height:calc(100vh - 190px);border:1px solid var(--line);border-radius:10px;background:#fff}
.hint{background:var(--blue-s);border:1px solid #C9DCFB;border-radius:8px;padding:10px 12px;font-size:13px}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:0 0 10px;flex-wrap:wrap}
.tabs button{border:0;border-bottom:2px solid transparent;border-radius:0;background:none;padding:6px 10px;color:var(--mut)}
.tabs button.on{border-bottom-color:var(--blue);color:var(--blue);font-weight:600}
svg text{fill:var(--mut);font-size:11px}
/* assistant */
.ah{padding:14px 16px 10px;border-bottom:1px solid var(--line)}
.ah .t{display:flex;align-items:center;gap:8px}.ah .t b{font-size:16px}.ah .t .grow{flex:1}
.ah .ctx{margin-top:8px;font-size:12.5px;color:var(--mut);display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.ah .ctx .tag{max-width:250px;overflow:hidden;text-overflow:ellipsis}
.ah .opts{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}
.ah select{padding:3px 6px;font-size:12.5px}.ah .seg button{padding:3px 10px;font-size:12.5px}
#amsg{flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:14px}
.m-u{align-self:flex-end;max-width:88%;background:#F0F3F8;border-radius:10px;padding:8px 12px;overflow-wrap:anywhere}
.m-a{display:flex;gap:9px;max-width:100%}.m-a .av{width:28px;height:28px;border-radius:50%;background:var(--navy);display:grid;place-items:center;flex:none}
.m-a .bd{min-width:0;flex:1}.m-a .md{font-size:13.5px}
.m-time{font-size:11.5px;color:var(--mut);margin-top:3px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.cite{display:flex;gap:8px;align-items:flex-start;border:1px solid var(--line);border-radius:8px;padding:7px 9px;margin-top:6px;background:#FAFBFD;cursor:pointer}
.cite:hover{border-color:var(--blue)}.cite .k{font-size:11px;padding:0 5px;border-radius:3px;background:var(--blue-s);color:var(--blue);flex:none;margin-top:2px}
.cite .k.tbl{background:var(--ok-s);color:var(--ok)}.cite .k.code{background:#EEF0F3;color:#4B5565}.cite .k.dom,.cite .k.index{background:var(--pur-s);color:var(--pur)}
.cite .key{overflow-wrap:anywhere;word-break:break-all}.cite .ct{min-width:0;flex:1;font-size:12.5px}.cite .ct b{font-weight:600;display:block;overflow-wrap:anywhere}.cite .ct span{color:var(--mut);overflow-wrap:anywhere}
.noev{display:inline-flex;gap:5px;align-items:center;color:var(--warn);background:var(--warn-s);border:1px solid #F5D9A0;border-radius:4px;padding:1px 8px;font-size:12px;margin-top:6px}
.cost{font-size:11.5px;background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:0 8px;color:var(--fg)}
.confirm{border:1px solid #C9DCFB;background:var(--blue-s);border-radius:10px;padding:10px 12px;font-size:13px}
.confirm .row{gap:8px;margin-top:8px}
.sugg{display:flex;gap:6px;flex-wrap:wrap;padding:0 16px 8px}
.sugg button{font-size:12.5px;padding:3px 9px;border-radius:999px;background:var(--soft)}
.ain{border-top:1px solid var(--line);padding:10px 12px 12px}
.ain .box{border:1px solid var(--line);border-radius:10px;padding:8px 10px;display:flex;gap:8px;align-items:flex-end}
.ain .box:focus-within{border-color:var(--blue)}
.ain textarea{border:0;min-height:40px;max-height:140px;padding:2px;resize:none;outline:none}
.ain .foot{font-size:11.5px;color:var(--mut);margin-top:6px;display:flex;justify-content:space-between;gap:8px}
#astOpen{position:fixed;right:18px;bottom:22px;z-index:6;border-radius:999px;padding:10px 16px;background:var(--navy);color:#fff;border:0;box-shadow:0 6px 20px rgba(16,24,40,.25)}

/* page header shared by the information pages */
.ph{display:flex;align-items:flex-end;gap:14px;margin:4px 0 18px;flex-wrap:wrap}.ph h1{font-size:26px;margin:2px 0 4px;letter-spacing:.5px}
.eyebrow{font-size:11.5px;letter-spacing:2px;color:var(--mut);text-transform:uppercase}
a.btn{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:5px 12px;color:var(--fg);background:var(--panel);white-space:nowrap}a.btn:hover{border-color:var(--blue);color:var(--blue);text-decoration:none}
.crumb{font-size:12.5px;color:var(--mut);letter-spacing:.5px}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin:0 0 18px}
.kpis>div{padding:16px 4px;display:flex;flex-direction:column;gap:2px}.kpis b{font-size:28px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.2}
.kpis span{font-size:12.5px;color:var(--fg)}.kpis small{font-size:11.5px;color:var(--mut)}
@media (max-width:700px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
.cnt{display:inline-block;min-width:18px;padding:0 5px;border-radius:9px;background:var(--warn);color:#fff;font-size:11px;font-weight:600;margin-left:2px}
.seg.kbt{margin-bottom:14px}.seg.kbt button{padding:7px 16px}
/* maintenance matters */
.card.mt{margin-bottom:14px}
.steps{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:10px;align-items:center;margin:14px 0}
.steps i{color:var(--mut);font-style:normal}.stp{border:1px solid var(--line);border-radius:8px;padding:12px 14px;display:flex;flex-direction:column;gap:2px;min-width:0}
.stp b{font-size:13.5px}.stp span{font-size:12.5px;color:var(--mut)}.stp.on{border-color:var(--blue);background:var(--blue-s)}.stp.on b{color:var(--blue)}.stp.done{background:var(--soft)}.stp.done b{color:var(--ok)}
@media (max-width:700px){.steps{grid-template-columns:1fr}.steps i{display:none}}
.slist{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;margin-top:10px;padding-top:10px;border-top:1px dashed var(--line);align-items:baseline}
.empty2{text-align:center;padding:36px 20px}.empty2 p{max-width:520px;margin:8px auto 14px}
/* knowledge reading */
.kbread{display:grid;grid-template-columns:260px minmax(0,1fr);gap:16px;align-items:start}
@media (max-width:900px){.kbread{grid-template-columns:1fr}.kbdir{max-height:260px}}
.kbdir{border:1px solid var(--line);border-radius:10px;padding:12px;position:sticky;top:70px;max-height:calc(100vh - 100px);overflow:auto;background:var(--panel)}
.kbdir input[type=text],.kbdir #kbq{width:100%;margin-bottom:6px}.chk{display:flex;gap:6px;align-items:center;margin:2px 0 8px;font-size:12.5px}
.kd summary{cursor:pointer;font-weight:600;padding:5px 2px;display:flex;gap:6px;align-items:center}.kd summary small{margin-left:auto;color:var(--mut);font-weight:400;font-variant-numeric:tabular-nums}
.kn{display:flex;align-items:center;gap:6px;padding:5px 8px 5px 14px;border-radius:6px;color:var(--fg);font-size:13px;border-left:2px solid var(--line);margin-left:6px}
.kn span{flex:1;min-width:0;overflow-wrap:anywhere}.kn:hover{background:var(--soft);text-decoration:none}.kn.on{background:var(--blue-s);color:var(--blue);border-left-color:var(--blue);font-weight:600}
.kn.dim{color:var(--mut)}.kn.top{font-weight:600;border-left:0;margin-left:0;padding-left:4px}.kn.dom{font-style:normal;color:var(--mut)}
.dot{width:7px;height:7px;border-radius:50%;flex:none;background:var(--line)}.dot.ok{background:var(--ok)}.dot.warn{background:var(--warn)}.dot.bad{background:var(--bad)}.dot.mute{background:#C5CBD3}
.kbdoc{min-width:0;padding:22px 26px}.kbdoc h1{font-size:24px}
.kbdoc .note{background:var(--soft);border-radius:8px;padding:9px 12px;font-size:12.5px;color:var(--mut);margin:6px 0 12px}
.kbdoc .lead{font-size:15px;margin:0 0 6px}.kbmd{max-width:72ch}.kbmd h2{font-size:16px;margin:18px 0 6px}
.fold{border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin:14px 0}.fold summary{cursor:pointer;font-weight:600}
.acts2{gap:8px;align-items:center;border-top:1px solid var(--line);padding-top:14px;margin-top:16px}
/* architecture */
.archwrap{overflow-x:auto}.arch{width:100%;min-width:720px;height:auto;display:block}
.arch .ab rect{fill:#F7F9FC;stroke:#C9D3E1;stroke-width:1.2}.arch .ab.d rect{fill:var(--blue-s);stroke:#9EC2F8}.arch .ab.t rect{fill:var(--ok-s);stroke:#9FD8BE}.arch .ab.x rect{fill:#fff;stroke:#C9D3E1;stroke-dasharray:4 3}
.arch a:hover rect{stroke:var(--blue);stroke-width:2}.arch .t1{font-size:15px;font-weight:600;fill:var(--fg)}.arch .t2{font-size:12px;fill:var(--mut)}
.arch .cap{font-size:12px;fill:var(--mut);letter-spacing:1px}.arch .ln{fill:none;stroke:#98A6BB;stroke-width:1.3}.arch .ln.dash{stroke-dasharray:5 4}
.rfbar{flex:1;display:flex;height:8px;border-radius:4px;background:var(--line);overflow:hidden}.rfbar i{display:block;height:100%;flex:none}.rfbar .ok{background:var(--ok)}.rfbar .vf{background:var(--s-verify)}.rfbar .rl{background:var(--blue);opacity:.45}
.rfp{margin-bottom:16px}.rfpz{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px;padding:8px 12px;border-radius:6px;border:1px solid color-mix(in srgb,var(--warn) 45%,#fff);background:var(--warn-s);color:var(--warn)}
.rfpz .grow{min-width:0;flex:1 1 240px}
.rfau{display:flex;gap:6px;align-items:center;white-space:nowrap;margin-left:auto}
.rflog{margin-top:10px;display:flex;flex-direction:column;gap:3px;font-size:13px;border-left:2px solid var(--line);padding-left:10px}
.rfk{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}@media (max-width:800px){.rfk{grid-template-columns:repeat(2,minmax(0,1fr))}}
.rfkb{display:flex;flex-direction:column;align-items:flex-start;gap:4px;text-align:left;padding:10px 12px;height:auto;white-space:normal}.rfkb span{font-size:12px;color:var(--mut);font-weight:400;line-height:1.5}.rfkb.on{border-color:var(--blue);box-shadow:0 0 0 1px var(--blue) inset}
.rfdl{max-height:260px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:4px 10px}.rfd{display:flex;gap:8px;align-items:center;padding:5px 0;border-bottom:1px solid var(--line)}.rfd:last-child{border:0}.rfd input{width:auto}
.drow{display:flex;gap:10px;align-items:center;padding:10px 0;border-top:1px solid var(--line);color:var(--fg)}.drow:first-of-type{border-top:0}.drow:hover{text-decoration:none}.drow:hover b{color:var(--blue)}
.drow .grow{display:flex;flex-direction:column;min-width:0}
.chk2{padding-left:18px;margin:6px 0 14px}.chk2 li{margin:6px 0}
/* runs */
.rl{padding:4px 20px}.ri{display:flex;gap:14px;align-items:flex-start;padding:16px 0;border-top:1px solid var(--line)}.ri:first-child{border-top:0}
.rt{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:2px}.rt b{font-size:15px}.ri .out{margin-top:6px;font-size:13px;overflow-wrap:anywhere}
.ra{display:flex;flex-direction:column;gap:6px;flex:none}.sub2{margin-top:6px}.sub2 summary{cursor:pointer;font-size:13px}
@media (max-width:700px){.ri{flex-direction:column}.ra{flex-direction:row}}
/* assistant sessions */
.ah .sess{display:flex;gap:10px;align-items:flex-start;background:var(--soft);border-radius:10px;padding:10px 12px;margin-top:10px}
.ah .lbl{font-size:11.5px;color:var(--mut)}.ah .nm{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chips2{display:flex;gap:5px;flex-wrap:wrap;margin-top:6px}.tag.on{background:var(--blue-s);color:var(--blue);border-color:#C9DCFB}.tag.warn{background:var(--warn-s);color:var(--warn);border-color:#F3D69B}
.hbtn{flex:none;font-size:12.5px;padding:3px 9px}.hbtn.on{border-color:var(--blue);color:var(--blue);background:var(--blue-s)}
.ah .acts{display:flex;gap:6px;align-items:center;margin-top:8px}.ah .acts button{font-size:12.5px;padding:3px 9px}
.nw{position:relative}.menu{position:absolute;left:0;top:calc(100% + 4px);z-index:9;background:var(--panel);border:1px solid var(--line);border-radius:10px;box-shadow:0 10px 30px rgba(16,24,40,.16);width:270px;padding:6px}
.menu button{display:flex;flex-direction:column;align-items:flex-start;width:100%;border:0;text-align:left;padding:7px 10px;border-radius:6px}.menu button:hover{background:var(--soft)}
.menu button span{font-size:11.5px;color:var(--mut)}.menu .mh{font-size:11.5px;color:var(--mut);padding:6px 10px 2px;border-top:1px solid var(--line);margin-top:4px}
.offer{margin-top:8px;border:1px solid #F3D69B;background:var(--warn-s);border-radius:8px;padding:8px 10px;font-size:12.5px}.offer .row{gap:6px;margin-top:6px}.offer button{font-size:12.5px;padding:3px 9px}
.hist input{width:100%;margin-bottom:6px}.hg{margin:4px 0}.hg summary{cursor:pointer;font-weight:600;font-size:13px;padding:4px 2px;display:flex;gap:6px;align-items:center}
.hg summary small{background:var(--soft);border-radius:8px;padding:0 6px;font-weight:400;color:var(--mut)}.hm{font-size:12px;color:var(--mut);padding:4px 10px 0}
.hrow{display:flex;gap:8px;align-items:center;width:100%;border:0;border-left:2px solid var(--line);border-radius:0 6px 6px 0;text-align:left;padding:6px 10px;margin-left:6px;width:calc(100% - 6px)}
.hrow .grow{display:flex;flex-direction:column;min-width:0}.hrow b{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hrow i{font-style:normal;font-size:11.5px;color:var(--mut)}.hrow small{color:var(--mut);white-space:nowrap;font-size:11.5px}
.hrow:hover{background:var(--soft);color:var(--fg)}.hrow.on{background:var(--blue-s);border-left-color:var(--blue)}.hrow.on b{color:var(--blue);font-weight:600}
.m-a .afol{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.m-a .afol button{font-size:12px;padding:3px 9px;border-radius:12px}.m-a .aact{margin-top:8px;gap:6px}
.m-a .sec{font-size:12px;font-weight:600;color:var(--mut);margin:10px 0 2px;letter-spacing:.5px}.m-a .nx{font-size:13px}
.more summary{cursor:pointer;font-size:12.5px;color:var(--blue);margin-top:6px}
.ain .box{flex-direction:column;align-items:stretch}.ain .abar{display:flex;align-items:center;gap:6px;border-top:1px solid var(--line);padding-top:6px}.ain .abar .ghost{font-size:12.5px;color:var(--mut);padding-left:2px}.ain textarea{width:100%;min-height:52px}.ain .foot span:last-child{white-space:nowrap}
#toast button{color:#fff;border-color:#8592A3;margin-left:8px;padding:2px 10px}
label.fl{display:flex;flex-direction:column;gap:4px;font-size:12.5px;color:var(--mut);margin-bottom:10px}label.fl input,label.fl select,label.fl textarea{color:var(--fg);font-size:14px}
.cite .ct{min-width:0}.cite .key{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ttabs{display:flex;gap:22px;border-bottom:1px solid var(--line);margin:-4px 0 14px}.ttabs a{padding:6px 0;color:var(--mut);border-bottom:2px solid transparent}
.ttabs a.on{color:var(--blue);border-bottom-color:var(--blue);font-weight:600}.ttabs a:hover{text-decoration:none;color:var(--blue)}
.pgrid{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:16px}@media (max-width:1300px){.pgrid{grid-template-columns:1fr}}
.ptx{width:100%;min-height:440px;font:12.5px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--code);white-space:pre-wrap;resize:vertical}
.grid5{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}@media (max-width:1200px){.grid5{grid-template-columns:repeat(2,minmax(0,1fr))}}
.kpi .l{display:flex;align-items:center;gap:6px}.kpi .n{margin:4px 0 2px}
.kpi.core .chg{margin-top:8px;font-size:13px}.kpi.core .up{color:var(--ok);font-weight:600}.kpi.core .down{color:var(--bad);font-weight:600}
@media (max-width:520px){.grid4{grid-template-columns:1fr 1fr;gap:8px}.kpi .n{font-size:22px}}
.facts{display:flex;flex-direction:column;gap:2px}.fact{display:flex;gap:8px;align-items:baseline;padding:7px 0;border-bottom:1px solid var(--line)}.fact:last-child{border:0}.fact b{font-size:18px;font-variant-numeric:tabular-nums}
.srow{display:flex;align-items:center;gap:10px;padding:5px 0;font-size:13px}.srow>span:first-child{width:118px;flex:none}
.sbar{flex:1;height:8px;background:var(--soft);border-radius:4px;overflow:hidden}.sbar i{display:block;height:100%;background:var(--blue);border-radius:4px}
.trend{width:100%;height:auto;max-height:200px}.trend .tb{fill:var(--blue);opacity:.85}.trend .tv{fill:var(--fg);font-size:12px;font-weight:600}
.trend .tl{fill:var(--fg);font-size:12px}.trend .ts{fill:var(--mut);font-size:11px}
.est .n{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums;margin:2px 0 4px}
#aiCard h2{white-space:nowrap}#aiCard select{max-width:100%}
/* AI assistant: one box for questions and page operations */
kbd{font:11px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;border:1px solid currentColor;border-radius:4px;padding:0 4px;opacity:.65;margin-left:4px;white-space:nowrap}
.ah .t kbd{color:var(--mut)}.ah .t .hbtn{font-size:12.5px}.ah .t .menu{left:auto;right:0}
.ah .sess{align-items:center}.ah .sact{display:flex;gap:2px;flex:none}.ah .sact button{font-size:12px;padding:2px 6px;color:var(--mut)}
.ah .ctx{margin-top:8px;font-size:12.5px;display:flex;gap:6px;align-items:baseline;flex-wrap:wrap;min-width:0}
.ah .ctx b{font-weight:600;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ah .ctx .lbl{flex:none}
.hgt{font-size:12px;font-weight:600;color:var(--mut);margin:6px 2px 4px}.jump{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:4px}
.jump .tag{max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-decoration:none}
.m-a .av.cmd{background:var(--blue);color:#fff;font-size:14px}
.cmdc{border:1px solid #C9DCFB;background:var(--blue-s);border-radius:10px;padding:9px 12px;font-size:13px}
.cmdc .row{gap:8px;margin-top:8px}.cmdc .m-time{margin-top:6px}
.csteps{list-style:none;margin:6px 0 0;padding:0;display:flex;flex-direction:column;gap:4px}
.csteps li{display:flex;gap:8px;align-items:baseline;color:var(--mut)}.csteps li .tx{flex:1;min-width:0;overflow-wrap:anywhere;color:var(--fg)}
.csteps li .op{flex:none;font-size:11.5px;border:1px solid var(--line);background:var(--panel);border-radius:4px;padding:0 5px}
.cmdc .chd{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.cmdc.done,.cmdc.undone,.cmdc.cancelled{background:var(--panel);border-color:var(--line)}
.cst{flex:none;font-size:12px;color:var(--mut);white-space:nowrap}.cst.ok{color:var(--ok)}.cst.bad{color:var(--bad)}.cst.run{color:var(--blue)}
.cst.wait{color:#fff;background:var(--warn);border-radius:4px;padding:0 6px}
.csd{margin-top:6px}.csd summary{cursor:pointer;font-size:12px;color:var(--mut)}
.csteps li.ok .op{background:var(--ok-s);border-color:var(--ok);color:var(--ok)}.csteps li.ok .tx{color:var(--mut)}
.csteps li.wait .op,.csteps li.run .op{background:var(--blue);border-color:var(--blue);color:#fff}
.tag.ok{background:var(--ok-s);color:var(--ok);border-color:var(--ok)}
/* dialogs leave the assistant usable, so it can fill a form and wait for the confirm next to it */
@media (min-width:1101px){body.ast-on #modal{right:384px}}
@media (max-width:1100px){body.ast-on #ast{z-index:11}}
.ai-hl{outline:2px solid var(--blue)!important;outline-offset:2px;box-shadow:0 0 0 6px var(--blue-s)!important;transition:outline-color .2s}
.t td.num,.t th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.lbar{display:flex;align-items:center;gap:8px}.lbar i{display:block;height:8px;border-radius:4px;background:var(--acc2);min-width:2px}.lbar span{font-variant-numeric:tabular-nums;font-size:12px;color:var(--mut)}
.fsteps{list-style:none;margin:6px 0 12px;padding:0;display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:0;counter-reset:f}
.fsteps li{position:relative;display:flex;flex-direction:column;align-items:center;text-align:center;gap:2px;padding:0 4px;min-width:0}
.fsteps li:before{content:'';position:absolute;top:13px;left:-50%;right:50%;height:2px;background:var(--line);z-index:0}.fsteps li:first-child:before{display:none}
.fsteps li.done:before,.fsteps li.cur:before,.fsteps li.bad:before{background:var(--ok)}
.fsteps .dot{position:relative;z-index:1;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;background:var(--panel);border:2px solid var(--line);color:var(--mut)}
.fsteps li.done .dot{background:var(--ok);border-color:var(--ok);color:#fff}.fsteps li.cur .dot{border-color:var(--acc);color:var(--acc);box-shadow:0 0 0 4px rgba(22,119,255,.12)}
.fsteps li.bad .dot{border-color:var(--bad);color:var(--bad)}.fsteps li.skip{opacity:.45}
.fsteps b{font-size:13px}.fsteps li.cur b{color:var(--acc)}.fsteps small{font-size:11px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.concl .c4{display:grid;grid-template-columns:44px minmax(0,1fr);gap:8px 12px;margin:0}
.concl .c4 dt{font-size:12.5px;color:var(--mut);padding-top:2px}.concl .c4 dd{margin:0;min-width:0;overflow-wrap:anywhere;line-height:1.6}
.concl .c4 dd.na{border-radius:6px;padding:2px 8px;margin-left:-8px;background:#F6F9FF}.concl .c4 dd.na.warn{background:#FFFBF0}.concl .c4 dd.na.ok{background:#F6FCF8}.concl .c4 dd.na.bad{background:#FFF6F6}
.concl .cact{margin:12px 0 0 56px}.concl .cbox{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}
@media (max-width:700px){.concl .cact{margin-left:0}}
.props{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;margin:-4px 0 12px;font-size:13px}
.props label{display:inline-flex;gap:4px;align-items:center;color:var(--mut);font-size:12.5px;margin:0}
.props select,.props input{width:auto;min-width:0;padding:1px 4px;font-size:13px;border:1px solid transparent;background:transparent;color:var(--fg);border-radius:4px;height:auto}
.props select:hover,.props input:hover,.props select:focus,.props input:focus{border-color:var(--line);background:var(--panel)}
.evg summary{display:flex;gap:6px;align-items:center;cursor:pointer;color:var(--mut);list-style:none}.evg summary::-webkit-details-marker{display:none}
.evg summary .dot{width:8px;height:8px;border-radius:50%;background:var(--line);flex:none}.evg summary b{color:var(--fg);font-weight:600}
.evg summary .when{font-size:12px;margin-left:6px}.evg[open]>summary{margin-bottom:8px}.evg>.ev{margin:0 0 8px 16px}
.tl[data-f=talk] .evg,.tl[data-f=talk] .ev:not(.comment){display:none}.tl[data-f=auto]>.ev:not(.auto){display:none}
.flowrow .fb{display:inline-flex;gap:2px;flex:none}.drow.done .sub{white-space:normal;overflow-wrap:anywhere}
details.more summary{cursor:pointer;font-size:12.5px;color:var(--mut)}
.adv>summary{cursor:pointer;display:flex;gap:10px;align-items:baseline;list-style:none}.adv>summary::-webkit-details-marker{display:none}.adv>summary:before{content:'▸';color:var(--mut)}.adv[open]>summary:before{content:'▾'}
@media (max-width:700px){.fsteps{grid-template-columns:repeat(3,minmax(0,1fr));row-gap:12px}.fsteps li:nth-child(4):before{display:none}}
.ah{padding:10px 14px 8px}
.ah .stitle{display:flex;align-items:center;gap:6px;min-width:0;max-width:240px;border:0;background:none;padding:4px 6px;margin-left:-6px;border-radius:6px;font-size:15px;font-weight:600;color:var(--fg)}
.ah .stitle:hover,.ah .stitle.on{background:var(--soft)}.ah .stitle .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ah .stitle .car{color:var(--mut);font-size:11px}
.ah .ctx{margin-top:4px}.ah .ctx a{font-size:12.5px}
.ah .mset{display:flex;flex-direction:column;gap:6px;padding:4px 10px 8px}.ah .mset select{width:100%}
#ast .menu{min-width:240px}
.abar .tog.on{background:var(--blue-s);color:var(--blue);border-color:#C9DCFB}
.inbox{margin-bottom:16px;border-left:3px solid var(--blue)}
.ibx>.ev-tag:first-child{flex:none;min-width:44px;justify-content:center}
.ibx{display:flex;gap:10px;align-items:center;padding:9px 6px;border-top:1px solid var(--line);color:var(--fg);border-radius:6px}.ibx:first-of-type{border-top:0}
.ibx:hover{text-decoration:none;background:var(--soft)}.ibx:hover .ibgo{color:var(--blue)}
.ibw{display:block;margin-top:3px;white-space:normal}.ibgo{flex:none;font-size:13px;color:var(--mut);font-weight:600}
.ibn{display:inline-block;min-width:20px;padding:0 6px;border-radius:10px;background:var(--blue);color:#fff;font-size:12px;text-align:center;vertical-align:2px}
.ibg{margin-top:10px}.ibh{display:flex;gap:8px;align-items:center;margin-bottom:2px}.ibmore{margin:2px 0 0 6px;font-size:13px}
.ibo{margin-top:8px}.ibo summary{cursor:pointer;padding:4px 0}
@media (max-width:640px){.ibgo{display:none}}
.catch{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:12px;padding:10px 14px;border-radius:8px;background:var(--warn-s);color:var(--fg);font-size:13px}
.catch span{flex:1;min-width:0}
.autoc{display:inline-flex;align-items:center;gap:6px;padding:1px 4px 1px 8px;border-radius:999px;background:var(--ok-s);color:var(--ok);font-size:12px}
.autoc::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.autoc.off{background:var(--warn-s);color:var(--warn)}
.autoc button.link{border:0;background:transparent;color:var(--blue);padding:0 4px;font-size:12px;cursor:pointer;height:auto}
.autoc button.link:hover{text-decoration:underline}
.first{max-width:760px}.frs{display:flex;gap:14px;align-items:center;padding:14px 0;border-top:1px solid var(--line)}
.frn{flex:none;width:28px;height:28px;border-radius:50%;background:var(--blue);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700}
.frs.done .frn{background:var(--ok)}.frs.done b{color:var(--mut)}
@media (max-width:700px){.frs{flex-wrap:wrap}.frs>.grow{flex-basis:calc(100% - 42px)}.frs>.btn,.frs>button{margin-left:42px}}
/* phones: no Ctrl K to show, and room at the bottom so the floating 助手 button never sits on the last buttons */
@media (max-width:700px){#astOpen{padding:9px 14px;right:12px;bottom:14px}#astOpen kbd,.frk{display:none}#page{padding-bottom:76px}}
/* 经验有没有用: three numbers side by side, wrapping on a phone */
.imp{border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin-bottom:10px}
.impg{display:flex;flex-wrap:wrap;gap:8px 24px;margin:6px 0}.impg>div{display:flex;flex-direction:column;min-width:7em}.impg b{font-size:16px;font-variant-numeric:tabular-nums}
/* 上线体检 rows: the mark carries the state, the fix sits under the finding */
.rdy{display:flex;gap:10px;padding:7px 0;border-top:1px solid var(--line)}.rdy .sub{white-space:normal;overflow-wrap:anywhere}.rdy>.grow{min-width:0}
.rdi{width:1.4em;text-align:center;font-weight:700;flex:none}.rdy.ok .rdi{color:var(--ok)}.rdy.warn .rdi{color:var(--warn)}.rdy.bad .rdi{color:var(--bad)}
.rdf{font-size:13px;margin-top:2px}
.tag.bad{background:var(--bad-s);color:var(--bad);border-color:#F5C2C3}
/* 最近出的版本 */
.rel{margin-bottom:14px}.relr{display:flex;gap:10px;align-items:baseline;padding:6px 0;border-top:1px solid var(--line);flex-wrap:wrap}.relr .grow{overflow-wrap:anywhere}
"""
