"""A shared, compact screen treatment for the three cutting workstations."""


def style_page(page: str) -> str:
    return page.replace("</head>", STYLE + "</head>", 1)


STYLE = r'''<style>
.cp-edge-tag{display:inline-flex;align-items:center;flex-shrink:0;width:fit-content;max-width:100%;padding:2px 5px;border:1px solid #c5dbc9;border-radius:5px;background:#eef6ee;color:#28613c;font:800 .65rem/1.4 Manrope,sans-serif;white-space:nowrap;vertical-align:middle}.cp-edge-tag[hidden]{display:none!important}.cp-edge-tag[data-status="ambiguous"],.cp-edge-tag[data-status="unknown"]{background:#fff5e8;border-color:#edd5af;color:#8a591d}.cw-item[data-complete="true"] .cp-edge-tag{background:#ffffff26;color:#fff;border-color:#ffffff50}.cw-pallet-line .cp-edge-tag,.cw-sent-item .cp-edge-tag{display:inline-flex;margin:0 0 0 6px;font-size:.65rem}
.cp-process-time{display:block;margin:0 0 10px;font-size:.75rem;line-height:1.5;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fw-pallet .cp-process-time{margin:8px 0 10px;font-size:.72rem}.cp-history-event time{white-space:nowrap}
.cp-history-tabs{display:flex;gap:5px;margin:0 0 14px}.cp-history-tabs a{padding:10px 18px;border-radius:10px;text-decoration:none;font-weight:800;font-size:.85rem;color:var(--green-dark);background:#eaf0eb}.cp-history-tabs a[aria-current]{background:var(--green);color:#fff}.cp-history-events{display:grid;gap:10px;margin-top:14px}.cp-history-event{padding:16px 18px;min-width:0}.cp-history-event time{display:block;margin-bottom:10px;font-size:.8rem;font-weight:800;color:var(--muted)}.cp-history-row{display:flex;gap:12px;align-items:center;padding:9px 0;border-top:1px solid var(--line)}.cp-history-row>span{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.85rem}.cp-history-row strong{white-space:nowrap;color:var(--green-dark)}.cp-history-row small{color:var(--orange);white-space:nowrap}@media(max-width:479px){.cp-history-row{flex-wrap:wrap}.cp-history-row small{flex-basis:100%}}
.cp-edge-tag[data-approximate="true"][data-status="matched"]{background:#eaf2fa;border-color:#bfd0e5;color:#365b82}
@media screen{
 .cp-page .cp-size-cell::before{display:none!important}.cp-size-heading{display:flex;align-items:center;justify-content:space-between;gap:4px;height:16px;margin-bottom:5px;font-size:.65rem;font-weight:800;line-height:16px;color:var(--muted)}.cp-size-heading>span{flex-shrink:0}.cp-size-heading>.cp-edge-tag{display:block;min-width:0;max-width:calc(100% - 62px);margin:0;padding:0 4px;border:0;font-size:.58rem;line-height:16px;overflow:hidden;text-overflow:ellipsis}

 .cp-page{--ink:#1b2e24;--muted:#65776d;--line:#e1e9e3;--soft:#f0f6f2;background:radial-gradient(ellipse at 20% 0,#eaf3ed 0,transparent 50%),#f5f7f5;-webkit-font-smoothing:antialiased}
 .cp-page .cp-shell{padding-top:16px;padding-bottom:36px}
 .cp-page #editor:focus{outline:none}
 .cp-page .cp-top{padding:14px 18px;margin-bottom:12px;border-radius:17px;border-color:#dfe8e1;background:#ffffffed;box-shadow:0 2px 4px #173b2a03,0 8px 24px #173b2a05}
 .cp-page .cp-mark{width:36px;height:36px;border-radius:11px;background:linear-gradient(140deg,#1b9b64,#107248);box-shadow:inset 0 0 0 6px #ffffff18}
 .cp-page .cp-brand strong{font-size:1rem;letter-spacing:-.02em}.cp-page .cp-brand small{font-size:.7rem;letter-spacing:.02em}.cp-page .cp-back{font-size:.8rem;color:#53695b}
 .cp-page .cp-card{border-color:#dfe8e1;border-radius:18px;box-shadow:0 2px 4px #173b2a03,0 10px 26px #173b2a05}
 .cp-page :is(.cp-view-tabs,.cw-tabs,.fw-tabs){display:flex;gap:4px;padding:4px;margin-bottom:14px;border:1px solid #dfe7e0;border-radius:14px;background:#eaf0eb}
 .cp-page :is(.cp-view-tabs,.cw-tabs,.fw-tabs) a{flex:1;display:flex;align-items:center;justify-content:center;min-height:44px;padding:9px 12px;border:1px solid transparent;border-radius:10px;background:transparent;color:#64796b;font-size:.83rem;transition:background .15s,color .15s,box-shadow .15s}
 .cp-page :is(.cp-view-tabs,.cw-tabs,.fw-tabs) a[aria-current]{background:#fff;color:var(--green-dark);border-color:#dbe6de;box-shadow:0 2px 5px #173b2a09}
 .cp-page :is(.cp-overview-head,.cw-toolbar,.fw-toolbar){padding:18px 20px}
 .cp-page .cp-overview-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:center}
 .cp-page :is(.cp-overview-head h1,.cw-toolbar h1,.fw-toolbar h1){font-size:1.3rem;line-height:1.2;letter-spacing:-.025em}
 .cp-page :is(.cp-overview-head p,.cw-toolbar p,.fw-toolbar p){font-size:.8rem;line-height:1.5;margin-top:7px}
 .cp-page .cp-new-day{gap:8px}.cp-page .cp-new-day input{min-width:155px}.cp-page .cp-new-day button{padding:0 14px}
 .cp-page .cp-field>span{font-size:.7rem;color:#586e60;letter-spacing:.01em}
 .cp-page :is(.cp-field input,.cp-field select,.cp-table input,.cp-table select,.cw-pallet-line input,.fw-good input[type="number"]){border-color:#d7e2da;border-radius:10px;background:#fff;font-variant-numeric:tabular-nums;transition:border-color .15s,box-shadow .15s,background .15s}
 .cp-page :is(.cp-field input,.cp-field select,.cp-table input,.cp-table select,.fw-good input[type="number"]):focus{border-color:#56a47a;box-shadow:0 0 0 3px #0d8b5510}
 .cp-page :is(.cp-add-plan,.cp-add-row,.cp-print){border-radius:10px;min-height:44px;transition:background .15s,box-shadow .15s}
 .cp-page .cp-add-plan{box-shadow:0 2px 4px #0d8b5510}.cp-page .cp-add-row{background:#edf4ef;border:1px solid #e0ebe3;color:#276043}
 .cp-page .cp-create{padding:16px 18px;border-radius:16px;margin-top:12px}.cp-page .cp-editor-back{margin-bottom:12px}.cp-page .cp-editor-actions{margin-top:14px}
 .cp-page :is(.cp-plan-head,.cw-colour-head){padding:12px 16px;background:linear-gradient(115deg,#183d2d,#28593f)}
 .cp-page :is(.cp-plan-title h2,.cw-colour-head h2){font-size:1.13rem;line-height:1.25;letter-spacing:-.015em}
 .cp-page .cp-plan-title p{font-size:.7rem;color:#d4e3d9}.cp-page .cp-head-total{border:1px solid #ffffff19;background:#ffffff10}
 .cp-page .cp-collapse-toggle{background:#ffffff0d;border-color:#ffffff24;border-radius:10px}
 .cp-page .cp-remove-plan{min-height:40px;padding:8px 10px;border-color:#ffffff25;background:#ffffff08;font-size:.72rem}
 .cp-page .cp-remove-plan:disabled{opacity:.4;cursor:default}
 .cp-page :is(.cp-subplan-head,.cw-subplan>h3){min-height:44px;padding-top:10px;padding-bottom:10px;background:#eff5f0;border-bottom:1px solid #e2ece5}
 .cp-page :is(.cp-subplan-head strong,.cw-subplan>h3){font-size:.85rem}
 .cp-page :is(.cp-offcut-panel .cp-subplan-head,.cw-offcut-panel>h3){background:#fbf4eb;border-bottom-color:#f0e5d7;color:#a56b32}
 .cp-page :is(.cp-subplan+.cp-subplan,.cw-offcut-panel){border-left-color:#efdfcb;background:#fffcf8}
 .cp-page .cp-subtable tr{padding-top:10px;padding-bottom:10px}
 .cp-page :is(.cp-table input:disabled,.cp-table select:disabled){background:#f0f3f1;border-color:#e3e9e4;color:#7b8b80}
 .cp-page .cp-remove-row{border-radius:9px;background:#fbefed;color:#ad6357}.cp-page .cp-remove-row:disabled{opacity:.55;cursor:default}
 .cp-page :is(.cp-subplan-empty,.cw-panel-empty){color:#829087;font-size:.76rem}
 .cp-page .cw-item{padding-top:10px;padding-bottom:10px;border-top-color:#e3ebe5;border-radius:7px}
 .cp-page .cw-item[data-complete="true"]{box-shadow:inset 3px 0 #096b43}
 .cp-page .cp-main-table tr[data-board-parent="true"],.cp-page .cw-item[data-board-parent="true"]{margin-top:8px;border:1px solid #c7dbce;border-left:3px solid var(--green);border-bottom:0;border-radius:10px 10px 0 0}
 .cp-page .cp-main-table tr[data-parent-row-id],.cp-page .cw-item[data-parent-row-id]{position:relative;margin-top:0;border:0;border-left:3px solid var(--green);border-right:1px solid #c7dbce;border-radius:0;padding-left:24px}
 .cp-page .cp-main-table tr[data-parent-row-id]::after,.cp-page .cw-item[data-parent-row-id]::after{content:'';position:absolute;left:24px;right:8px;top:0;height:1px;background:#e0eae3;pointer-events:none}
 .cp-page .cp-main-table tr[data-group-end="true"],.cp-page .cw-item[data-group-end="true"]{border-bottom:1px solid #c7dbce;border-radius:0 0 10px 10px;margin-bottom:8px}
 .cp-page .cp-main-table tr[data-board-parent="true"],.cp-page .cp-main-table tr[data-parent-row-id]{background:#f5f9f6}
 .cp-page .cw-item[data-board-parent="true"]:not([data-complete="true"]),.cp-page .cw-item[data-parent-row-id]:not([data-complete="true"]){background:#f5f9f6}
 .cp-page .cp-main-table tr[data-parent-row-id] .cp-size-cell::before{content:'Méret (mm)'}
 .cp-page .cw-item[data-parent-row-id] .cw-size::before{display:none}
 .cp-page :is(.cw-size,.cw-board-count,.cw-piece-count,.cp-card-total){font-variant-numeric:tabular-nums}
 .cp-page .cw-batch-state{border-radius:7px;font-size:.7rem}
 .cp-page .cw-pallet{border-color:#ceddd2;border-radius:18px;box-shadow:0 6px 15px #153b2a08,0 22px 60px #153b2a20}
 .cp-page .cw-pallet-handle{background:#1c4431;padding:10px 14px}.cp-page .cw-pallet-handle strong{font:700 .95rem Manrope,sans-serif;letter-spacing:-.01em}
 .cp-page .cw-pallet-handle button{background:#ffffff10;border-radius:9px}.cp-page .cw-pallet-line{border-bottom-color:#e8eee9}.cp-page .cw-pallet-line strong{font-size:.78rem}
 .cp-page .cw-pallet-total{font-size:.75rem;color:#64796b}.cp-page .cw-sent{padding:16px 18px}.cp-page .cw-sent>summary{font-size:.8rem;color:#5e7566}
 .cp-page .fw-card{padding:17px}.cp-page .fw-ready{border-radius:8px;background:#edf5ef}.cp-page .fw-check{padding-top:14px;padding-bottom:14px}
 .cp-page .cp-day-grid{grid-template-columns:minmax(0,1fr);gap:8px;margin-top:12px}
 .cp-page .cp-day-card{display:grid;grid-template-columns:minmax(115px,.85fr) minmax(80px,.55fr) minmax(0,1.8fr) 24px;align-items:center;gap:3px 12px;padding:13px 16px;border-radius:14px;box-shadow:0 2px 4px #173b2a03}
 .cp-page .cp-card-date{grid-column:1;grid-row:1;font-size:1rem;align-self:end;white-space:nowrap;letter-spacing:-.025em}
 .cp-page .cp-card-weekday{grid-column:1;grid-row:2;margin:0;font-size:.7rem;align-self:start}
 .cp-page #workerDays .cp-card-date{grid-row:1/span 2;align-self:center}
 .cp-page .cp-card-total{grid-column:2;grid-row:1/span 2;margin:0;font-size:.72rem;line-height:1.5}.cp-page .cp-card-total strong{font-size:1.15rem}
 .cp-page .cp-card-colours{grid-column:3;grid-row:1/span 2;display:flex;flex-wrap:wrap;gap:5px;border:0;padding:0}
 .cp-page .cp-card-colour{display:flex;align-items:center;gap:7px;padding:4px 7px;background:#f1f6f2;border:1px solid #e5eee7;border-radius:7px;font-size:.7rem;line-height:1.35}
 .cp-page .cp-card-open{grid-column:4;grid-row:1/span 2;padding:0;margin:0;font-size:0;text-align:right}.cp-page .cp-card-open::after{content:'→';font-size:1.2rem;color:#609275}
 .cp-page .fw-card{padding:0;overflow:hidden;border-color:#d8e5dc;border-top:2px solid #81ad92;border-radius:14px;box-shadow:0 2px 4px #173b2a04,0 6px 16px #173b2a06;transition:border-color .16s,box-shadow .16s,transform .16s}
 .cp-page .fw-card .fw-pallet{display:flex;flex-direction:column;align-items:stretch;padding:10px;height:100%;border-radius:0;background:#fff}
 .cp-page .fw-card h2{margin:-14px -14px 8px;padding:12px 14px;border-bottom:1px solid #e4ede7;background:linear-gradient(115deg,#f1f7f3,#fafcfb);color:#315943;font-size:.79rem;line-height:1.55;letter-spacing:-.01em;font-variant-numeric:tabular-nums}
 .cp-page .fw-card h2 time{font:inherit;margin:0}
 .cp-page .fw-card .fw-item{align-items:center;gap:7px;margin-top:0;padding:10px 0;border-top:0;border-bottom:1px solid #edf2ee;font-size:.76rem;color:#425e4c}
 .cp-page .fw-card .fw-item:last-child{border-bottom:0;padding-bottom:0}
 .cp-page .fw-card .fw-item strong{padding:3px 6px;border:1px solid #e0ebe3;border-radius:6px;background:#f0f6f2;color:#245c3b;font-size:.7rem;line-height:1.3;font-variant-numeric:tabular-nums}
 .cp-page .fw-card .cp-process-time{margin:0 0 4px;font-size:.69rem;color:#6b7e70}
 .cp-page .fw-card .fw-pallet:focus-visible{outline:3px solid var(--green);outline-offset:-3px}
 .cp-page .fw-grid{grid-auto-rows:132px;gap:10px}.cp-page .fw-card .fw-card-head{display:block;flex:0 0 52px;height:52px;margin:-10px -10px 0;padding:8px 10px;border-bottom:1px solid #e4ede7;background:linear-gradient(115deg,#f1f7f3,#fafcfb);overflow:hidden}
 .cp-page .fw-card .fw-card-head h2{margin:0;padding:0;border:0;background:none;font-size:.73rem;line-height:1.4}.cp-page .fw-card .fw-card-head .cp-process-time{margin:3px 0 0;font-size:.65rem}
 .cp-page .fw-card-items{display:block;flex:0 0 34px;height:34px;margin-top:2px;overflow:hidden}.cp-page .fw-card .fw-card-items .fw-item{height:34px;padding:5px 0;font-size:.73rem}.cp-page .fw-card .fw-card-items .fw-item:last-child{padding-bottom:5px}
 .cp-page .fw-card-more{display:flex;align-items:center;flex:0 0 18px;min-height:18px;margin-top:auto;padding-top:0;font-size:.66rem;font-weight:800;color:#407752;white-space:nowrap}
 .cp-page .cp-day-card{border-color:#d8e5dc;box-shadow:0 3px 10px #173b2a05;transition:border-color .16s,box-shadow .16s,background .16s}
 .cp-page .cp-card-date{color:#28553b;font-weight:800}.cp-page .cp-card-open::after{display:inline-flex;align-items:center;justify-content:center;width:27px;height:30px;border-radius:8px;background:#edf5ef}
 .cp-page .cp-history-event{border-left:3px solid #a5c6af;box-shadow:0 3px 12px #173b2a05}.cp-page .cp-history-event time{font-size:.75rem;color:#52705b}
 .cp-page .history-card{padding:0;border-left:1px solid #d8e5dc}.cp-page .history-card .fw-card-head{flex-basis:64px;height:64px}.cp-page .history-card .fw-card-head h2{font-size:.7rem;line-height:1.35}.cp-page .history-card .fw-card-head time{margin:0;font:inherit}.cp-page .history-card .fw-card-head .cp-process-time{margin-top:2px;font-size:.64rem;line-height:1.35}.cp-page .history-card .fw-card-head h2 .cp-process-time{margin:0;font:inherit}
 @media(hover:hover) and (pointer:fine){.cp-page :is(.cp-view-tabs,.cw-tabs,.fw-tabs) a:hover{background:#ffffff80;color:#285f41}.cp-page .cp-day-card:hover{border-color:#9bbda6;background:#fcfefc;box-shadow:0 5px 16px #173b2a0c}.cp-page .fw-card:hover{border-color:#9bbda6;box-shadow:0 5px 10px #173b2a07,0 14px 28px #173b2a0c;transform:translateY(-2px)}.cp-page .cp-add-plan:hover{background:#0b7d4c}.cp-page .cp-collapse-toggle:hover{background:#ffffff20}}
 @media(max-width:560px){.cp-page .cp-top{padding:12px 14px}.cp-page .cp-overview-head{grid-template-columns:1fr;padding:16px;gap:12px}.cp-page .cp-new-day{flex-wrap:nowrap}.cp-page .cp-new-day .cp-field{flex-basis:auto;min-width:0}.cp-page .cp-new-day input{min-width:0}.cp-page .cp-new-day button{flex-shrink:0}.cp-page .cp-day-card{grid-template-columns:minmax(100px,1fr) minmax(80px,1fr) 22px;gap:3px 10px;padding:12px 14px}.cp-page .cp-card-colours{grid-column:1/-1;grid-row:3;margin-top:5px}.cp-page .cp-card-open{grid-column:3}.cp-page :is(.cp-view-tabs,.cw-tabs,.fw-tabs) a{padding:9px 7px;font-size:.76rem}}
 @media(prefers-reduced-motion:reduce){.cp-page *{transition:none!important;scroll-behavior:auto!important}}
}
</style>'''
