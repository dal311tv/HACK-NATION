<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#0d1014">
  <title>CRUCIBLE Mission Control</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0d1014; --panel: #151a20; --panel-2: #1b2129; --line: #2a323c; --muted: #95a0ae; --text: #eef2f6;
      --accent: #b8f28b; --link: #8cc8ff; --warn-bg: #3a2a08; --warn-line: #e0a526; --warn-text: #ffe2a3;
      --fact: #4ade80; --evidence: #60a5fa; --inference: #c4b5fd; --hypothesis: #fbbf24; --result: #2dd4bf; --uncertainty: #f472b6;
      --approval: #e6c35c; --decision: #a78bfa;
      --mono: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; scroll-padding-top: 90px; }
    body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
    a { color: var(--link); }
    button { font: inherit; }
    .wrap { width: min(1180px, 100%); margin: 0 auto; padding: 0 16px; }

    /* Example-data banner: sticky so it stays visible while scrolling. */
    .example-banner { position: sticky; top: 0; z-index: 50; background: repeating-linear-gradient(135deg, #7a1010 0 14px, #5c0b0b 14px 28px); color: #fff; text-align: center; font-weight: 800; letter-spacing: .08em; padding: 9px 16px; border-bottom: 2px solid #ff6b6b; }
    .example-banner[hidden] { display: none; }

    /* a. Mission header */
    .topbar { position: sticky; top: 0; z-index: 40; background: rgba(13,16,20,.92); backdrop-filter: blur(8px); border-bottom: 1px solid var(--line); }
    body.has-example .topbar { top: 42px; }
    .topbar .wrap { display: flex; align-items: center; gap: 18px; min-height: 52px; flex-wrap: wrap; }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 800; letter-spacing: .12em; }
    .brand .logo { width: 26px; height: 26px; border-radius: 7px; background: var(--accent); color: #11160d; display: grid; place-items: center; font-size: 14px; }
    .topbar nav { display: flex; gap: 14px; font-size: 13px; }
    .topbar nav a { color: var(--muted); text-decoration: none; }
    .topbar nav a:hover { color: var(--text); }
    .status { margin-left: auto; display: flex; align-items: center; gap: 12px; font-size: 12px; color: var(--muted); }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--fact); display: inline-block; margin-right: 6px; }
    .dot.err { background: #f87171; }
    .chat-link { font-size: 12px; color: var(--muted); border: 1px solid var(--line); border-radius: 999px; padding: 3px 10px; text-decoration: none; }
    .chat-link:hover { color: var(--text); border-color: var(--muted); }

    .mission { padding: 34px 0 10px; }
    .mission .eyebrow { font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); }
    .mission h1 { margin: 4px 0 14px; font-size: clamp(30px, 5vw, 44px); letter-spacing: .06em; }
    .question { background: var(--panel); border: 1px solid var(--line); border-left: 4px solid var(--accent); border-radius: 10px; padding: 14px 18px; }
    .question .q-label { font-size: 12px; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); margin-bottom: 6px; }
    .question .q-text { font-size: 17px; white-space: pre-wrap; overflow-wrap: anywhere; }
    .question .q-text.clamped { max-height: 7.6em; overflow: hidden; -webkit-mask-image: linear-gradient(#000 60%, transparent); mask-image: linear-gradient(#000 60%, transparent); }
    .question .q-meta { margin-top: 8px; font-size: 13px; color: var(--muted); }
    .meta-row { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-top: 12px; font-size: 13px; color: var(--muted); }
    .meta-row b { color: var(--text); font-weight: 600; }

    section.block { padding: 30px 0 8px; }
    section.block > h2 { font-size: 13px; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); margin: 0 0 14px; display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
    section.block > h2 .count { letter-spacing: 0; text-transform: none; font-weight: 400; }
    .notice { font-size: 13px; color: var(--warn-text); }

    /* b. Filters */
    .filters { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; display: grid; gap: 10px; margin-bottom: 18px; }
    .filter-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
    .filter-row .f-title { font-size: 12px; color: var(--muted); width: 52px; text-transform: uppercase; letter-spacing: .08em; }
    .chip { border: 1px solid var(--line); background: var(--panel-2); color: var(--text); border-radius: 999px; padding: 3px 11px; font-size: 12.5px; cursor: pointer; }
    .chip[aria-pressed="true"] { background: var(--text); color: var(--bg); border-color: var(--text); }
    .chip .n { opacity: .6; margin-left: 4px; }
    .chip.clear { background: transparent; color: var(--muted); }

    /* Timeline */
    .timeline { list-style: none; margin: 0; padding: 0 0 0 22px; position: relative; }
    .timeline::before { content: ""; position: absolute; left: 6px; top: 6px; bottom: 6px; width: 2px; background: var(--line); }
    .entry { position: relative; margin: 0 0 14px; }
    .entry::before { content: ""; position: absolute; left: -21px; top: 18px; width: 12px; height: 12px; border-radius: 50%; background: var(--bg); border: 2px solid var(--lc, var(--muted)); }
    .entry[hidden] { display: none; }
    .card { background: var(--panel); border: 1px solid var(--line); border-left: 5px solid var(--lc, var(--muted)); border-radius: 10px; padding: 12px 16px 12px 14px; transition: box-shadow .3s; }
    .entry.flash .card { box-shadow: 0 0 0 3px var(--accent); }
    .card-head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
    .eid { font-family: var(--mono); font-weight: 700; font-size: 14px; color: var(--text); text-decoration: none; }
    .eid:hover { text-decoration: underline; }
    .badge { font-size: 11px; font-weight: 700; letter-spacing: .06em; border-radius: 4px; padding: 1px 7px; text-transform: uppercase; }
    .type-badge { background: #262e38; color: #c9d1db; font-weight: 600; text-transform: none; letter-spacing: 0; font-family: var(--mono); }
    .agent { font-size: 12.5px; color: var(--muted); }
    .conf { font-size: 12.5px; color: var(--muted); font-family: var(--mono); }
    .ts { margin-left: auto; font-size: 12px; color: var(--muted); font-family: var(--mono); }
    .ex-tag { background: #7a1010; color: #fff; }
    .text { margin: 9px 0 4px; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14.5px; }
    .text.clamped { max-height: 9.2em; overflow: hidden; -webkit-mask-image: linear-gradient(#000 65%, transparent); mask-image: linear-gradient(#000 65%, transparent); }
    .more { background: none; border: 0; color: var(--link); cursor: pointer; padding: 0; font-size: 13px; }
    .refs { display: grid; gap: 4px; margin-top: 8px; font-size: 13px; }
    .refs .r-title { color: var(--muted); margin-right: 6px; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
    .refs a, .refs span.cite { overflow-wrap: anywhere; margin-right: 10px; }
    .parent-link { font-family: var(--mono); font-size: 12.5px; text-decoration: none; border: 1px solid var(--line); border-radius: 4px; padding: 0 6px; margin-right: 6px; display: inline-block; }
    .parent-link:hover { border-color: var(--link); }
    .parent-link.missing { color: var(--muted); text-decoration: line-through; border-style: dashed; }
    details.payload { margin-top: 8px; font-size: 13px; }
    details.payload summary { cursor: pointer; color: var(--muted); }
    details.payload pre { background: #0a0d10; border: 1px solid var(--line); border-radius: 8px; padding: 10px; overflow: auto; max-height: 420px; font: 12px/1.45 var(--mono); white-space: pre-wrap; overflow-wrap: anywhere; }

    /* Label styles: every label has its own badge and colour. */
    .l-FACT { --lc: var(--fact); }
    .l-EVIDENCE { --lc: var(--evidence); }
    .l-INFERENCE { --lc: var(--inference); }
    .l-HYPOTHESIS { --lc: var(--hypothesis); }
    .l-RESULT { --lc: var(--result); }
    .l-UNCERTAINTY { --lc: var(--uncertainty); }
    .label-badge { background: var(--lc, #555); color: #0b0e12; }
    .label-badge.l-FACT::before { content: "\2714  "; }
    .label-badge.l-EVIDENCE::before { content: "\25A0  "; }
    .label-badge.l-INFERENCE { background: transparent; color: var(--inference); border: 1px solid var(--inference); }
    .label-badge.l-UNCERTAINTY { background: transparent; color: var(--uncertainty); border: 1px dotted var(--uncertainty); }
    .label-badge.l-UNCERTAINTY::before { content: "~ "; }
    /* HYPOTHESIS must never look like FACT or EVIDENCE: hollow dashed badge, dashed card, italic text, "?" marker. */
    .label-badge.l-HYPOTHESIS { background: transparent; color: var(--hypothesis); border: 1px dashed var(--hypothesis); font-style: italic; }
    .label-badge.l-HYPOTHESIS::before { content: "? "; }
    .entry.l-HYPOTHESIS .card { border: 1px dashed var(--hypothesis); border-left: 5px dashed var(--hypothesis); background: repeating-linear-gradient(135deg, rgba(251,191,36,.045) 0 10px, transparent 10px 20px), var(--panel); }
    .entry.l-HYPOTHESIS .text { font-style: italic; }
    .entry.l-HYPOTHESIS::before { border-style: dashed; }
    .entry.l-UNCERTAINTY .card { border-left-style: dotted; }

    /* Type styles: approval, result, decision. */
    .entry.t-approval .card { border: 2px solid var(--approval); border-left: 5px solid var(--approval); background: linear-gradient(90deg, rgba(230,195,92,.12), rgba(230,195,92,.02) 60%), var(--panel); }
    .entry.t-approval .type-badge { background: var(--approval); color: #1d1604; display: inline-flex; gap: 4px; align-items: center; font-weight: 700; }
    .entry.t-approval::before { border-color: var(--approval); background: var(--approval); border-radius: 3px; }
    .lock { width: 13px; height: 13px; flex: none; }
    .entry.t-result .card { background: linear-gradient(180deg, rgba(45,212,191,.11), rgba(45,212,191,.02)), var(--panel); box-shadow: inset 0 0 0 1px rgba(45,212,191,.35); }
    .entry.t-result .type-badge { background: var(--result); color: #04201c; font-weight: 700; }
    .entry.t-result::before { background: var(--result); }
    .entry.t-decision .card { border-top: 4px solid var(--decision); background: linear-gradient(180deg, rgba(167,139,250,.12), rgba(167,139,250,.02) 120px), var(--panel); }
    .entry.t-decision .type-badge { background: var(--decision); color: #160f2b; font-weight: 700; }
    .entry.t-decision::before { border-color: var(--decision); transform: rotate(45deg); border-radius: 2px; }

    /* c. Results */
    .run-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
    .run-tab { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 8px; padding: 6px 14px; cursor: pointer; font-family: var(--mono); font-size: 13px; }
    .run-tab[aria-pressed="true"] { border-color: var(--result); box-shadow: inset 0 0 0 1px var(--result); background: #10221f; }
    .run-tab .latest { font-family: inherit; font-size: 11px; color: var(--muted); margin-left: 6px; }
    .caveat { display: flex; gap: 12px; align-items: flex-start; background: var(--warn-bg); border: 1px solid var(--warn-line); border-left: 6px solid var(--warn-line); color: var(--warn-text); border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; }
    .caveat .icon { font-size: 20px; line-height: 1.2; }
    .caveat strong { display: block; text-transform: uppercase; letter-spacing: .08em; font-size: 12px; }
    .results-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; align-items: start; }
    .results-grid figure { max-width: 860px; }
    .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; min-width: 0; }
    .panel h3 { margin: 0 0 10px; font-size: 14px; }
    .panel h3 small { color: var(--muted); font-weight: 400; }
    figure { margin: 0; }
    figure img { width: 100%; height: auto; display: block; border-radius: 6px; background: #fff; }
    figcaption { font-size: 12px; color: var(--muted); margin-top: 6px; }
    .img-missing { padding: 40px 10px; text-align: center; color: var(--muted); border: 1px dashed var(--line); border-radius: 6px; }
    .table-scroll { overflow-x: auto; }
    table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
    th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
    th { font-size: 11.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 600; white-space: nowrap; }
    td.num { font-family: var(--mono); white-space: nowrap; }
    td .sub { display: block; font-size: 11.5px; color: var(--muted); font-family: var(--mono); }
    .nr { color: var(--muted); font-style: italic; font-family: inherit; }
    .run-meta { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13px; color: var(--muted); margin-bottom: 14px; }
    .run-meta b { color: var(--text); font-weight: 600; }
    .related { font-size: 13px; color: var(--muted); margin-top: 12px; }
    .stack { display: grid; gap: 16px; margin-top: 16px; }
    details.raw summary { cursor: pointer; color: var(--muted); font-size: 13px; margin-top: 10px; }
    details.raw pre { font: 12px/1.45 var(--mono); white-space: pre-wrap; overflow-wrap: anywhere; color: var(--muted); }

    /* d. Acceleration */
    .accel { background: linear-gradient(135deg, rgba(184,242,139,.10), rgba(45,212,191,.05)), var(--panel); border: 1px solid #3c4a33; border-radius: 12px; padding: 18px 20px; }
    .accel-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-top: 12px; }
    .stat { background: rgba(0,0,0,.22); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
    .stat .k { font-size: 12px; color: var(--muted); font-family: var(--mono); overflow-wrap: anywhere; }
    .stat .v { font-size: 28px; font-weight: 700; font-family: var(--mono); margin-top: 2px; }
    .stat .v.nr { font-size: 18px; padding-top: 8px; }
    .stat.primary { border-color: var(--accent); }
    .accel p.src { font-size: 12.5px; color: var(--muted); margin: 6px 0 0; }

    footer { color: var(--muted); font-size: 12px; padding: 30px 0 40px; }
    .empty { color: var(--muted); font-style: italic; }

    @media (max-width: 860px) {
      .ts { margin-left: 0; width: 100%; }
      .status { margin-left: 0; width: 100%; padding-bottom: 8px; }
      body.has-example .topbar { top: 58px; }
    }
  </style>
</head>
<body>
  <div class="example-banner" id="exampleBanner" role="alert" hidden>EXAMPLE DATA - not real results</div>

  <header class="topbar">
    <div class="wrap">
      <div class="brand"><span class="logo">&#9650;</span>CRUCIBLE</div>
      <nav aria-label="Sections">
        <a href="#ledger">Ledger</a>
        <a href="#results">Results</a>
        <a href="#acceleration">Acceleration</a>
      </nav>
      <div class="status">
        <span id="refreshStatus"><span class="dot"></span>Loading&hellip;</span>
        <a class="chat-link" href="chat.php" title="Separate chat page; requires an API key on the server">Chat &rarr;</a>
      </div>
    </div>
  </header>

  <main class="wrap">
    <!-- a. Mission header -->
    <section class="mission" aria-labelledby="missionTitle">
      <div class="eyebrow">Mission Control &middot; read-only research ledger</div>
      <h1 id="missionTitle">CRUCIBLE</h1>
      <div class="question" id="question">
        <div class="q-label" id="questionLabel">Research question</div>
        <div class="q-text" id="questionText"><span class="empty">Loading ledger&hellip;</span></div>
        <button class="more" id="questionMore" type="button" hidden>Show more</button>
        <div class="q-meta" id="questionMeta"></div>
      </div>
      <div class="meta-row" id="ledgerMeta"></div>
    </section>

    <!-- b. Ledger timeline -->
    <section class="block" id="ledger" aria-labelledby="ledgerTitle">
      <h2 id="ledgerTitle">Ledger timeline <span class="count" id="ledgerCount"></span></h2>
      <div class="filters" id="filters">
        <div class="filter-row" id="typeFilters"><span class="f-title">Type</span></div>
        <div class="filter-row" id="labelFilters"><span class="f-title">Label</span></div>
      </div>
      <ol class="timeline" id="timeline"></ol>
    </section>

    <!-- c. Results -->
    <section class="block" id="results" aria-labelledby="resultsTitle">
      <h2 id="resultsTitle">Results</h2>
      <div class="run-tabs" id="runTabs" role="group" aria-label="Select run"></div>
      <div id="resultsBody"><p class="empty">Loading results&hellip;</p></div>
    </section>

    <!-- d. Acceleration -->
    <section class="block" id="acceleration" aria-labelledby="accelTitle">
      <h2 id="accelTitle">Acceleration</h2>
      <div class="accel" id="accelBody"><p class="empty">Loading&hellip;</p></div>
    </section>

    <footer>
      Read-only view. Every number on this page is read from <code>ledger/ledger.jsonl</code> or <code>results/&lt;run_id&gt;/summary.json</code>; nothing is recomputed. Auto-refresh every 15 s.
    </footer>
  </main>

  <script>
  (() => {
    'use strict';

    const REFRESH_MS = 15000;
    const RUN_ID_RE = /^run-[A-Za-z0-9_-]+$/;
    const LABELS = ['FACT', 'EVIDENCE', 'INFERENCE', 'HYPOTHESIS', 'RESULT', 'UNCERTAINTY'];
    const LOCK_SVG = '<svg class="lock" viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M4 7V5a4 4 0 1 1 8 0v2h.5A1.5 1.5 0 0 1 14 8.5v6a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 14.5v-6A1.5 1.5 0 0 1 3.5 7H4Zm2 0h4V5a2 2 0 1 0-4 0v2Z"/></svg>';

    const state = {
      ledgerRaw: '', ledger: null,
      runsRaw: '', runs: [], latestRun: null,
      selectedRun: null, userPickedRun: false,
      summaryRaw: '', summary: null,
      filters: { type: new Set(), label: new Set() },
      expanded: new Set(), openPayloads: new Set(),
      questionExpanded: false,
    };

    const $ = (sel) => document.querySelector(sel);
    function el(tag, props = {}, ...children) {
      const node = document.createElement(tag);
      for (const [k, v] of Object.entries(props)) {
        if (v === undefined || v === null) continue;
        if (k === 'class') node.className = v;
        else if (k === 'text') node.textContent = v;
        else if (k === 'dataset') Object.assign(node.dataset, v);
        else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v);
      }
      for (const c of children) if (c !== null && c !== undefined) node.append(c);
      return node;
    }
    const safeClass = (s) => String(s ?? '').replace(/[^A-Za-z0-9_-]/g, '_');

    // ---- Number display: values are shown as stored, only rounded for display. ----
    function fmt(v, digits) {
      if (v === null || v === undefined) return null;
      if (typeof v !== 'number') return String(v);
      if (Number.isInteger(v)) return String(v);
      const s = String(Number(v.toFixed(digits)));
      return s === '-0' ? '0' : s;
    }
    function numCell(v, digits, nullText = 'not reached') {
      const td = el('td', { class: 'num' });
      if (v === null || v === undefined) {
        td.append(el('span', { class: 'nr', text: v === null ? nullText : 'not in summary' }));
      } else {
        td.textContent = fmt(v, digits);
        td.title = 'Stored value: ' + JSON.stringify(v);
      }
      return td;
    }
    function ciCell(ci, digits) {
      const td = el('td', { class: 'num' });
      if (Array.isArray(ci) && ci.length === 2) {
        td.textContent = '[' + fmt(ci[0], digits) + ', ' + fmt(ci[1], digits) + ']';
        td.title = 'Stored value: ' + JSON.stringify(ci);
      } else {
        td.append(el('span', { class: 'nr', text: ci === null ? 'null' : 'not in summary' }));
      }
      return td;
    }

    // ---- Citations: only http(s) links, DOIs and local result files become links. ----
    function citationNode(c) {
      const s = String(c).trim();
      let href = null;
      if (/^https?:\/\//i.test(s)) href = s;
      else if (/^doi:\s*/i.test(s)) href = 'https://doi.org/' + s.replace(/^doi:\s*/i, '');
      else if (/^10\.\d{4,9}\//.test(s)) href = 'https://doi.org/' + s;
      else {
        const m = s.match(/^results\/(run-[A-Za-z0-9_-]+)\/(summary\.json|recall_curves\.png)$/);
        if (m) href = 'api/results.php?run_id=' + encodeURIComponent(m[1]) + (m[2] === 'recall_curves.png' ? '&image=1' : '');
      }
      if (!href) return el('span', { class: 'cite', text: s });
      return el('a', { href, target: '_blank', rel: 'noopener noreferrer', text: s });
    }

    // ---- Fetch helpers ----
    async function fetchText(url) {
      const res = await fetch(url, { cache: 'no-store' });
      const text = await res.text();
      if (!res.ok) {
        let msg = 'HTTP ' + res.status;
        try { msg = JSON.parse(text).error || msg; } catch (_) {}
        throw new Error(msg);
      }
      return text;
    }

    // =====================================================================
    // Ledger
    // =====================================================================
    function entryAnchor(id) { return 'entry-' + safeClass(id); }

    function isExample(ledger) {
      if (!ledger) return false;
      if (/^example_ledger\.jsonl$/i.test(ledger.source || '')) return true;
      return (ledger.entries || []).some((e) => e && e.example === true);
    }

    function renderBanner() {
      const show = isExample(state.ledger);
      $('#exampleBanner').hidden = !show;
      document.body.classList.toggle('has-example', show);
    }

    function renderQuestion(entries) {
      const textEl = $('#questionText'), metaEl = $('#questionMeta'), labelEl = $('#questionLabel'), moreBtn = $('#questionMore');
      const preregs = entries.filter((e) => e.type === 'preregistration');
      textEl.replaceChildren(); metaEl.replaceChildren(); moreBtn.hidden = true; textEl.classList.remove('clamped');
      if (!preregs.length) {
        labelEl.textContent = 'Research question';
        textEl.append(el('span', { class: 'empty', text: 'No preregistration entry in the ledger yet.' }));
        return;
      }
      // Prefer an explicit question written in a preregistration text, newest first.
      for (const p of [...preregs].reverse()) {
        const t = String(p.text || '');
        const m = t.match(/research question[^(?]*\(([^()]*\?)\)/i) || t.match(/research question\s*[:\-]\s*([^\n]*?\?)/i);
        if (m) {
          labelEl.textContent = 'Research question';
          textEl.textContent = m[1].trim();
          metaEl.append('From preregistration ', parentLink(p.id, true));
          return;
        }
      }
      // Otherwise show the latest preregistration text itself.
      const p = preregs[preregs.length - 1];
      labelEl.textContent = 'Current preregistration';
      textEl.textContent = String(p.text || '');
      if (textEl.textContent.length > 420) {
        if (!state.questionExpanded) textEl.classList.add('clamped');
        moreBtn.hidden = false;
        moreBtn.textContent = state.questionExpanded ? 'Show less' : 'Show more';
      }
      metaEl.append('Source: ', parentLink(p.id, true));
      const pm = p.payload && p.payload.primary_metric;
      if (typeof pm === 'string' && pm) metaEl.append(' · Primary metric: ' + pm);
    }
    $('#questionMore').addEventListener('click', () => {
      state.questionExpanded = !state.questionExpanded;
      $('#questionText').classList.toggle('clamped', !state.questionExpanded);
      $('#questionMore').textContent = state.questionExpanded ? 'Show less' : 'Show more';
    });

    function renderLedgerMeta(ledger) {
      const meta = $('#ledgerMeta');
      meta.replaceChildren();
      const add = (k, v) => meta.append(el('span', {}, k + ' ', el('b', { text: v })));
      add('Source:', 'ledger/' + (ledger.source || '?'));
      add('Entries:', String(ledger.entries.length));
      if (ledger.invalid_lines) meta.append(el('span', { class: 'notice', text: ledger.invalid_lines + ' invalid line(s) skipped' }));
      const last = ledger.entries[ledger.entries.length - 1];
      if (last && last.timestamp) add('Last entry:', String(last.timestamp));
    }

    let knownIds = new Set();
    function parentLink(id, exists = knownIds.has(id)) {
      const a = el('a', { class: 'parent-link' + (exists ? '' : ' missing'), href: '#' + entryAnchor(id), text: String(id) });
      if (!exists) a.title = 'Not found in this ledger';
      a.addEventListener('click', (ev) => { ev.preventDefault(); if (exists) goToEntry(id); });
      return a;
    }

    function goToEntry(id) {
      const node = document.getElementById(entryAnchor(id));
      if (!node) return;
      if (node.hidden) { state.filters.type.clear(); state.filters.label.clear(); renderFilters(); applyFilters(); }
      node.scrollIntoView({ behavior: 'smooth', block: 'center' });
      history.replaceState(null, '', '#' + entryAnchor(id));
      node.classList.remove('flash'); void node.offsetWidth; node.classList.add('flash');
      setTimeout(() => node.classList.remove('flash'), 1800);
    }

    function renderEntry(e) {
      const id = String(e.id ?? '(no id)');
      const label = String(e.label ?? '');
      const type = String(e.type ?? '');
      const li = el('li', {
        class: 'entry l-' + safeClass(label) + ' t-' + safeClass(type),
        id: entryAnchor(id),
        dataset: { type, label },
      });
      const card = el('article', { class: 'card' });

      const typeBadge = el('span', { class: 'badge type-badge' });
      if (type === 'approval') typeBadge.innerHTML = LOCK_SVG; // static markup only
      typeBadge.append(type || 'unknown type');
      if (type === 'approval') typeBadge.title = 'Approval';

      const head = el('div', { class: 'card-head' },
        el('a', { class: 'eid', href: '#' + entryAnchor(id), text: id, onclick: (ev) => { ev.preventDefault(); goToEntry(id); } }),
        typeBadge,
        el('span', { class: 'badge label-badge l-' + safeClass(label), text: label || 'NO LABEL', title: 'Epistemic label' }),
        el('span', { class: 'agent', text: 'by ' + String(e.agent ?? 'unknown') }),
      );
      if (typeof e.confidence === 'number') head.append(el('span', { class: 'conf', text: 'confidence ' + e.confidence, title: 'Stored confidence (0-1)' }));
      if (e.example === true) head.append(el('span', { class: 'badge ex-tag', text: 'EXAMPLE' }));
      if (e.timestamp) head.append(el('span', { class: 'ts', text: String(e.timestamp), title: e.hash ? 'hash ' + e.hash : null }));
      card.append(head);

      const text = String(e.text ?? '');
      const textEl = el('div', { class: 'text', text });
      card.append(textEl);
      if (text.length > 600) {
        const open = state.expanded.has(id);
        if (!open) textEl.classList.add('clamped');
        const btn = el('button', { class: 'more', type: 'button', text: open ? 'Show less' : 'Show more' });
        btn.addEventListener('click', () => {
          const nowOpen = !state.expanded.has(id);
          nowOpen ? state.expanded.add(id) : state.expanded.delete(id);
          textEl.classList.toggle('clamped', !nowOpen);
          btn.textContent = nowOpen ? 'Show less' : 'Show more';
        });
        card.append(btn);
      }

      const refs = el('div', { class: 'refs' });
      const cits = Array.isArray(e.citations) ? e.citations : [];
      if (cits.length) refs.append(el('div', {}, el('span', { class: 'r-title', text: 'Citations' }), ...cits.map(citationNode)));
      const parents = Array.isArray(e.parents) ? e.parents : [];
      if (parents.length) refs.append(el('div', {}, el('span', { class: 'r-title', text: 'Parents' }), ...parents.map((p) => parentLink(String(p)))));
      if (refs.childNodes.length) card.append(refs);

      if (e.payload !== undefined && e.payload !== null) {
        const det = el('details', { class: 'payload' }, el('summary', { text: 'Payload' }), el('pre', { text: JSON.stringify(e.payload, null, 2) }));
        det.open = state.openPayloads.has(id);
        det.addEventListener('toggle', () => { det.open ? state.openPayloads.add(id) : state.openPayloads.delete(id); });
        card.append(det);
      }

      li.append(card);
      return li;
    }

    function countBy(entries, key) {
      const m = new Map();
      for (const e of entries) { const k = String(e[key] ?? ''); m.set(k, (m.get(k) || 0) + 1); }
      return m;
    }

    function renderFilters() {
      const entries = state.ledger ? state.ledger.entries : [];
      const build = (rowSel, key, order) => {
        const row = $(rowSel);
        row.querySelectorAll('.chip').forEach((n) => n.remove());
        const counts = countBy(entries, key);
        const keys = [...counts.keys()].sort((a, b) => {
          const ia = order ? order.indexOf(a) : -1, ib = order ? order.indexOf(b) : -1;
          if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
          return a.localeCompare(b);
        });
        const set = state.filters[key];
        for (const k of [...set]) if (!counts.has(k)) set.delete(k);
        for (const k of keys) {
          const chip = el('button', { class: 'chip', type: 'button', 'aria-pressed': String(set.has(k)) }, k || '(none)', el('span', { class: 'n', text: String(counts.get(k)) }));
          chip.addEventListener('click', () => { set.has(k) ? set.delete(k) : set.add(k); renderFilters(); applyFilters(); });
          row.append(chip);
        }
        if (set.size) {
          const clear = el('button', { class: 'chip clear', type: 'button', text: 'clear' });
          clear.addEventListener('click', () => { set.clear(); renderFilters(); applyFilters(); });
          row.append(clear);
        }
      };
      build('#typeFilters', 'type', null);
      build('#labelFilters', 'label', LABELS);
    }

    function applyFilters() {
      const { type, label } = state.filters;
      let shown = 0, total = 0;
      for (const li of document.querySelectorAll('#timeline > .entry')) {
        total++;
        const ok = (!type.size || type.has(li.dataset.type)) && (!label.size || label.has(li.dataset.label));
        li.hidden = !ok;
        if (ok) shown++;
      }
      $('#ledgerCount').textContent = shown === total ? total + ' entries, file order' : 'showing ' + shown + ' of ' + total;
    }

    function renderLedger() {
      const ledger = state.ledger;
      renderBanner();
      const entries = ledger.entries.filter((e) => e && typeof e === 'object');
      knownIds = new Set(entries.map((e) => String(e.id)));
      renderQuestion(entries);
      renderLedgerMeta(ledger);
      const list = $('#timeline');
      list.replaceChildren(...entries.map(renderEntry));
      if (!entries.length) list.append(el('li', { class: 'empty', text: 'The ledger has no entries yet.' }));
      renderFilters();
      applyFilters();
      // Results section links to ledger entries citing the run; refresh those links too.
      if (state.summary) renderResults();
    }

    async function loadLedger() {
      const raw = await fetchText('api/ledger.php');
      if (raw === state.ledgerRaw) return;
      const data = JSON.parse(raw);
      if (!Array.isArray(data.entries)) throw new Error('Unexpected ledger response');
      state.ledgerRaw = raw;
      state.ledger = data;
      const firstLoad = !document.querySelector('#timeline > .entry');
      renderLedger();
      if (firstLoad && location.hash.startsWith('#entry-')) {
        const node = document.getElementById(location.hash.slice(1));
        if (node) node.scrollIntoView({ block: 'center' });
      }
    }

    // =====================================================================
    // Results
    // =====================================================================
    function renderRunTabs() {
      const box = $('#runTabs');
      box.replaceChildren();
      if (!state.runs.length) { box.append(el('p', { class: 'empty', text: 'No runs with summary.json found in results/.' })); return; }
      const ordered = [...state.runs].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
      for (const id of ordered) {
        const btn = el('button', { class: 'run-tab', type: 'button', 'aria-pressed': String(id === state.selectedRun) }, id);
        if (id === state.latestRun) btn.append(el('span', { class: 'latest', text: 'latest' }));
        btn.addEventListener('click', () => {
          if (id === state.selectedRun) return;
          state.selectedRun = id; state.userPickedRun = true;
          renderRunTabs();
          loadSummary(true).catch(showError);
        });
        box.append(btn);
      }
    }

    function imageUrl(runId, bust) {
      return 'api/results.php?run_id=' + encodeURIComponent(runId) + '&image=1' + (bust ? '&v=' + bust : '');
    }

    let imageVersion = Date.now();
    function renderResults() {
      const s = state.summary, runId = state.selectedRun;
      const body = $('#resultsBody');
      body.replaceChildren();
      if (!s || !runId) { body.append(el('p', { class: 'empty', text: 'No results available yet.' })); renderAccel(); return; }

      if (s.caveat !== undefined && s.caveat !== null && s.caveat !== '') {
        body.append(el('div', { class: 'caveat', role: 'note' },
          el('span', { class: 'icon', 'aria-hidden': 'true', text: '⚠' }),
          el('div', {}, el('strong', { text: 'Caveat' }), el('span', { text: String(s.caveat) }))));
      }

      const meta = el('div', { class: 'run-meta' });
      const addMeta = (k, v) => { if (v !== undefined && v !== null) meta.append(el('span', {}, k + ' ', el('b', { text: typeof v === 'object' ? JSON.stringify(v) : String(v) }))); };
      addMeta('Run:', s.run_id ?? runId);
      addMeta('Dataset:', s.dataset);
      addMeta('Target:', s.target);
      addMeta('Candidates:', s.n_candidates);
      addMeta('Top set size:', s.top_set_size);
      if (s.protocol && typeof s.protocol === 'object') {
        addMeta('Protocol:', Object.entries(s.protocol).map(([k, v]) => k + '=' + JSON.stringify(v)).join(', '));
      }
      if (s.pairing_check && typeof s.pairing_check.verified === 'boolean') addMeta('Pairing verified:', String(s.pairing_check.verified));
      body.append(meta);

      const grid = el('div', { class: 'results-grid' });

      // Recall curves image
      const fig = el('figure');
      const img = el('img', { src: imageUrl(runId, imageVersion), alt: 'Recall curves for ' + runId, loading: 'lazy' });
      img.addEventListener('error', () => fig.replaceChildren(el('div', { class: 'img-missing', text: 'recall_curves.png is not available for ' + runId + '.' })));
      fig.append(el('a', { href: imageUrl(runId), target: '_blank', rel: 'noopener', title: 'Open full size' }, img),
        el('figcaption', { text: 'results/' + runId + '/recall_curves.png' }));
      grid.append(el('div', { class: 'panel' }, el('h3', {}, 'Recall curves ', el('small', { text: runId })), fig));

      // Arms table
      const armsPanel = el('div', { class: 'panel' }, el('h3', {}, 'Arms ', el('small', { text: 'from summary.json → arms' })));
      const arms = s.arms && typeof s.arms === 'object' ? Object.entries(s.arms) : [];
      if (arms.length) {
        const tbody = el('tbody');
        for (const [name, a] of arms) {
          const spec = a && a.spec ? Object.entries(a.spec).map(([k, v]) => k + '=' + v).join(' · ') : null;
          tbody.append(el('tr', {},
            el('td', {}, el('strong', { text: name }), spec ? el('span', { class: 'sub', text: spec }) : null),
            numCell(a.mean_final_recall, 4, 'null'),
            ciCell(a.final_recall_95ci, 4),
            numCell(a.median_calls_to_50pct, 2, 'not reached'),
            numCell(a.seeds_reaching_50pct, 0, 'null')));
        }
        armsPanel.append(el('div', { class: 'table-scroll' }, el('table', {},
          el('thead', {}, el('tr', {}, ...['Arm', 'mean_final_recall', 'final_recall_95ci', 'median_calls_to_50pct', 'seeds_reaching_50pct'].map((h) => el('th', { text: h })))),
          tbody)));
        armsPanel.append(el('p', { class: 'related', text: 'Values rounded to 4 decimals for display; hover a cell for the stored value.' }));
      } else {
        armsPanel.append(el('p', { class: 'empty', text: 'No arms block in this summary.' }));
      }
      grid.append(armsPanel);
      body.append(grid);

      // Comparisons
      const stack = el('div', { class: 'stack' });
      const compPanel = el('div', { class: 'panel' }, el('h3', {}, 'Comparisons ', el('small', { text: 'from summary.json → comparisons' })));
      const comps = s.comparisons && typeof s.comparisons === 'object' ? Object.entries(s.comparisons) : [];
      if (comps.length) {
        const tbody = el('tbody');
        for (const [name, c] of comps) {
          const wlt = el('td', { class: 'num' });
          const parts = [c.seeds_first_better, c.seeds_second_better, c.ties];
          wlt.textContent = parts.every((x) => x === undefined) ? '—' : parts.map((x) => (x === undefined || x === null ? '?' : String(x))).join(' / ');
          tbody.append(el('tr', {},
            el('td', {}, el('strong', { text: name })),
            el('td', { text: c.metric !== undefined ? String(c.metric) : '—' }),
            numCell(c.mean_difference, 4, 'null'),
            ciCell(c.difference_95ci, 4),
            ciCell(c.difference_90ci, 4),
            wlt,
            numCell(c.n_seeds, 0, 'null')));
        }
        compPanel.append(el('div', { class: 'table-scroll' }, el('table', {},
          el('thead', {}, el('tr', {}, ...['Comparison', 'Metric', 'mean_difference', 'difference_95ci', 'difference_90ci', 'first / second better / ties', 'n_seeds'].map((h) => el('th', { text: h })))),
          tbody)));
        const raw = {};
        for (const [name, c] of comps) if (Array.isArray(c.per_seed_differences)) raw[name] = c.per_seed_differences;
        if (Object.keys(raw).length) {
          compPanel.append(el('details', { class: 'raw' }, el('summary', { text: 'Per-seed differences (as stored)' }), el('pre', { text: JSON.stringify(raw, null, 1) })));
        }
      } else {
        compPanel.append(el('p', { class: 'empty', text: 'No comparisons block in this summary.' }));
      }

      // Ledger entries that cite this run
      const citing = state.ledger ? state.ledger.entries.filter((e) => e && (e.id === runId || (Array.isArray(e.citations) && e.citations.some((c) => String(c).startsWith('results/' + runId + '/'))))) : [];
      if (citing.length) compPanel.append(el('div', { class: 'related' }, 'Ledger entries citing this run: ', ...citing.map((e) => parentLink(String(e.id)))));
      stack.append(compPanel);
      body.append(stack);

      renderAccel();
    }

    // =====================================================================
    // Acceleration (values exactly as stored, rounded to at most 2 decimals)
    // =====================================================================
    function statBox(key, value, primary) {
      const v = value === null
        ? el('div', { class: 'v nr', text: 'not reached' })
        : value === undefined
          ? el('div', { class: 'v nr', text: 'not in summary' })
          : el('div', { class: 'v', text: (typeof value === 'number' ? fmt(value, 2) + '×' : String(value)), title: 'Stored value: ' + JSON.stringify(value) });
      return el('div', { class: 'stat' + (primary ? ' primary' : '') }, el('div', { class: 'k', text: key }), v);
    }

    function renderAccel() {
      const box = $('#accelBody');
      box.replaceChildren();
      const s = state.summary;
      if (!s) { box.append(el('p', { class: 'empty', text: 'No results available yet.' })); return; }

      box.append(el('h3', { style: 'margin:0;font-size:15px' }, 'Speed-up vs random in calls to 50% recall'));
      const grid1 = el('div', { class: 'accel-grid' });
      const sp = s.speedup_vs_random_calls_to_50pct;
      if (sp && typeof sp === 'object') {
        for (const [arm, val] of Object.entries(sp)) grid1.append(statBox('speedup_vs_random_calls_to_50pct.' + arm, val, arm.startsWith('C_')));
      } else {
        grid1.append(statBox('speedup_vs_random_calls_to_50pct', sp === null ? null : undefined));
      }
      box.append(grid1);

      box.append(el('h3', { style: 'margin:18px 0 0;font-size:15px' }, 'C vs B: ratio of calls to 50% recall'));
      const grid2 = el('div', { class: 'accel-grid' });
      grid2.append(statBox('C_vs_B_calls_to_50pct_ratio', s.C_vs_B_calls_to_50pct_ratio, true));
      box.append(grid2);

      box.append(el('p', { class: 'src', text: 'Source: results/' + state.selectedRun + '/summary.json. Shown exactly as stored, rounded to at most 2 decimals; hover for the full stored value. "not reached" means the stored value is null.' }));
    }

    async function loadRuns() {
      const raw = await fetchText('api/results.php');
      if (raw === state.runsRaw) return false;
      const data = JSON.parse(raw);
      state.runsRaw = raw;
      state.runs = (Array.isArray(data.runs) ? data.runs : []).filter((r) => RUN_ID_RE.test(r));
      state.latestRun = RUN_ID_RE.test(data.latest_run || '') ? data.latest_run : null;
      if (!state.userPickedRun || !state.runs.includes(state.selectedRun)) {
        state.selectedRun = state.latestRun;
        state.userPickedRun = false;
      }
      renderRunTabs();
      return true;
    }

    async function loadSummary(force) {
      const runId = state.selectedRun;
      if (!runId) { state.summary = null; state.summaryRaw = ''; renderResults(); return; }
      const raw = await fetchText('api/results.php?run_id=' + encodeURIComponent(runId));
      if (runId !== state.selectedRun) return; // user switched while loading
      if (!force && raw === state.summaryRaw) return;
      state.summaryRaw = raw;
      state.summary = JSON.parse(raw);
      imageVersion = Date.now(); // summary changed (or run switched): reload the image too
      renderResults();
    }

    // =====================================================================
    // Refresh loop
    // =====================================================================
    function setStatus(ok, msg) {
      const s = $('#refreshStatus');
      s.replaceChildren(el('span', { class: 'dot' + (ok ? '' : ' err') }), msg);
    }
    function showError(err) { setStatus(false, 'Refresh failed: ' + (err && err.message ? err.message : err)); }

    let busy = false;
    async function refresh() {
      if (busy) return;
      busy = true;
      try {
        const results = await Promise.allSettled([loadLedger(), loadRuns().then(() => loadSummary(false))]);
        const failed = results.find((r) => r.status === 'rejected');
        if (failed) showError(failed.reason);
        else setStatus(true, 'Updated ' + new Date().toLocaleTimeString() + ' · every 15 s');
      } finally {
        busy = false;
      }
    }

    refresh();
    setInterval(refresh, REFRESH_MS);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  })();
  </script>
</body>
</html>
