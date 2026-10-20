"""Shared product tokens and shell. Loaded after page modules so routes cannot fork the theme."""

THEME_CSS = r"""
:root{
 --bg:#F6F7F4;--panel:#FFFFFF;--fg:#23352D;--mut:#61716A;--line:#DCE3DC;--soft:#EFF2ED;
 --blue:#20634C;--blue-s:#EAF2EC;--acc:#20634C;--acc2:#76A58C;
 --navy:#233C31;--navy-rf:#233C31;--navy2:#2B493C;--navy3:#355746;
 --ok:#227451;--ok-s:#EAF4ED;--bad:#B73D39;--bad-s:#FCF0EE;
 --warn:#95610F;--warn-s:#FCF4E3;--pur:#615391;--pur-s:#F1EEF7;--code:#EFF2EE;
 --s-new:#66786D;--s-analyzing:#346C8E;--s-confirm:#75619A;--s-doing:#21785C;--s-verify:#996515;--s-closed:#517459;
 --shell-height:68px;--focus:#277657;color-scheme:light;
}
body{background:var(--bg);font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased}
::selection{background:#CDE4D5;color:#153D2C}
button,input,select,textarea,a.btn{border-radius:6px;min-height:36px;line-height:1.5}
button,a.btn{padding:7px 13px;font-weight:500;transition:background-color .15s,border-color .15s,color .15s}
button:hover,a.btn:hover{background:var(--blue-s);border-color:#A5BAAC;color:var(--blue)}
button.primary,a.btn.primary{background:var(--blue);color:#fff;border-color:var(--blue)}
button.primary:hover,a.btn.primary:hover{background:#194F3D;border-color:#194F3D;filter:none}
button:active:not(:disabled),a.btn:active{background:#DAE8DE}
button.primary:active:not(:disabled),a.btn.primary:active{background:#154431}
button:disabled{opacity:.55;cursor:not-allowed}
button.ghost:hover{background:var(--soft);border-color:transparent}
input,select,textarea{padding:8px 10px;border-color:#CBD6CD;max-width:100%}
input::placeholder,textarea::placeholder{color:#7A857E;opacity:1}
input[type=checkbox],input[type=radio]{min-height:0;accent-color:var(--blue);width:16px;height:16px}
:where(a,button,input,select,textarea,summary,[tabindex]):focus-visible{outline:2px solid var(--focus);outline-offset:3px;box-shadow:0 0 0 4px var(--blue-s)}
.ain textarea:focus-visible{outline:2px solid var(--focus);outline-offset:3px}
#main:focus-visible{outline:0;box-shadow:none}
.skip-link{position:fixed;top:8px;left:16px;transform:translateY(-150%);z-index:100;background:var(--panel);padding:10px 18px;border:1px solid var(--blue);border-radius:6px}
.skip-link:focus{transform:none}
h1,h2,h3{color:var(--fg);text-wrap:balance;overflow-wrap:anywhere;letter-spacing:-.025em}
h1,.ph h1{font-size:26px;line-height:1.35;font-weight:650}
h2{font-size:18px;line-height:1.45;font-weight:650}
h3{font-size:15px;line-height:1.5;font-weight:650}
.sub{line-height:1.65;color:var(--mut)}
.ph{margin:0 0 24px;gap:16px}.ph .eyebrow{letter-spacing:.04em;text-transform:none}
.hdr{margin-bottom:20px}.crumb{letter-spacing:0;margin-bottom:14px}
.card,.blk{padding:20px;border-radius:10px;box-shadow:none}
.card h2,.blk h2{margin-bottom:16px}
.blk.src,.blk.cov,.blk.qa,.blk.mr{background:var(--panel);border-color:var(--line)}
.hint,.confirm,.cmdc{border-color:#CEDDD1;background:var(--blue-s)}
.inbox{border-left-width:1px}
.md blockquote{border-left-width:1px}
.md{line-height:1.8}.md pre{padding:16px}.md p{margin:8px 0}
pre.log,pre.diff{font-size:12px;line-height:1.65;padding:16px}
pre.log{background:#1E3028;color:#DAE5DD}
.key,code,pre{overflow-wrap:anywhere}
.empty,.empty2{padding:48px 24px}.empty2 p{line-height:1.8}
.pill,.tag,.ev-tag{font-size:12px;line-height:1.5;letter-spacing:0}
.tag{max-width:100%;white-space:normal;overflow-wrap:anywhere}
.pill{padding:3px 9px}
.tw{border-color:var(--line);border-radius:8px;background:var(--panel);max-width:100%}
table.t{font-size:13px}table.t th{padding:12px 14px;background:var(--soft);font-size:12px;color:var(--mut);font-weight:600}
table.t td{padding:12px 14px;vertical-align:top;border-color:var(--line)}
table.t tbody tr:hover{background:#F5F8F3}
.kpis{margin-bottom:24px}.kpis b,.kpi .n{font-weight:600;letter-spacing:-.04em}
.band{background:#2B493C;border-radius:10px;padding:22px 24px;box-shadow:none}
.band .gl,.band .cap b{color:#F6F8F4}.band .gs,.band .today,.band .cap span{color:#D0DFD4}
.band .insight{color:#E4EBE6;border-color:#53725E}.band .insight b{color:#D7EBCF}
.board{gap:16px}.col{padding:12px;background:#EAF0E9}.tc{padding:14px;box-shadow:none}
.detail{gap:24px}.grid2,.pgrid{gap:24px}.kbread{gap:24px}
.kbdir{top:84px}.kbdir,.stp{border-radius:8px}
.fsteps{padding:18px 0 22px;margin:0 0 20px;border-bottom:1px solid var(--line)}
.fsteps li.cur .dot{box-shadow:0 0 0 4px var(--blue-s)}
.tl{gap:16px}.ev .cbody{padding:12px 14px;background:var(--soft)}
.seg{border-radius:6px;background:var(--panel)}
.seg button.on{background:var(--blue-s);color:var(--blue)}
.ttabs,.tabs{gap:16px}.ttabs a,.tabs button{padding:10px 4px}

/* A stable workspace header: project scope and tools use the same hierarchy on every route. */
#top,body.svc-reform #top{height:var(--shell-height);padding:0 32px;gap:16px;background:var(--panel);color:var(--fg);border-bottom:1px solid var(--line);box-shadow:none}
#top .brand{color:var(--blue);font-size:16px;line-height:1.3;font-weight:650;letter-spacing:-.02em;gap:10px;flex:none}
#top .brand:hover{text-decoration:none}#top .brand #brandName{color:var(--fg)}
#top .brand svg{display:block;width:32px;height:32px}
#projSel{background:var(--soft);color:var(--fg);border:1px solid transparent;max-width:240px;min-width:144px;min-height:36px;padding:7px 28px 7px 12px;font-size:12px}
#projSel:hover{border-color:#A5BAAC}
#svc{background:var(--soft);border:1px solid var(--line);padding:2px;border-radius:7px}
#svc a{color:var(--mut);padding:5px 9px;font-size:12px}
#svc a.on,body.svc-reform #svc a.on{background:var(--panel);color:var(--blue);box-shadow:0 1px 3px #203F3010}
#svc a:hover{color:var(--blue)}
#top button{color:var(--fg);background:var(--panel);border:1px solid var(--line);white-space:nowrap;font-size:12px}
#top button:hover{color:var(--blue);background:var(--soft);border-color:#A5BAAC}
#top .pts{gap:5px;border:0;background:none;border-radius:6px;padding:6px;font-size:12px;color:var(--mut)}
.pts .dot{width:6px;height:6px;background:var(--acc2)}.pts b{font-size:12px;font-weight:600;color:var(--fg)}
#say{margin:0;display:flex;width:auto;flex:none;gap:0;border:1px solid var(--line);border-radius:6px;background:var(--panel);overflow:visible}
#say input{width:170px;min-width:0;background:transparent;color:var(--fg);border:0;outline-offset:1px;font-size:12px;box-shadow:none}
#say input::placeholder{color:var(--mut)}#top #sayGo{border:0;background:var(--soft);border-radius:0 5px 5px 0;padding:7px 11px;color:var(--fg)}
#say:focus-within{border-color:var(--blue)}
#account{display:flex;align-items:center;gap:8px;flex:none}
#top .me{display:inline-flex;align-items:center;justify-content:center;min-height:32px;padding:6px 10px;color:var(--mut);background:var(--soft);border:0;border-radius:6px;font-size:12px}
#logout{font-size:12px;color:var(--mut)}
#top kbd{font-size:10px;border-color:var(--line);opacity:1;color:var(--mut);background:var(--soft)}
#wrap{min-height:calc(100% - var(--shell-height))}
#page{padding:0 32px 64px;min-width:0}
.sheet{padding:0;max-width:1600px;margin:0 auto;border-radius:0;background:transparent;box-shadow:none}
#main{padding-top:28px;min-width:0;scroll-margin-top:100px}
#nav5{background:transparent;border-bottom:1px solid var(--line)}
#tabs{margin:0;gap:24px;flex-wrap:wrap;padding:0;border-bottom:1px solid var(--line);align-items:center}
#tabs>a,.tmore>summary{font-size:13px;padding:14px 0 12px}
#tabs .tnew{margin-left:auto;min-height:32px;font-size:12px}
.tmp{border-radius:8px;border-color:var(--line);box-shadow:0 8px 24px #23352D14}
#tabs .tmp a{padding:10px 16px;min-height:40px}

/* Dialogs and assistant share typography and predictable keyboard scope. */
body.dialog-open{overflow:hidden}
#modal{background:#23352D65;padding:6vh 20px;z-index:20;overscroll-behavior:contain}
.mbox{padding:28px;border-radius:14px;box-shadow:0 24px 80px #172E3026;outline:none}
.mbox> #mbody>h2:first-child{padding-right:36px;font-size:22px;margin-bottom:20px}
.mx{right:14px;top:14px;width:36px;min-height:36px;padding:0;line-height:1;font-size:24px;color:var(--mut)}
.form{gap:16px}.form label,label.fl{color:var(--mut);font-size:12px;line-height:1.6}
.form label>input,.form label>textarea,.form label>select{margin-top:5px}
#toast{background:var(--navy);border:1px solid #56715E;box-shadow:0 8px 24px #23352D20;z-index:30}
#ast{top:var(--shell-height);height:calc(100dvh - var(--shell-height));border-color:var(--line);background:var(--panel)}
.ah{padding:18px 16px 14px}.ain{padding:16px}.ain .box{border-radius:8px;background:var(--panel);padding:12px}
.ain textarea{font-size:14px;line-height:1.7;padding:4px;min-height:80px}
.ain .abar{padding-top:10px}.ain .foot{margin-top:10px}
.m-u{background:var(--blue-s);border-radius:10px 10px 2px 10px;padding:12px 14px}
.cite{background:var(--panel);border-radius:6px;padding:10px}
#astOpen{display:none!important} /* The always-visible header control is the single assistant entry. */
body.ast-on #ast{z-index:21}
.atl{--a-bg:#1B2C24;--a-panel:#243A2F;--a-card:#2C4436;--a-line:#425F4B;--a-fg:#E9F0E8;--a-mut:#B3C4B5;--a-gold:#DBD4A2;border-radius:10px}
.atl-cv{background-image:none}.atl-side .tour{background:var(--a-card);border-color:var(--a-line)}
.atl .n.sel .frame,.atl .n.sel circle.core,.atl .n:hover .frame,.atl .n:hover circle.core{filter:none}
.atl .n.pulse .frame,.atl .n.pulse circle.core,.atl .tkring{animation:none}
.atl :focus-visible{outline-color:#DBD4A2;box-shadow:none}

@media(max-width:1450px){#say input{display:none}#top #sayGo{border-radius:5px}#top{gap:12px}#projSel{max-width:210px}.pts .w{display:none}}
@media(max-width:1150px){#top{padding:0 24px;gap:10px}#page{padding-left:24px;padding-right:24px}#top kbd{display:none}#projSel{max-width:190px;min-width:140px}#svc a span{display:none}#top .brand{font-size:14px}}
@media(max-width:950px){
 :root{--shell-height:116px}
 #top,body.svc-reform #top{height:auto;min-height:var(--shell-height);display:grid;grid-template-columns:minmax(0,1fr) auto auto auto;gap:8px;padding:12px 20px}
 #top .brand{grid-column:1/4;grid-row:1;font-size:15px}#account{grid-column:4;grid-row:1;justify-self:end}
 #projSel{grid-column:1;grid-row:2;max-width:none;width:100%;min-width:0}
 #top .pts{grid-column:2;grid-row:2}#say{grid-column:3;grid-row:2}#astToggle{grid-column:4;grid-row:2}#svc{grid-column:1/-1;grid-row:3}#top .sp{display:none}
 #top .me{max-width:160px;white-space:normal;overflow-wrap:anywhere}
 #ast{position:fixed;right:0;top:0;height:100dvh;z-index:21;box-shadow:-8px 0 30px #23352D24;max-width:100%}
 body.ast-on #modal{right:0}
 #page{padding-left:20px;padding-right:20px}.sheet{padding:0}
 .detail,.grid2,.pgrid{grid-template-columns:minmax(0,1fr)}
}
@media(max-width:700px){
 #top{position:relative;padding:12px 16px;gap:8px}#top .brand svg{display:block;width:28px;height:28px}#brandName{display:inline}
 #top .brand{font-size:14px;flex-basis:calc(100% - 120px)}#account{max-width:110px}#top .me{font-size:11px;padding:5px 8px}
 #projSel{font-size:12px;min-height:44px;flex-basis:140px}#top .pts{display:flex!important;min-height:44px;padding:6px;font-size:11px}
 #top #astToggle{display:block;min-height:44px;font-size:12px;padding:8px}#say{display:flex}#top #sayGo{min-height:42px;padding:6px 10px;font-size:20px}#top #sayGo span{display:none}
 #svc{flex:1 1 100%;justify-content:center}#svc a{flex:1;text-align:center;min-height:40px;padding:9px}#svc a span{display:inline}
 #page{padding:0 16px calc(96px + env(safe-area-inset-bottom))}.sheet{padding:0}#main{padding-top:22px}
 #nav5{background:var(--panel);border-top:1px solid var(--line);border-bottom:0}
 #tabs{gap:8px 18px;padding:8px 0}#tabs>a,.tmore>summary{padding:10px 0;font-size:12px}#tabs .tnew{margin-left:0}
 #tabs .tmp{right:0;left:auto}.tmore>summary b{max-width:none}
 h1,.ph h1{font-size:24px}.ph{margin-bottom:20px}.hdr{gap:10px}
 .card,.blk{padding:16px}.grid2,.detail,.kbread{gap:16px}.ph .grow,.hdr .grow{min-width:160px}
 button,a.btn,select,input:not([type=checkbox]):not([type=radio]),summary{min-height:44px}
 button,a.btn{padding:10px 12px}.seg{max-width:100%;flex-wrap:wrap}.seg button{flex:1;white-space:nowrap}
 .props select,.props input{min-height:36px}.props{gap:8px 12px}
 .row{gap:10px}.row>button,.row>.btn{max-width:100%;white-space:normal}
 #modal{padding:12px;align-items:flex-start}.mbox{padding:20px 16px;border-radius:10px}.mbox>.mx{top:8px;right:8px;width:44px;min-height:44px}
 .mbox>#mbody>h2:first-child{font-size:20px;padding-right:40px;margin-bottom:20px}
 #toast{bottom:calc(84px + env(safe-area-inset-bottom));max-width:calc(100vw - 32px);width:max-content;font-size:13px}
 #ast{width:100%;max-width:100%;top:0;height:100dvh}.ain{padding-bottom:calc(16px + env(safe-area-inset-bottom))}
 .band{padding:18px 16px}.gauges{grid-template-columns:minmax(0,1fr)}.gauge{gap:16px}
 .ttabs{gap:18px}.md table{max-width:100%}
 .atl{min-height:440px}.atl-q input{max-width:100%;width:100%}.atl-q{min-width:0;flex:1 1 100%}
}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
"""
