"""Unified workspace presentation, layered after legacy page styles.

The shell retains every route and action.  Page-specific layouts can opt into
the ws-* primitives without making their rendering depend on this stylesheet.
"""

WORKSPACE_CSS = r"""
:root{
 --workspace-nav-width:208px;--workspace-gap:24px;
 --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
html{scroll-padding-top:calc(var(--shell-height) + 16px)}
body{background:var(--bg);font-size:14px;line-height:1.65;letter-spacing:0}
::selection{background:#D8E7FF;color:#183A75}
a{color:var(--blue)}
h1,h2,h3{color:var(--fg);letter-spacing:-.025em;overflow-wrap:anywhere}
h1,.ph h1{font-size:27px;font-weight:650;line-height:1.35}
h2{font-size:17px;font-weight:650;line-height:1.5}
h3{font-size:14px;font-weight:600;line-height:1.55}
.mem-notice:empty{display:none}
.sub{font-size:13px;line-height:1.7;color:var(--mut)}
code,.key,pre{font-family:var(--mono)}
button,input,select,textarea,a.btn{border-radius:6px;min-height:36px;line-height:1.55;font-size:13px}
button,a.btn{font-weight:500;padding:7px 12px;transition:background-color 140ms,border-color 140ms,color 140ms,transform 100ms}
button:hover,a.btn:hover{border-color:var(--control-line);background:var(--hover);color:var(--blue);text-decoration:none}
button:active:not(:disabled),a.btn:active{transform:translateY(1px)}
button.primary,a.btn.primary{background:var(--blue);border-color:var(--blue);color:#fff}
button.primary:hover,a.btn.primary:hover{background:#173FAF;border-color:#173FAF;color:#fff;filter:none}
button.primary:active:not(:disabled){background:#153486}
button.ghost:hover{background:var(--soft);border-color:transparent}
button:disabled{opacity:.55;cursor:not-allowed;transform:none}
input,select,textarea{border-color:var(--control-line);padding:8px 10px;max-width:100%;background:#fff}
input::placeholder,textarea::placeholder{color:var(--mut);opacity:1}
input[type=checkbox],input[type=radio]{min-height:0;width:16px;height:16px;accent-color:var(--blue)}
:where(a,button,input,select,textarea,summary,[tabindex]):focus-visible{outline:2px solid var(--focus);outline-offset:3px;box-shadow:0 0 0 3px var(--blue-s)}
#main:focus-visible{outline:none;box-shadow:none}
.skip-link{z-index:100}

/* Header is global; the project scope remains visible while routes change. */
#top,body.svc-reform #top{
 height:var(--shell-height);min-height:var(--shell-height);display:flex;align-items:center;
 gap:14px;padding:0 24px;background:#fff;color:var(--fg);border-bottom:1px solid var(--line);
 position:sticky;top:0;z-index:16;box-shadow:none;
}
#top .brand{display:flex;align-items:center;gap:9px;min-width:calc(var(--workspace-nav-width) - 38px);color:var(--blue);font-size:17px;font-weight:700;letter-spacing:-.04em;white-space:nowrap;flex:none}
#top .brand #brandName{color:var(--fg)}
#top .brand svg{display:block;width:28px;height:28px;flex:none}
#projSel{width:190px;min-width:130px;max-width:210px;padding:7px 25px 7px 11px;min-height:34px;background:var(--bg);color:var(--fg);border:1px solid var(--control-line);font-size:13px;flex:none}
#projSel:hover{border-color:var(--control-line)}
#top .sp{flex:1;min-width:0}
#say{display:flex;align-items:center;margin:0;min-width:0;max-width:380px;width:auto;flex:1;background:var(--bg);border:1px solid var(--line);border-radius:6px;overflow:visible}
#say input{display:block;width:100%;min-width:0;min-height:34px;padding:7px 11px;border:0;background:transparent;color:var(--fg);font-size:12px;box-shadow:none}
#say input::placeholder{color:var(--mut)}
#say:focus-within{border-color:var(--blue)}
#top #sayGo{padding:7px 10px;border:0;border-left:1px solid var(--line);border-radius:0 5px 5px 0;min-height:34px;background:transparent;color:var(--blue);font-size:12px;white-space:nowrap}
#top button{background:#fff;border-color:var(--control-line);color:var(--fg);min-height:34px;font-size:12px;white-space:nowrap}
#top button:hover{border-color:var(--control-line);background:var(--soft);color:var(--blue)}
#top button.primary{background:var(--blue);border-color:var(--blue);color:#fff}
#top button.primary:hover{background:#173FAF;border-color:#173FAF}
#top #astToggle{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:7px 11px}
#top kbd{color:var(--mut);border-color:var(--line);background:var(--bg);opacity:1;font-size:10px}
#top .pts{display:flex;align-items:center;gap:5px;border:0;background:transparent;padding:5px;color:var(--mut);min-height:34px;font-size:12px;white-space:nowrap}
#top .pts b{font-size:12px;color:var(--fg);font-variant-numeric:tabular-nums}
#top .pts .dot{background:#94A3B8;width:5px;height:5px}
#account{display:flex;align-items:center;gap:8px;flex:none}
#top .me{display:inline-flex;align-items:center;justify-content:center;min-height:30px;padding:5px 10px;border-radius:6px;background:var(--soft);color:var(--mut);font-size:12px;white-space:nowrap}
#logout{color:var(--mut);font-size:12px}
#svc{background:var(--soft);border-color:var(--line);border-radius:6px}
#svc a{color:var(--mut);font-size:12px}
#svc a.on,body.svc-reform #svc a.on{background:#fff;color:var(--blue);box-shadow:none}

/* Main navigation is a true sidebar; the page's own tabs stay in its context. */
#wrap{display:flex;align-items:flex-start;min-height:calc(100dvh - var(--shell-height))}
#page{padding:0;min-width:0;flex:1;animation:workspace-enter 220ms ease-out both}
.sheet{
 display:grid;grid-template-columns:var(--workspace-nav-width) minmax(0,1fr);grid-template-rows:auto 1fr;
 max-width:none;min-height:calc(100dvh - var(--shell-height));margin:0;padding:0;
 border-radius:0;background:var(--bg);box-shadow:none;align-items:start;
}
#nav5{
 grid-column:1;grid-row:1/3;position:sticky;top:var(--shell-height);bottom:auto;left:auto;right:auto;
 align-self:start;display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;
 gap:3px;width:auto;min-width:0;height:calc(100dvh - var(--shell-height));min-height:0;
 padding:20px 12px 24px;margin:0;overflow-y:auto;overscroll-behavior:contain;
 background:#F0F2F5;border:0;border-right:1px solid var(--line);z-index:4;
}
#nav5 a{
 display:flex;position:relative;flex:none;flex-direction:row;align-items:center;justify-content:flex-start;
 gap:10px;min-height:40px;padding:9px 12px;margin:0;border:0;border-radius:6px;
 color:var(--mut);font-size:13px;font-weight:500;line-height:1.5;white-space:normal;text-decoration:none;
 transition:background-color 160ms,color 160ms;
}
#nav5 a:hover{color:var(--blue);background:var(--hover);text-decoration:none}
#nav5 a.on{background:var(--blue-s);color:var(--blue);box-shadow:inset 0 0 0 1px var(--selected-line);font-weight:650}
#nav5 a i{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;flex:none}
#nav5 .wicon,#nav5 svg{width:18px;height:18px}
#nav5 a b{position:static;margin-left:auto;flex:none;min-width:19px;line-height:19px;padding:0 5px;border-radius:4px;background:#DCE9FF;color:var(--blue);font-size:11px;font-weight:600;text-align:center}
#nav5 .ws-nav-label,#nav5 .nav-label{margin:26px 12px 8px;color:var(--mut);font-size:11px;letter-spacing:.06em;font-weight:500}
#nav5>.ws-nav-label{display:block;margin:1px 12px 12px}
#nav5 .ws-nav-secondary{display:flex;flex-direction:column;gap:3px;margin-top:auto;padding-top:30px}
#nav5 .ws-nav-secondary .ws-nav-label{display:block;margin:0 12px 8px}
#nav5 .ws-nav-secondary>a{font-size:12px;min-height:38px;padding:9px 12px}
#nav5 .ws-nav-note{margin:24px 12px 0;color:var(--mut);font-size:12px;line-height:1.8}
#tabs{
 grid-column:2;grid-row:1;display:flex;flex-wrap:wrap;align-items:center;gap:0 23px;
 margin:0;padding:0 30px;min-height:52px;border:0;border-bottom:1px solid var(--line);
 background:#fff;overflow:visible;
}
#tabs:empty{display:none}
#tabs>a,.tmore>summary{font-size:13px;padding:15px 0 13px;color:var(--mut);border-bottom-width:2px}
#tabs>a.on,.tmore.on>summary{color:var(--blue);border-bottom-color:var(--blue)}
#tabs .tnew{align-self:center;margin:8px 0 8px auto;min-height:30px;font-size:12px}
#tabs .tsep{border:0;margin-left:auto;padding-left:0;font-size:12px;color:var(--mut)}
.tmp{border-radius:8px;border-color:var(--line);box-shadow:0 8px 24px #11182714;z-index:24}
#tabs .tmp a{padding:9px 15px;min-height:36px}
#tabs .tmp a:hover,#tabs .tmp a.on{background:var(--blue-s)}
#main{grid-column:2;grid-row:2;min-width:0;width:100%;padding:27px 30px 56px;scroll-margin-top:calc(var(--shell-height) + 14px)}

/* Existing pages retain their content and actions in the new workspace. */
.ph,.hdr,.wkh{margin-bottom:22px;gap:14px}
.ph .eyebrow,.crumb{color:var(--mut);font-size:12px;letter-spacing:0}
.wk{max-width:none;margin:0}
.card,.blk{background:#fff;border:1px solid var(--line);border-radius:8px;padding:19px;box-shadow:none}
.card h2,.blk h2{margin-bottom:14px}
.detail,.grid2,.pgrid,.kbread{gap:var(--workspace-gap)}
.wkg{gap:var(--workspace-gap)}
.wkg .card{padding:18px 20px}
.wkg .wr{padding:14px 0;border-color:var(--line)}
.wr b{font-weight:550;line-height:1.6}
.wr .sub{font-size:12px;line-height:1.7}
.wr .go{font-size:12px;white-space:normal}
.wr .ico{color:var(--mut);background:var(--soft);border-radius:6px}
.saybig{border-radius:8px;border-color:var(--line);background:var(--bg);padding:18px;margin-bottom:22px}
.saybig textarea{background:#fff;min-height:74px;border-color:var(--control-line);font-size:14px}
.saybig label{font-size:14px;font-weight:600;color:var(--fg)}
.band{background:var(--navy);border-radius:8px;box-shadow:none;padding:21px 23px}
.band .gl,.band .cap b{color:#FFFFFF}.band .gs,.band .today,.band .cap span{color:#E2E8F0}
.band .insight{color:#E2E8F0;border-color:#64748B}.band .insight b{color:#E2E8F0}
.kpis{margin-bottom:23px;gap:14px}.kpis b,.kpi .n{font-weight:600;letter-spacing:-.035em;font-variant-numeric:tabular-nums}
.board{gap:14px}.col{background:var(--soft);border-radius:7px;padding:10px}.tc{border-color:var(--line);border-radius:7px;box-shadow:none;padding:13px}
.pill,.tag,.ev-tag{font-size:12px;line-height:1.5;letter-spacing:0}
.tag{padding:2px 6px;max-width:100%;white-space:normal;overflow-wrap:anywhere;background:var(--soft);color:var(--mut);border-color:var(--line)}
.pill{padding:2px 8px}.ev-tag{padding:2px 7px;border-radius:4px}
.st{font-size:12px;line-height:1.5;padding:3px 7px;border-radius:4px}
.tw{border-color:var(--line);border-radius:7px;background:#fff;max-width:100%}
table.t{font-size:13px;line-height:1.65}table.t th{white-space:nowrap}table.t td{overflow-wrap:anywhere}table.t .key{white-space:nowrap}table.t th{padding:11px 13px;background:var(--soft);font-size:12px;font-weight:500;color:var(--mut)}
table.t td{padding:13px;vertical-align:top;border-color:var(--line)}
table.t tbody tr:hover,table.t tr.click:hover td{background:var(--hover)}
.key{font-size:12px;color:var(--mut)}
.hint,.confirm,.cmdc{background:var(--blue-s);border-color:var(--line);border-radius:7px}
.inbox{border-left-width:2px}
.empty,.empty2{padding:44px 24px;color:var(--mut)}
.empty2 p{line-height:1.8}.wke{line-height:1.8;color:var(--mut)}
.fsteps{padding:15px 0 20px;margin-bottom:20px;border-bottom:1px solid var(--line)}
.fsteps li.cur .dot{box-shadow:0 0 0 4px var(--blue-s)}
.seg{border-radius:6px;background:var(--soft);border-color:var(--line)}
.seg button{font-size:12px}.seg button.on{background:var(--blue-s);color:var(--blue)}
.ttabs,.tabs{gap:20px}.ttabs a,.tabs button{padding:10px 3px}
.md{font-size:14px;line-height:1.85}.md p{margin:10px 0}.md pre{padding:16px;background:var(--code);border-radius:6px}
.md blockquote{border-left:2px solid #94A3B8;color:var(--mut);padding-left:16px}
pre.log,pre.diff{font-size:12px;line-height:1.7;padding:16px;border-radius:7px}
pre.log{background:var(--navy);color:#E2E8F0}
.kbdir{top:calc(var(--shell-height) + 16px);border-radius:7px;background:var(--bg);border-color:var(--line)}
.kbdir a.on{background:var(--blue-s);color:var(--blue)}
.lib-layout{gap:var(--workspace-gap);margin-top:20px}
.lib-row{padding:16px 0;border-color:var(--line)}.lib-meta{font-size:12px;line-height:1.85}
.lib-raw{font-size:12px;line-height:1.8;background:#FFFFFF;border-radius:6px}
.lib-section{margin-top:20px;padding-top:18px;border-color:var(--line)}
.atl{--a-bg:var(--bg);--a-panel:#FFFFFF;--a-card:var(--soft);--a-line:var(--line);--a-fg:var(--fg);--a-mut:var(--mut);--a-gold:var(--blue);border:1px solid var(--line);border-radius:8px}
.atl-cv{background-image:none}.atl-side .tour{background:var(--bg);border-color:var(--line)}

/* New workspace modules use these optional object-oriented primitives. */
.ws-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;flex-wrap:wrap;margin-bottom:16px}
.ws-head h1{margin:0 0 5px}.ws-head p{margin:0;color:var(--mut);font-size:13px}
.ws-eyebrow{display:block;color:var(--mut);font-size:12px;line-height:1.6;margin-bottom:6px;letter-spacing:.015em}
.ws-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ws-queue-tabs{display:flex;align-items:stretch;gap:20px;flex-wrap:wrap;margin:0 0 12px;border-bottom:1px solid var(--line)}
.ws-queue-tabs button{display:inline-flex;align-items:center;gap:7px;min-height:45px;padding:10px 0;border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;color:var(--mut);font-size:13px;white-space:nowrap}
.ws-queue-tabs button:hover{background:transparent;color:var(--blue)}
.ws-queue-tabs button.on{border-bottom-color:var(--blue);color:var(--blue);font-weight:600}
.ws-queue-tabs button span{padding:0 5px;min-width:18px;background:var(--soft);color:var(--mut);font-size:11px;line-height:18px;border-radius:4px;font-weight:500;text-align:center;font-variant-numeric:tabular-nums}
.ws-queue-tabs button.on span{background:#DCE9FF;color:var(--blue)}
.ws-subnav{display:flex;align-items:center;gap:24px;flex-wrap:wrap;border-bottom:1px solid var(--line);margin:0 0 22px}
.ws-subnav>a,.ws-subnav>button{padding:11px 0;color:var(--mut);border:0;border-bottom:2px solid transparent;background:transparent;border-radius:0;font-size:13px}
.ws-subnav>.on,.ws-subnav>[aria-current=page],.ws-subnav>[aria-selected=true]{color:var(--blue);border-bottom-color:var(--blue);font-weight:600}
.ws-columns{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(300px,1fr);gap:26px;align-items:start}
.ws-columns>*{min-width:0}
.ws-list,.ws-panel{border:1px solid var(--line);border-radius:8px;background:#fff;min-width:0;overflow-wrap:anywhere}
.ws-list-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 19px;border-bottom:1px solid var(--line)}
.ws-list-head h2{margin:0;font-size:15px}.ws-list-head small{color:var(--mut);font-size:12px}
.ws-row{display:flex;align-items:center;gap:14px;padding:16px 19px;border-bottom:1px solid var(--line);position:relative;min-width:0}
.ws-row:last-child{border-bottom:0}
.ws-row:hover{background:var(--bg)}
.ws-row.on,.ws-row[aria-selected=true]{background:var(--blue-s);box-shadow:inset 3px 0 var(--blue)}
.ws-row-title{font-size:14px;font-weight:600;line-height:1.6;color:var(--fg);overflow-wrap:anywhere}
.ws-row-meta{display:flex;gap:7px 10px;flex-wrap:wrap;margin-top:5px;font-size:12px;line-height:1.65;color:var(--mut)}
.ws-row-meta code{font-size:11px}
.ws-row .ws-action{margin-left:auto;flex:none}
.ws-row>.btn{flex:none;font-size:12px;padding:6px 10px;min-height:32px}
.ws-row>.pill{flex:none}
.ws-task-marker{display:block;width:9px;height:9px;border-radius:3px;background:#A6B3A6;border:1px solid #95A794;flex:none;align-self:flex-start;margin-top:8px}
.ws-task-marker.state-analyzing{background:#91B3C5;border-color:#6D99B0}.ws-task-marker.state-doing{background:#A8C4FA;border-color:#5B85CC}
.ws-task-marker.state-verify{background:#E7CC8C;border-color:#BEA361}.ws-task-marker.state-confirm{background:#C8B5D7;border-color:#AC91C0}
.ws-task-marker.state-closed{background:#AAC5A7;border-color:#83A77E}
.ws-pagination{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-top:17px;flex-wrap:wrap}
.ws-pagination>.sub{margin-right:auto;font-size:12px}.ws-pagination button{min-height:31px;padding:5px 9px;font-size:12px}
.ws-aside{display:flex;flex-direction:column;gap:20px;min-width:0}
.ws-aside .ws-panel{padding:19px 20px}.ws-aside .ws-panel h2{font-size:15px;margin:0 0 13px}
.ws-aside .ws-panel .hdr{margin:0 0 6px;align-items:center}.ws-aside .ws-panel .hdr h2{margin:0}
.ws-aside .hdr>a{font-size:12px}
.ws-project-line{display:flex;align-items:center;gap:11px;padding:14px 0;border-bottom:1px solid var(--line);color:var(--fg);text-decoration:none}
.ws-project-line:last-child{border-bottom:0;padding-bottom:0}.ws-project-line:hover{text-decoration:none;color:var(--blue)}
.ws-project-line b{display:block;font-size:13px;font-weight:600;line-height:1.6;overflow-wrap:anywhere}
.ws-project-line small{display:block;margin-top:2px;color:var(--mut);font-size:12px;line-height:1.7}
.ws-project-line>.wicon{width:16px;height:16px;flex:none;color:var(--mut)}
.ws-project-avatar{display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;border:1px solid var(--line);border-radius:8px;background:var(--soft);color:var(--blue);font-family:var(--mono);font-size:11px;font-weight:650;flex:none}
.ws-project-line .ws-project-avatar{width:32px;height:32px;border-radius:7px}
.ws-project-search{display:flex;align-items:center;gap:12px;max-width:510px;font-size:12px;color:var(--mut);margin:0 0 23px}
.ws-project-search input{flex:1;min-width:0;font-size:13px}
.ws-project-intro{margin-bottom:26px;background:var(--bg);border-color:var(--line)}
.ws-project-intro h2{margin:8px 0 12px;font-size:21px}.ws-project-intro p{font-size:13px;color:var(--mut);line-height:1.85;margin:0 0 16px}
.ws-quicklinks{display:flex;flex-direction:column;gap:0}
.ws-quicklinks>a{display:flex;align-items:center;justify-content:space-between;gap:14px;min-height:43px;padding:10px 0;color:var(--mut);font-size:13px;line-height:1.65;text-decoration:none;border-bottom:1px solid var(--line)}
.ws-quicklinks>a:last-child{border-bottom:0}.ws-quicklinks>a:hover{color:var(--blue);background:var(--hover)}
.ws-quicklinks .wicon{width:16px;height:16px;flex:none;color:var(--mut)}
.ws-memory-callout{background:var(--bg);border-color:var(--line)}
.ws-aside .ws-memory-callout h2{font-size:16px;line-height:1.6;margin:7px 0 10px}
.ws-memory-callout .sub{color:var(--mut);font-size:12px;line-height:1.85;margin:0 0 15px}
.ws-memory-callout .btn{display:inline-flex;align-items:center;gap:10px;background:#fff;border-color:var(--control-line);font-size:12px;color:var(--blue)}
.ws-memory-callout .wicon{width:15px;height:15px}
.ws-ticket-team dl{display:grid;grid-template-columns:68px 1fr;gap:8px 12px;margin:13px 0 17px;font-size:13px}
.ws-ticket-team dt{color:var(--mut)}.ws-ticket-team dd{margin:0;color:var(--fg)}
.ws-panel{padding:22px}
.ws-panel h2{font-size:21px;line-height:1.45;margin:11px 0 12px}
.ws-panel h3{margin:0 0 12px}
.ws-section{padding:19px 0;border-top:1px solid var(--line)}
.ws-section:first-child{padding-top:0;border-top:0}.ws-section:last-child{padding-bottom:0}
.ws-label{color:var(--mut);font-size:12px;line-height:1.6;margin-bottom:9px}
.ws-empty{padding:32px 22px;color:var(--mut);font-size:13px;line-height:1.85}
.ws-empty strong{display:block;margin-bottom:6px;color:var(--fg);font-size:15px;font-weight:600}
.ws-stat-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:22px 0}
.ws-stat{padding:18px;border:1px solid var(--line);border-radius:7px;background:#fff;min-width:0}
.ws-stat b{display:block;margin:6px 0;font-size:24px;font-weight:600;line-height:1.3;font-variant-numeric:tabular-nums;letter-spacing:-.03em}
.ws-stat small{font-size:12px;color:var(--mut)}
.ws-filterbar{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:17px}
.ws-search{display:flex;align-items:center;gap:8px;min-width:0}.ws-search input{width:260px;max-width:100%;font-size:13px}
form.ws-search{margin:0 0 17px;gap:10px}form.ws-search>label{font-size:12px;color:var(--mut);white-space:nowrap}form.ws-search>input{flex:1;min-width:0;width:auto}form.ws-search>button{font-size:12px;flex:none}
.ws-note{border-left:2px solid #94A3B8;padding:7px 0 7px 14px;color:var(--mut);font-size:13px;line-height:1.8}
.ws-evidence{padding:13px 15px;border:1px solid var(--line);border-radius:6px;background:var(--bg);font-size:13px;line-height:1.75}
.ws-avatar{display:inline-flex;align-items:center;justify-content:center;width:27px;height:27px;border-radius:50%;background:var(--soft);color:var(--blue);font-size:12px;flex:none}
.ws-timeline{border-left:1px solid var(--line);padding-left:18px;margin:12px 0 0 5px}
.ws-timeline>div{position:relative;padding:0 0 19px}.ws-timeline>div:before{content:'';position:absolute;left:-22px;top:7px;width:7px;height:7px;border-radius:50%;background:#94A3B8;border:1px solid #fff}
.ws-timeline>div:last-child{padding-bottom:0}

/* Dialogs, assistant and long evidence keep the same visual hierarchy. */
#modal{z-index:40;background:#11182766;padding:5vh 20px}
.mbox{padding:27px;border-radius:12px;box-shadow:0 24px 70px #11182726}
.mx{width:34px;min-height:34px;right:13px;top:13px;font-size:24px;padding:0;color:var(--mut)}
.mbox>#mbody>h2:first-child{font-size:22px;padding-right:35px;margin-bottom:18px}
.form{gap:15px}.form label,label.fl{font-size:12px;color:var(--mut);line-height:1.7}
.form label>input,.form label>textarea,.form label>select{margin-top:5px}
#toast{z-index:50;background:var(--navy);border-color:#64748B;border-radius:7px;box-shadow:0 6px 22px #11182720}
#ast{position:sticky;top:var(--shell-height);height:calc(100dvh - var(--shell-height));width:360px;max-width:100%;background:#fff;border-left:1px solid var(--line);z-index:18;animation:workspace-panel 200ms ease-out both}
.ah{padding:18px 17px 14px;border-color:var(--line)}.ain{padding:15px}.ain .box{border:1px solid var(--control-line);background:var(--bg);border-radius:7px;padding:11px}
.ain textarea{font-size:14px;line-height:1.75;padding:4px;min-height:76px}.ain .foot{font-size:12px;line-height:1.6}
.m-u{background:var(--blue-s);border-radius:9px 9px 2px 9px;padding:12px 14px}
.cite{border:1px solid var(--line);border-radius:6px;padding:10px;background:#fff}
#astOpen{display:none!important}
body.ast-on #ast{z-index:25}
@keyframes workspace-enter{from{opacity:0}to{opacity:1}}
@keyframes workspace-panel{from{opacity:0;transform:translateX(7px)}to{opacity:1;transform:none}}

@media(min-width:1600px){:root{--workspace-nav-width:220px}#main{padding:30px 40px 64px}#tabs{padding:0 40px}}
@media(max-width:1300px){
 :root{--workspace-nav-width:184px;--workspace-gap:20px}
 #top{padding:0 18px;gap:10px}#top .brand{min-width:148px;font-size:16px}
 #projSel{width:155px;max-width:170px;min-width:125px}#say{max-width:290px}#top kbd{display:none}
 #top .pts .w{display:none}#main{padding:25px 24px 52px}#tabs{padding:0 24px;gap:0 19px}
 .ws-columns{grid-template-columns:minmax(0,1.5fr) minmax(280px,1fr);gap:20px}
}
@media(max-width:1100px){
 #say input{width:140px}#say{max-width:210px}#top .brand{min-width:0}#projSel{width:150px}
 #ast{position:fixed;right:0;box-shadow:-10px 0 35px #11182724}
 .detail,.grid2,.pgrid,.ws-columns{grid-template-columns:minmax(0,1fr)}
 .ws-stat-grid{gap:12px}.ws-panel{padding:20px}
}
@media(max-width:950px){
 :root{--shell-height:112px;--workspace-nav-width:170px}
 #top,body.svc-reform #top{height:auto;min-height:var(--shell-height);display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:9px 12px;padding:12px 18px}
 #top .brand{grid-column:1;grid-row:1;font-size:16px}#account{grid-column:3;grid-row:1;justify-self:end}
 #projSel{grid-column:1;grid-row:2;max-width:100%;width:100%;min-width:0}
 #say{grid-column:2;grid-row:2;max-width:none;width:auto;justify-self:stretch}#say input{width:135px}
 #astToggle{grid-column:3;grid-row:2}#top .pts{grid-column:2;grid-row:1;justify-self:end}
 #top .sp{display:none}#svc{grid-column:1/-1;grid-row:3}
 #main{padding:23px 20px 48px}#tabs{padding:0 20px;gap:0 16px}
 #nav5{padding:20px 9px}#nav5 a{font-size:12px;padding:10px;gap:8px}
 .wkg,.kbread{grid-template-columns:minmax(0,1fr)}
}
@media(max-width:700px){
 :root{--shell-height:116px;--workspace-nav-width:0px;--workspace-gap:18px}
 #top,body.svc-reform #top{position:sticky;top:0;padding:10px 14px;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;height:auto;min-height:var(--shell-height)}
 #top .brand{font-size:16px;grid-column:1;grid-row:1;min-width:0}#top .brand svg{display:block;width:26px;height:26px}
 #brandName{display:inline}#top .brand #brandName{display:inline}
 #account{grid-column:3;grid-row:1;gap:6px;max-width:100%}#top .me{display:inline-flex;font-size:11px;min-height:30px;padding:5px 9px;max-width:110px;white-space:normal;overflow-wrap:anywhere}
 #top .pts{grid-column:2;grid-row:1;display:flex!important;padding:3px;min-height:30px;font-size:11px}
 #projSel{grid-column:1;grid-row:2;min-height:42px;font-size:12px;max-width:none;width:100%;min-width:0}
 #say{grid-column:2;grid-row:2;display:flex;min-width:0;flex:none}#say input{display:none}
 #top #sayGo{display:block;min-height:42px;border-left:0;border-radius:5px;font-size:13px;padding:8px 11px}
 #top #sayGo span{display:inline}#top #astToggle{grid-column:3;grid-row:2;display:inline-flex;min-height:42px;padding:8px 10px;font-size:12px}
 #top kbd{display:none}#svc{grid-row:3;display:flex;justify-content:flex-start}#svc a{min-height:36px;padding:8px 10px;flex:1}
 #wrap{min-height:calc(100dvh - var(--shell-height))}#page{padding:0}
 .sheet{display:block;min-height:calc(100dvh - var(--shell-height));padding:0}
 #nav5{
  position:fixed;top:auto;left:0;right:0;bottom:0;height:auto;min-height:64px;width:100%;
  flex-direction:row;align-items:stretch;justify-content:space-around;gap:0;padding:3px 5px calc(4px + env(safe-area-inset-bottom));
  border:0;border-top:1px solid var(--line);background:var(--bg);overflow:visible;z-index:20;
 }
 #nav5 a{display:flex;flex:1;flex-direction:column;justify-content:center;align-items:center;gap:4px;padding:7px 2px 6px;min-height:56px;border-radius:5px;font-size:11px;line-height:1.35;white-space:normal;text-align:center}
 #nav5 a.on{background:var(--blue-s);border:0;color:var(--blue);box-shadow:inset 0 0 0 1px var(--selected-line)}
 #nav5 a i,#nav5 svg,#nav5 .wicon{width:19px;height:19px}
 #nav5 a b{position:absolute;top:1px;right:4px;min-width:15px;font-size:10px;line-height:15px;padding:0 4px}
 #nav5 .ws-nav-label,#nav5 .nav-label,#nav5 .ws-nav-note{display:none}
 #nav5 .ws-nav-secondary{display:none}
 #tabs{display:flex;min-height:44px;gap:0 16px;margin:0;padding:0 16px;flex-wrap:wrap;border-bottom:1px solid var(--line)}
 #tabs>a,.tmore>summary{font-size:12px;padding:12px 0 10px}
 #tabs .tnew{margin:6px 0 6px auto;min-height:32px}#tabs .tsep{font-size:11px}
 #main{padding:22px 16px calc(98px + env(safe-area-inset-bottom));min-width:0;scroll-margin-top:130px}
 h1,.ph h1{font-size:24px}.ph,.hdr,.wkh,.ws-head{gap:12px;margin-bottom:19px}
 .card,.blk,.ws-panel{padding:16px;border-radius:7px}.wkg .card{padding:16px}
 .ws-head h1{margin-bottom:4px}.ws-head p{font-size:12px}
 .ws-columns{display:grid;grid-template-columns:minmax(0,1fr);gap:18px}
 .ws-row{padding:14px;gap:10px;flex-wrap:wrap}.ws-row .ws-action{margin-left:0}.ws-row-title{font-size:14px}
 .ws-list-head{padding:14px}.ws-subnav{gap:15px;margin-bottom:18px}.ws-subnav>a,.ws-subnav>button{font-size:12px}
 .ws-queue-tabs{gap:13px;margin-bottom:16px}.ws-queue-tabs button{font-size:12px;gap:4px;padding:10px 0;min-height:41px}
 .ws-queue-tabs button span{font-size:10px;padding:0 4px;min-width:16px;line-height:17px}
 .ws-aside{gap:17px}.ws-aside .ws-panel{padding:17px}.ws-project-search{align-items:flex-start;flex-direction:column;gap:6px;margin-bottom:18px}.ws-project-search input{width:100%}
 .ws-project-intro{margin-bottom:22px}.ws-project-intro h2{font-size:19px}.ws-project-line small{font-size:12px}
 .ws-row>.btn{min-height:34px}.ws-row>.grow{flex-basis:calc(100% - 50px)}.ws-row>.pill{margin-left:23px}
 form.ws-search{flex-wrap:wrap;gap:8px}form.ws-search>label{width:100%;font-size:12px}form.ws-search>input{flex:1}
 .ws-stat-grid{grid-template-columns:minmax(0,1fr);gap:10px;margin:18px 0}.ws-stat{padding:15px}.ws-stat b{font-size:23px}
 .ws-search{width:100%}.ws-search input{width:100%;min-width:0}
 .ws-filterbar{align-items:stretch}.ws-actions{gap:7px}
 .saybig{padding:15px}.saybig textarea{min-height:90px}
 .tw:has(>table.t)::before{content:"左右滑动，查看全部字段";display:block;position:sticky;left:0;width:100%;padding:8px 12px;background:var(--soft);border-bottom:1px solid var(--line);color:var(--mut);font-size:12px}table.t{min-width:720px}table.t th,table.t td{padding:10px 12px}table.t th:nth-child(2),table.t td:nth-child(2){min-width:200px}
 .kbdir{position:static;max-height:none}.kbread,.grid2,.detail,.pgrid,.wkg{grid-template-columns:minmax(0,1fr)}
 #ast{position:fixed;top:0;right:0;bottom:0;width:100%;max-width:100%;height:100dvh;z-index:35;box-shadow:none}
 body.ast-on #ast{z-index:35}body.ast-on #modal{right:0}
 #modal{padding:18px 12px;align-items:flex-start}.mbox{padding:22px 18px;border-radius:10px;max-width:100%}
 .mbox>#mbody>h2:first-child{font-size:20px}.mbox h2:has(#nproj){display:flex;flex-direction:column;align-items:flex-start;gap:8px;text-wrap:initial}.mbox #nproj{max-width:100%;min-width:0}.mx{top:10px;right:10px}
 .md{font-size:14px;line-height:1.85}pre.log,pre.diff,.lib-raw{font-size:12px;line-height:1.7;padding:12px}
}
@media(max-width:390px){#top{padding:10px 12px;gap:8px 6px}#top .brand{font-size:15px}#top .brand svg{width:24px;height:24px}#top .me{max-width:80px}#logout{font-size:11px}#top #sayGo{padding:8px}#top #astToggle{padding:8px}#main{padding-left:13px;padding-right:13px}#tabs{padding-left:13px;padding-right:13px}}
@media(prefers-reduced-motion:reduce){#page,#ast{animation:none}button,a.btn,#nav5 a{transition:none}button:active:not(:disabled),a.btn:active{transform:none}}

/* Delivery/operations handoff workspace: keep responsibility visible at every width. */
.ws-stage-strip{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.ws-stage-strip button{display:flex;align-items:center;gap:12px;justify-content:space-between;padding:8px 12px;min-width:96px;background:var(--panel);border-color:var(--line)}
.ws-stage-strip button b{font-variant-numeric:tabular-nums;font-size:16px}.ws-stage-strip button[aria-pressed=true]{background:var(--blue-s);border-color:var(--selected-line);color:var(--blue)}
.ws-flow-layout{display:grid;grid-template-columns:minmax(290px,.95fr) minmax(380px,1.35fr);gap:24px;align-items:start}.ws-flow-layout>*{min-width:0}
.ws-flow-row{padding:16px 18px;border-bottom:1px solid var(--line)}.ws-flow-row:last-child{border-bottom:0}.ws-flow-row:has([aria-pressed=true]){background:var(--blue-s);box-shadow:inset 3px 0 var(--blue)}
.ws-select-task{display:block;text-align:left;padding:4px 0;margin:6px 0;border:0;background:transparent;font-size:15px;font-weight:650;color:var(--fg);width:100%;overflow-wrap:anywhere}.ws-select-task:hover{background:transparent;color:var(--blue)}
.ws-row-owners{display:grid;grid-template-columns:85px minmax(0,1fr);gap:3px 10px;margin:10px 0;font-size:12px}.ws-row-owners dt{color:var(--mut)}.ws-row-owners dd{margin:0;overflow-wrap:anywhere}
.ws-task-action{display:inline-flex;align-items:center;gap:8px;margin-top:10px;font-size:12px}.ws-task-action svg{width:14px;height:14px}
.ws-filter-label{display:flex;gap:8px;align-items:center;font-size:12px;color:var(--mut)}.ws-filter-label select{min-width:130px}.ws-boundary{margin:7px 0 15px}.ws-work-links{display:flex;flex-wrap:wrap;gap:10px 16px;margin-top:24px;font-size:12px}
.ws-inline-error{padding:12px 14px;background:#FCF3EB;border:1px solid #EAD7BE;border-radius:6px;color:#794F20;margin:10px 0;overflow-wrap:anywhere}.ws-inline-error p{margin:0 0 8px}
#wsQueueNotice{margin:12px 0;color:var(--mut);font-size:12px;min-height:20px}
.ws-detail{padding:22px;border:1px solid var(--line);border-radius:8px;background:var(--panel);overflow-wrap:anywhere}.hf-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.hf-head h2{font-size:22px;line-height:1.45;margin:3px 0 16px}.hf-head button{flex:none;font-size:12px}.hf-head h2:focus{outline:2px solid var(--focus);outline-offset:4px}
.hf-progress{display:flex;gap:12px;align-items:center;justify-content:space-between;font-size:13px;margin:0 0 17px}.hf-facts{display:grid;grid-template-columns:96px minmax(0,1fr);gap:8px 12px;margin:0 0 18px;font-size:13px}.hf-facts dt{color:var(--mut)}.hf-facts dd{margin:0;overflow-wrap:anywhere}
.ws-block-reason{background:#FAF1E3;border-left:3px solid #B98D42;padding:10px 12px;line-height:1.7;font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}.ws-block-reason p{margin:5px 0 0}
.hf-evidence-state{display:flex;gap:8px 20px;flex-wrap:wrap;padding:10px 0 16px;font-size:12px;color:var(--mut)}.hf-full-text{white-space:pre-wrap;overflow-wrap:anywhere;word-break:normal;font:inherit;line-height:1.8;margin:8px 0}
.hf-source{margin:12px 0;border:1px solid var(--line);border-radius:6px;padding:8px 11px;background:#FFF}.hf-source summary,.hf-history-item summary{cursor:pointer;font-size:12px;color:var(--mut);line-height:1.8;overflow-wrap:anywhere}.hf-source pre,.hf-history-item pre{font:12px/1.8 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;max-width:100%;margin:12px 0 3px}
.hf-field{display:flex;flex-direction:column;gap:6px;font-size:12px;color:var(--mut);margin-bottom:13px}.hf-field textarea,.hf-field select{width:100%;font-size:13px;color:var(--fg);min-width:0}.hf-form-fields{margin-top:13px}.hf-history-item{padding:14px 0;border-bottom:1px solid var(--line)}.hf-history-item:last-child{border:0}.hf-history-item p{font-size:13px;margin:7px 0}.hf-history-item .ws-row-meta{margin:0}
#hfNotice:empty{display:none}#hfNotice{margin:10px 0}#hfBinding{margin:8px 0 12px}#hfFormArea .ws-actions{align-items:stretch}#hfRebind{font-size:12px}#hfBoundary{border-top:1px solid var(--line);padding-top:14px}
@media(max-width:1100px){.ws-flow-layout{grid-template-columns:minmax(260px,1fr) minmax(330px,1.1fr);gap:18px}.ws-detail{padding:18px}.ws-stage-strip button{min-width:84px}}
@media(max-width:900px){.ws-flow-layout{grid-template-columns:minmax(0,1fr)}.ws-detail{margin-top:2px}.ws-stage-strip{gap:6px}.ws-stage-strip button{flex:1 1 90px}.hf-head h2{font-size:21px}}
@media(max-width:520px){.ws-flow-row{padding:15px}.ws-detail{padding:16px}.ws-stage-strip button{min-width:0;font-size:12px}.hf-head{flex-wrap:wrap}.hf-head h2{margin-bottom:8px}.hf-facts{grid-template-columns:85px minmax(0,1fr)}.ws-filter-label{width:100%;justify-content:space-between}.ws-filter-label select{flex:1;max-width:220px}.hf-progress{align-items:flex-start;flex-wrap:wrap}.hf-field textarea{font-size:16px}.ws-row-owners{grid-template-columns:85px minmax(0,1fr)}.hf-source{padding:8px}.hf-head button{min-height:40px}.ws-work-links a{padding:7px 0}}
"""
