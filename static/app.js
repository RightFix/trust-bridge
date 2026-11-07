/* TrustBridge (ClearPay) — no-build frontend */
(() => {
  "use strict";

  const API_KEY = window.TRUSTBRIDGE_API_KEY || "trustbridge-demo-key";
  const state = {
    role: localStorage.getItem("tb_role") || "client",
    jobs: [],
    job: null,
    health: null,
    tab: "spec",
    tabJob: null,
    view: "client",
    flash: null,
    error: null,
    busy: false,
  };

  // ---------- helpers -------------------------------------------------------
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      ...opts,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
        ...(opts.headers || {}),
      },
    });
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
    if (!res.ok) {
      const d = data && data.detail;
      throw new Error(typeof d === "string" ? d : JSON.stringify(d) || `HTTP ${res.status}`);
    }
    return data;
  }

  const post = (path, body) =>
    api(path, { method: "POST", body: JSON.stringify(body || {}) });

  const role = () => state.role;
  const isClient = () => role() === "client";
  const isFreelancer = () => role() === "freelancer";
  const isReviewer = () => role() === "reviewer";

  const STATUS_CLASS = {
    clarifying: "s-mute", spec_ready: "", spec_editing: "s-warn",
    confirmed: "", funded: "", submitted: "", verifying: "",
    human_review: "s-warn", released: "s-ok", refunded: "s-bad",
    changes_requested: "s-warn",
  };

  const STEPS = ["clarifying", "spec_ready", "confirmed", "funded", "submitted", "released"];
  function stepIndex(status) {
    switch (status) {
      case "clarifying": return 0;
      case "spec_ready": case "spec_editing": return 1;
      case "confirmed": return 2;
      case "funded": case "changes_requested": return 3;
      case "submitted": case "verifying": case "human_review": return 4;
      case "released": return 5;
      case "refunded": return 4;
      default: return 0;
    }
  }

  function checkLabel(chk) {
    if (!chk) return "Human judgement (AI + reviewer)";
    switch (chk.type) {
      case "word_count":
        return `word count ${chk.min ?? 0}–${chk.max ?? "∞"}`;
      case "file_type":
        return `file type ${(chk.extensions || []).join(", ")}`;
      case "keywords":
        return `${(chk.mode || "all").toUpperCase()} of: ${(chk.values || []).join(", ")}`;
      case "sections":
        return `sections: ${(chk.values || []).join(", ")}`;
      case "code_tests":
        return "runs the provided test cases (10s limit)";
      default: return chk.type;
    }
  }

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }

  function setFlash(msg) { state.flash = msg; state.error = null; }
  function setError(msg) { state.error = msg; }

  async function run(fn) {
    state.busy = true; state.error = null;
    render();
    try {
      const out = await fn();
      if (out && out.__flash) setFlash(out.__flash);
      return out;
    } catch (e) {
      setError(e.message || String(e));
      return null;
    } finally {
      state.busy = false;
    }
  }

  // ---------- router --------------------------------------------------------
  function route() {
    const h = (location.hash || "#/").replace(/^#/, "");
    const m = h.match(/^\/job\/([\w-]+)/);
    return m ? { view: "job", id: m[1] } : { view: "home" };
  }

  let renderSeq = 0;
  async function render() {
    const seq = ++renderSeq;   // only the latest render may touch the DOM
    renderRoles();
    const app = $("#app");
    const r = route();
    try {
      if (r.view === "job") {
        const job = await api(`/api/jobs/${r.id}`);
        if (seq !== renderSeq) return;
        state.job = job;
        app.innerHTML = jobHTML(job);
        bindJob();
      } else {
        const data = await api("/api/jobs");
        if (seq !== renderSeq) return;
        state.jobs = data.jobs;
        if (!state.health) state.health = await api("/api/health").catch(() => null);
        if (seq !== renderSeq) return;
        app.innerHTML = homeHTML();
        bindHome();
      }
    } catch (e) {
      if (seq !== renderSeq) return;
      app.innerHTML = `<div class="error">Failed to load: ${esc(e.message)}</div>`;
    }
  }

  function renderRoles() {
    $$("#roles button").forEach((b) =>
      b.classList.toggle("active", b.dataset.role === state.role));
  }

  // ---------- home ----------------------------------------------------------
  function homeHTML() {
    const prov = state.health ? state.health.llm_provider : "?";
    const provLabel = prov === "mock"
      ? "offline deterministic mode (no API key set)"
      : `${prov} (LLM_API_KEY from environment)`;
    const jobs = state.jobs.map((j) => {
      const held = j.ledger.reduce((s, e) =>
        s + (e.kind === "FUND" ? e.amount_usdt : -e.amount_usdt), 0);
      return `
        <a class="job-card" href="#/job/${esc(j.id)}">
          <h3>${esc(j.title)}</h3>
          <p>${esc(j.brief)}</p>
          <div class="job-meta">
            <span class="chip ${STATUS_CLASS[j.status] || ""}">${esc(j.status_label)}</span>
            <span class="badge src">${j.spec ? j.spec.checklist.length : 0} checklist items</span>
            ${held > 0 ? `<span class="badge sim">⚠ ${held} USDT held · simulated</span>` : ""}
            <span class="muted" style="font-size:12.5px">${fmtDate(j.created_at)}</span>
          </div>
        </a>`;
    }).join("");

    return `
      <div class="card" style="margin-top:18px">
        <h2>Agree on “done” before the work starts</h2>
        <p class="sub">
          Describe the job in plain language → the AI asks 3–5 targeted questions → both sides
          confirm a structured, checkable spec → the deliverable is verified against it →
          payment is released from a <strong>simulated escrow ledger</strong>.
        </p>
        <div class="notice">⚠ Simulated escrow — no real money moves. This prototype does not
          integrate with Cleva, Tether, Upwork or Fiverr.</div>

        <label class="field" for="brief">1 · Describe the job in plain language</label>
        <textarea id="brief" placeholder="e.g. Write a 600-word blog post about how freelancers can avoid scope creep…"></textarea>
        <div class="btn-row">
          <button class="btn primary" id="create" ${state.busy ? "disabled" : ""}>
            ${state.busy ? "Working…" : "Create job →"}
          </button>
          <span class="muted" style="font-size:13px;align-self:center">
            AI engine: <strong>${esc(provLabel)}</strong>
          </span>
        </div>
      </div>

      <div class="card">
        <h2>Jobs</h2>
        <p class="sub">Two demo jobs are pre-seeded so you can show the flow immediately.</p>
        ${state.jobs.length ? jobs : `<p class="muted">No jobs yet.</p>`}
      </div>`;
  }

  function bindHome() {
    const btn = $("#create");
    if (!btn) return;
    btn.onclick = async () => {
      const brief = $("#brief").value.trim();
      if (brief.length < 10) { setError("Please describe the job in at least 10 characters."); render(); return; }
      const out = await run(() => post("/api/jobs", { brief }));
      if (out) {
        setFlash("Job created — the AI asked its follow-up questions.");
        location.hash = `#/job/${out.id}`;
      } else render();
    };
  }

  // ---------- job page ------------------------------------------------------
  function tabsHTML(job) {
    const tabs = [
      ["spec", "Spec & confirmation"],
      ["escrow", "Escrow (simulated)"],
      ["submit", "Submission"],
      ["report", "Verification report"],
      ["timeline", "Timeline"],
    ];
    return `<div class="tabs">${tabs.map(([id, label]) =>
      `<button data-tab="${id}" class="${state.tab === id ? "active" : ""}">${label}</button>`
    ).join("")}</div>`;
  }

  function stepperHTML(job) {
    const idx = stepIndex(job.status);
    const labels = ["Clarify", "Spec", "Lock", "Fund", "Verify", "Release"];
    return `<div class="stepper">${labels.map((l, i) => {
      const cls = job.status === "released" ? "done"
        : i < idx ? "done" : i === idx ? "current" : "";
      return `<div class="step ${cls}">${i + 1} · ${l}</div>`;
    }).join("")}</div>`;
  }

  function jobHTML(job) {
    if (state.tabJob !== job.id) {
      // sensible landing tab for the job's current state
      state.tabJob = job.id;
      state.tab = job.status === "human_review" ? "report"
        : job.status === "clarifying" || job.status === "spec_ready"
          || job.status === "spec_editing" || job.status === "confirmed" ? "spec"
        : job.status === "funded" || job.status === "changes_requested" ? "submit"
        : job.status === "released" || job.status === "refunded" ? "report"
        : "spec";
      state.view = job.status === "clarifying" ? "client"
        : role() === "freelancer" ? "freelancer" : "client";
    }
    const held = job.held_usdt || 0;
    const body = {
      spec: specTab, escrow: escrowTab, submit: submitTab,
      report: reportTab, timeline: timelineTab,
    }[state.tab](job);

    return `
      <div class="card" style="margin-top:18px">
        <div class="job-meta" style="margin:0 0 6px">
          <a href="#/" class="muted" style="font-size:13px">← All jobs</a>
          <span class="chip ${STATUS_CLASS[job.status] || ""}">${esc(job.status_label)}</span>
          ${job.locked ? `<span class="badge lock">🔒 Spec locked</span>` : ""}
          ${held > 0 ? `<span class="badge sim">⚠ ${held} USDT held · simulated</span>` : ""}
        </div>
        <h2 class="mt0">${esc(job.title)}</h2>
        <p class="sub">${esc(job.brief)}</p>
        ${stepperHTML(job)}
      </div>
      ${tabsHTML(job)}
      ${flashHTML()}
      <div id="tab-body">${body}</div>`;
  }

  function flashHTML() {
    let out = "";
    if (state.error) out += `<div class="error">⚠ ${esc(state.error)}</div>`;
    if (state.flash) out += `<div class="ok-note">✓ ${esc(state.flash)}</div>`;
    return out;
  }

  // ----- tab: spec ----------------------------------------------------------
  function specTab(job) {
    if (!job.spec) return clarifyHTML(job);
    const flags = job.flags || [];
    const flagged = new Set(flags.map((f) => f.item_id));

    const viewToggle = `
      <div class="btn-row" style="margin-top:0">
        <button class="btn sm ${state.view === "client" ? "primary" : ""}" data-view="client">Client view</button>
        <button class="btn sm ${state.view === "freelancer" ? "primary" : ""}" data-view="freelancer">Freelancer view (plain language)</button>
      </div>`;

    const clientBody = job.status === "spec_editing" && isClient()
      ? specEditForm(job)
      : specSummary(job);

    const freelancerBody = `
      <div class="quote">${esc(job.rewrite ? job.rewrite.rewrite : "")}</div>
      <h3 style="margin-top:16px">Questions to ask the client</h3>
      <ul style="margin:6px 0 0; padding-left:20px">
        ${(job.rewrite ? job.rewrite.questions : []).map((q) => `<li>${esc(q)}</li>`).join("")}
      </ul>
      <h3 style="margin-top:16px">Checklist — flag anything unclear</h3>
      ${checklistHTML(job, true)}
      ${isFreelancer() && ["spec_ready", "confirmed", "spec_editing"].includes(job.status)
        ? `<p class="sub" style="margin-top:10px">Flagging returns the job to the client for edits
             and unlocks confirmations.</p>` : ""}`;

    const confirmRow = confirmHTML(job);

    return `
      <div class="card">
        <h2>Structured spec</h2>
        <p class="sub">Locked specs are hashed; any edit resets both confirmations.</p>
        ${flags.length ? `<div class="banner warn">⚠ ${flags.length} item(s) flagged as unclear:
            ${flags.map((f) => esc(f.item_id)).join(", ")} — the client should edit the spec.</div>` : ""}
        ${viewToggle}
        <div style="margin-top:14px">${state.view === "client" ? clientBody : freelancerBody}</div>
      </div>
      ${confirmRow}`;
  }

  function checklistHTML(job, withFlag) {
    const flagged = new Set((job.flags || []).map((f) => f.item_id));
    return job.spec.checklist.map((it) => `
      <div class="cl-item ${flagged.has(it.id) ? "flagged" : ""}">
        <div class="cl-head">
          <span class="badge ${it.kind === "OBJECTIVE" ? "obj" : "sub"}">${it.kind}</span>
          <span class="badge src">${esc(it.id)}</span>
          ${flagged.has(it.id) ? `<span class="badge warn">flagged as unclear</span>` : ""}
          ${withFlag && isFreelancer() && ["spec_ready", "confirmed", "spec_editing"].includes(job.status)
            ? `<span class="spacer"></span>
               <button class="btn sm" data-act="flag" data-item="${esc(it.id)}">Flag as unclear</button>` : ""}
        </div>
        <div class="cl-text">${esc(it.text)}</div>
        <div class="cl-check">${it.kind === "OBJECTIVE"
          ? `Checked by code: <code>${esc(checkLabel(it.check))}</code>`
          : "Assessed by AI → human reviewer decides"}</div>
      </div>`).join("");
  }

  function specSummary(job) {
    const s = job.spec;
    return `
      <dl class="kv">
        <dt>Title</dt><dd>${esc(s.title)}</dd>
        <dt>Deliverables</dt><dd>${s.deliverables.map(esc).join("<br>")}</dd>
        <dt>Deadline</dt><dd>${esc(s.deadline)}</dd>
        <dt>Revision limit</dt><dd>${s.revision_limit} round(s)</dd>
        <dt>Not included</dt><dd>${s.out_of_scope.length ? s.out_of_scope.map(esc).join("<br>") : "<span class='muted'>—</span>"}</dd>
        <dt>Checklist</dt><dd>${s.checklist.length} items
          (${s.checklist.filter((i) => i.kind === "OBJECTIVE").length} objective /
           ${s.checklist.filter((i) => i.kind === "SUBJECTIVE").length} subjective)</dd>
      </dl>
      ${checklistHTML(job, state.view === "freelancer")}`;
  }

  function specEditForm(job) {
    const s = job.spec;
    return `
      <div class="banner warn" style="margin-bottom:10px">Client edit mode — address the flagged
        items, then both sides confirm again.</div>
      <label class="field" for="e-title">Title</label>
      <input type="text" id="e-title" value="${esc(s.title)}" />
      <label class="field" for="e-deadline">Deadline</label>
      <input type="text" id="e-deadline" value="${esc(s.deadline)}" />
      <label class="field" for="e-rev">Revision limit</label>
      <input type="number" id="e-rev" min="0" max="20" value="${s.revision_limit}" />
      <label class="field" for="e-deliv">Deliverables <span class="hint">(one per line)</span></label>
      <textarea id="e-deliv">${esc(s.deliverables.join("\n"))}</textarea>
      <label class="field" for="e-oos">Not included <span class="hint">(one per line)</span></label>
      <textarea id="e-oos">${esc(s.out_of_scope.join("\n"))}</textarea>
      <label class="field">Checklist text <span class="hint">(edit wording; kinds/checks stay fixed)</span></label>
      ${s.checklist.map((it, i) => `
        <div class="cl-item">
          <div class="cl-head">
            <span class="badge ${it.kind === "OBJECTIVE" ? "obj" : "sub"}">${it.kind}</span>
            <span class="badge src">${esc(it.id)}</span>
          </div>
          <input type="text" class="e-item" data-idx="${i}" value="${esc(it.text)}" style="margin-top:8px" />
        </div>`).join("")}
      <div class="btn-row">
        <button class="btn primary" data-act="save-spec" ${state.busy ? "disabled" : ""}>Save spec</button>
        <span class="muted" style="font-size:13px;align-self:center">Confirmations reset on save.</span>
      </div>`;
  }

  function confirmHTML(job) {
    const ready = ["spec_ready", "confirmed"].includes(job.status);
    const box = (who, done) => `
      <div class="cl-item" style="flex:1; min-width:200px">
        <div class="cl-head">
          <b>${who}</b>
          ${done ? `<span class="badge ok">confirmed</span>` : `<span class="badge src">waiting</span>`}
        </div>
        <div class="btn-row" style="margin-top:8px">
          ${ready && !job.locked && role() === who
            ? `<button class="btn ${done ? "" : "primary"} sm" data-act="confirm" data-role="${who}" ${done || state.busy ? "disabled" : ""}>
                 ${done ? "Confirmed ✓" : `Confirm as ${who}`}</button>`
            : `<span class="muted" style="font-size:13px">${done ? "Locked in." : "Not confirmed yet."}</span>`}
        </div>
      </div>`;
    return `
      <div class="card">
        <h2>Confirmations</h2>
        <p class="sub">Both sides must confirm. Confirming locks the spec (SHA-256 hash stored).</p>
        <div class="btn-row" style="margin-top:0; display:flex; gap:10px">
          ${box("client", job.confirmed_client)}
          ${box("freelancer", job.confirmed_freelancer)}
        </div>
        ${job.locked ? `<p class="sub" style="margin-top:12px">🔒 Locked · hash
          <code>${esc((job.lock_hash || "").slice(0, 16))}…</code></p>` : ""}
        ${ready && !job.locked ? `<p class="sub">Switch the role in the header to confirm as the
          other party (demo roles, no login).</p>` : ""}
        ${job.status === "spec_editing" ? `<div class="banner warn" style="margin-top:10px">
          The freelancer flagged items as unclear — the client must edit the spec first.</div>` : ""}
      </div>`;
  }

  function clarifyHTML(job) {
    const qs = job.messages.filter((m) => m.kind === "question");
    const ans = job.messages.filter((m) => m.kind === "answer");
    if (ans.length) {
      return `<div class="card"><h2>Clarification</h2>
        <p class="sub">Answers submitted — generating the spec…</p></div>`;
    }
    return `
      <div class="card">
        <h2>Clarification · ${qs.length} questions</h2>
        <p class="sub">The AI asked targeted follow-up questions about what “done” means,
          examples, deadline, revisions and exclusions. Answer all of them.</p>
        ${qs.map((q, i) => `
          <div class="qa">
            <div class="q"><span class="n">Q${i + 1}</span>${esc(q.content)}</div>
            <textarea class="q-answer" data-seq="${q.seq}" style="margin-top:8px"
              placeholder="Your answer…"></textarea>
          </div>`).join("")}
        <div class="btn-row">
          <button class="btn primary" data-act="clarify" ${state.busy ? "disabled" : ""}>
            ${state.busy ? "Building spec…" : "Submit answers → build the spec"}</button>
          ${isClient() ? "" : `<span class="muted" style="font-size:13px;align-self:center">
            Normally the client answers — demo roles, so anyone can.</span>`}
        </div>
      </div>`;
  }

  // ----- tab: escrow --------------------------------------------------------
  function escrowTab(job) {
    const canFund = job.status === "confirmed" && isClient();
    const rows = job.ledger.map((e) => `
      <tr>
        <td>${fmtDate(e.created_at)}</td>
        <td><span class="badge ${e.kind === "RELEASE" ? "ok" : e.kind === "REFUND" ? "bad" : "obj"}">${e.kind}</span></td>
        <td class="num">${e.amount_usdt} USDT</td>
        <td>${esc(e.note)} <span class="badge sim">simulated</span></td>
      </tr>`).join("");
    return `
      <div class="card">
        <h2>Milestone escrow</h2>
        <div class="notice" style="margin-bottom:12px">⚠ Simulated escrow ledger — fake USDT
          entries in local SQLite. No wallet, no chain, no real funds.</div>
        <dl class="kv">
          <dt>Status</dt><dd>${esc(job.status_label)}</dd>
          <dt>Held now</dt><dd>${job.held_usdt} USDT (simulated)</dd>
          <dt>Milestone</dt><dd>${job.amount_usdt || "—"} USDT (simulated)</dd>
        </dl>
        ${canFund ? `
          <label class="field" for="fund-amount">Fund amount (USDT, simulated)</label>
          <input type="number" id="fund-amount" min="1" step="1" value="${job.amount_usdt || 500}" />
          <div class="btn-row">
            <button class="btn primary" data-act="fund" ${state.busy ? "disabled" : ""}>
              Fund milestone (simulated) →</button>
          </div>` : ""}
        ${job.status === "confirmed" && !isClient()
          ? `<p class="sub" style="margin-top:12px">Switch to the <b>Client</b> role to fund the
               milestone (simulated).</p>` : ""}
        ${job.status === "clarifying" || job.status === "spec_ready" || job.status === "spec_editing"
          ? `<p class="sub" style="margin-top:12px">Both sides must confirm the locked spec first.</p>` : ""}
        <h3 style="margin-top:18px">Ledger entries</h3>
        ${job.ledger.length ? `
          <table class="ledger">
            <thead><tr><th>When</th><th>Type</th><th>Amount</th><th>Note</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>` : `<p class="muted">No ledger entries yet.</p>`}
      </div>`;
  }

  // ----- tab: submit --------------------------------------------------------
  function submitTab(job) {
    const sub = job.submission;
    const canSubmit = ["funded", "changes_requested", "submitted"].includes(job.status)
      && isFreelancer();
    const prefill = job.prefill;

    const form = canSubmit ? `
      <label class="field" for="s-kind">Deliverable type</label>
      <select id="s-kind">
        <option value="text" ${prefill && prefill.kind === "text" ? "selected" : ""}>Text / document</option>
        <option value="code" ${!prefill || prefill.kind === "code" ? "selected" : ""}>Code (pasted)</option>
        <option value="file">File upload (read as text)</option>
      </select>
      <div id="file-row" class="hidden">
        <label class="field" for="s-file">Choose file <span class="hint">(.py, .md, .txt, .js, .csv…)</span></label>
        <input type="file" id="s-file" />
      </div>
      <label class="field" for="s-name">Filename <span class="hint">(used for the file-type check)</span></label>
      <input type="text" id="s-name" placeholder="solution.py" value="${esc(prefill ? prefill.filename || "" : "")}" />
      <label class="field" for="s-content">Deliverable content</label>
      <textarea id="s-content" style="min-height:220px; font-family:ui-monospace,monospace; font-size:13px"
        placeholder="Paste the text, code or content here…">${esc(prefill ? prefill.content : "")}</textarea>
      <div class="btn-row">
        <button class="btn primary" data-act="submit" ${state.busy ? "disabled" : ""}>
          ${state.busy ? "Verifying…" : "Submit & run verification →"}</button>
        <span class="muted" style="font-size:13px;align-self:center">
          OBJECTIVE items are checked by code; the rest by AI → human review.</span>
      </div>` : "";

    const hint = !isFreelancer() ? `<p class="sub">Switch to the <b>Freelancer</b> role to submit
        a deliverable.</p>`
      : !canSubmit ? `<p class="sub">${job.status === "clarifying" || job.status === "spec_ready"
          || job.status === "spec_editing" || job.status === "confirmed"
          ? "The spec must be locked and the milestone funded (simulated) first."
          : "Nothing to submit right now — see the verification report."}</p>` : "";

    return `
      <div class="card">
        <h2>Deliverable submission</h2>
        <p class="sub">Text, an uploaded file (read locally as text), or pasted code.
          Test cases run in a time-limited subprocess.</p>
        ${form || hint}
      </div>
      ${sub ? `
        <div class="card">
          <h3>Last submission</h3>
          <p class="sub">${esc(sub.kind)}${sub.filename ? ` · ${esc(sub.filename)}` : ""}
            · ${fmtDate(sub.created_at)}</p>
          <pre class="code">${esc(sub.content)}</pre>
        </div>` : ""}`;
  }

  // ----- tab: report --------------------------------------------------------
  function reportTab(job) {
    const rep = job.report;
    if (!rep) {
      return `<div class="card"><h2>Verification report</h2>
        <p class="muted">No verification has run yet.</p>
        ${job.status === "funded" ? `<p class="sub">The freelancer can submit a deliverable
          (Submission tab) to trigger verification.</p>` : ""}</div>`;
    }
    const bannerCls = rep.overall === "pass" ? "ok" : rep.overall === "fail" ? "bad" : "warn";
    const bannerTxt = rep.overall === "pass"
      ? "✓ All checklist items passed — payment released automatically (simulated)."
      : rep.overall === "fail"
        ? "✕ Verification failed — a human reviewer decides release / changes / refund."
        : "⚠ Objective checks passed; subjective items need human review.";

    const items = rep.items.map((it) => `
      <div class="verdict">
        <div class="dot ${it.verdict}">${it.verdict === "pass" ? "✓" : it.verdict === "fail" ? "✕" : "?"}</div>
        <div>
          <div class="head">
            <b>${esc(it.text)}</b>
            <span class="badge ${it.kind === "OBJECTIVE" ? "obj" : "sub"}">${it.kind}</span>
            <span class="badge src">${it.source === "deterministic" ? "⚙ deterministic check" : "🤖 AI"}</span>
            <span class="badge ${it.verdict === "pass" ? "ok" : it.verdict === "fail" ? "bad" : "warn"}">
              ${it.verdict.replace("_", " ")}</span>
          </div>
          <div class="why">${esc(it.reason)}</div>
        </div>
      </div>`).join("");

    const reviewPanel = job.status === "human_review" && isReviewer() ? `
      <div class="card" style="border-color:#fcd34d">
        <h2>🧑‍⚖️ Human review</h2>
        <p class="sub">The AI recommends; you decide. Choose release, request changes, or refund
          (all movements are simulated).</p>
        <div class="banner warn">AI recommendation: ${esc(rep.recommendation)}</div>
        <label class="field" for="r-note">Reviewer note</label>
        <textarea id="r-note" placeholder="What did you check? Why this decision?"></textarea>
        <div class="btn-row">
          <button class="btn ok" data-act="review" data-decision="release" ${state.busy ? "disabled" : ""}>Release payment (simulated)</button>
          <button class="btn" data-act="review" data-decision="request_changes" ${state.busy ? "disabled" : ""}>Request changes</button>
          <button class="btn danger" data-act="review" data-decision="refund" ${state.busy ? "disabled" : ""}>Refund client (simulated)</button>
        </div>
      </div>` : job.status === "human_review" ? `
      <div class="banner warn">This job is waiting for a human reviewer — switch to the
        <b>Reviewer</b> role to open the dashboard.</div>` : "";

    const reviewDone = job.review ? `
      <div class="card">
        <h3>Reviewer decision</h3>
        <dl class="kv">
          <dt>Decision</dt><dd><span class="badge ${job.review.decision === "release" ? "ok"
            : job.review.decision === "refund" ? "bad" : "warn"}">${esc(job.review.decision)}</span></dd>
          <dt>Note</dt><dd>${esc(job.review.note || "—")}</dd>
          <dt>AI recommendation</dt><dd class="muted">${esc(job.review.recommendation || "—")}</dd>
          <dt>When</dt><dd>${fmtDate(job.review.created_at)}</dd>
        </dl>
      </div>` : "";

    return `
      <div class="card">
        <h2>Verification report</h2>
        <div class="banner ${bannerCls}">${bannerTxt}</div>
        <p class="sub" style="margin-top:10px">
          ${rep.checked_deterministically} deterministic check(s) ·
          ${rep.checked_by_ai} AI verdict(s) · generated ${fmtDate(rep.created_at)}</p>
        <div style="margin-top:6px">${items}</div>
        <div class="banner ${bannerCls}" style="margin-top:14px">Recommendation: ${esc(rep.recommendation)}</div>
      </div>
      ${reviewPanel}
      ${reviewDone}`;
  }

  // ----- tab: timeline ------------------------------------------------------
  function timelineTab(job) {
    const events = job.events.map((e) => `
      <li class="${e.kind === "ledger" ? "ledger" : ["verify", "flag", "review"].includes(e.kind) ? "warn" : ""}">
        <div class="t">${esc(e.label)}</div>
        ${e.detail ? `<div class="d">${esc(e.detail)}</div>` : ""}
        <div class="when">${fmtDate(e.created_at)}</div>
      </li>`).join("");
    return `
      <div class="card">
        <h2>Status timeline</h2>
        <p class="sub">Every state change on this job, including simulated ledger movements.</p>
        <ul class="timeline">${events || "<li class='muted'>No events.</li>"}</ul>
      </div>
      <div class="card">
        <h3>Job identifiers</h3>
        <dl class="kv">
          <dt>Job ID</dt><dd><code>${esc(job.id)}</code></dd>
          <dt>Status</dt><dd>${esc(job.status)}</dd>
          <dt>Spec locked</dt><dd>${job.locked ? `yes · ${esc((job.lock_hash || "").slice(0, 24))}…` : "no"}</dd>
          <dt>Created</dt><dd>${fmtDate(job.created_at)}</dd>
        </dl>
      </div>`;
  }

  // ---------- bindings ------------------------------------------------------
  function bindJob() {
    $$("[data-tab]").forEach((b) => b.onclick = () => { state.tab = b.dataset.tab; render(); });
    $$("[data-view]").forEach((b) => b.onclick = () => { state.view = b.dataset.view; render(); });

    const kind = $("#s-kind");
    if (kind) {
      const sync = () => $("#file-row").classList.toggle("hidden", kind.value !== "file");
      kind.onchange = sync; sync();
    }

    const act = async (el) => {
      const a = el.dataset.act;
      const id = state.job.id;

      if (a === "clarify") {
        const answers = {};
        $$(".q-answer").forEach((t) => { answers[t.dataset.seq] = t.value.trim(); });
        const out = await run(() => post(`/api/jobs/${id}/clarify`, { answers }));
        if (out) { state.job = out; state.tab = "spec"; state.view = "client";
          setFlash("Spec generated from your answers."); render(); }
        else render();
      }

      if (a === "confirm") {
        const out = await run(() => post(`/api/jobs/${id}/confirm`, { role: el.dataset.role }));
        if (out) {
          state.job = out;
          setFlash(out.locked ? "Spec locked — both sides confirmed."
            : `${el.dataset.role} confirmed. Waiting for the other party.`);
          render();
        } else render();
      }

      if (a === "fund") {
        const amount = parseFloat($("#fund-amount").value);
        const out = await run(() => post(`/api/jobs/${id}/fund`, { role: "client", amount_usdt: amount }));
        if (out) { state.job = out; setFlash("Milestone funded in the simulated ledger."); render(); }
        else render();
      }

      if (a === "flag") {
        const note = window.prompt("Why is this checklist item unclear?", "") || "";
        const out = await run(() => post(`/api/jobs/${id}/flag`,
          { role: "freelancer", item_id: el.dataset.item, note }));
        if (out) { state.job = out; setFlash("Flagged — the job is back with the client for edits."); render(); }
        else render();
      }

      if (a === "save-spec") {
        const s = JSON.parse(JSON.stringify(state.job.spec));
        s.title = $("#e-title").value.trim();
        s.deadline = $("#e-deadline").value.trim();
        s.revision_limit = parseInt($("#e-rev").value, 10) || 0;
        s.deliverables = $("#e-deliv").value.split("\n").map((x) => x.trim()).filter(Boolean);
        s.out_of_scope = $("#e-oos").value.split("\n").map((x) => x.trim()).filter(Boolean);
        $$(".e-item").forEach((inp) => { s.checklist[+inp.dataset.idx].text = inp.value.trim(); });
        const out = await run(() => post(`/api/jobs/${id}/spec`, { role: "client", spec: s }));
        if (out) { state.job = out; setFlash("Spec updated — confirmations reset."); render(); }
        else render();
      }

      if (a === "submit") {
        const kindV = $("#s-kind").value;
        const content = $("#s-content").value;
        let filename = $("#s-name").value.trim() || null;
        if (kindV === "file") {
          const f = $("#s-file").files[0];
          if (!f) { setError("Choose a file first."); render(); return; }
          filename = f.name;
          const text = await f.text();
          $("#s-content").value = text;
        }
        const finalContent = $("#s-content").value;
        if (!finalContent.trim()) { setError("The deliverable is empty."); render(); return; }
        const out = await run(() => post(`/api/jobs/${id}/submit`,
          { role: "freelancer", kind: kindV, content: finalContent, filename }));
        if (out) {
          state.job = out; state.tab = "report";
          setFlash(out.status === "released"
            ? "Verification passed — funds released (simulated)."
            : "Verification finished — routed to human review.");
          render();
        } else render();
      }

      if (a === "review") {
        const note = ($("#r-note") || {}).value || "";
        const out = await run(() => post(`/api/jobs/${id}/review`,
          { role: "reviewer", decision: el.dataset.decision, note }));
        if (out) { state.job = out;
          setFlash(`Reviewer decision recorded: ${el.dataset.decision.replace("_", " ")}.`);
          render();
        } else render();
      }
    };

    $$("[data-act]").forEach((el) => el.onclick = () => act(el));
  }

  // ---------- global events -------------------------------------------------
  $$("#roles button").forEach((b) => b.onclick = () => {
    state.role = b.dataset.role;
    localStorage.setItem("tb_role", state.role);
    state.view = state.role === "freelancer" ? "freelancer" : "client";
    render();
  });

  window.addEventListener("hashchange", () => { state.error = null; state.flash = null; render(); });
  render();
})();
