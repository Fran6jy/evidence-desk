const STORAGE_KEY = "evidence-desk-v1";
const CRITERIA = ["Recognition", "Optional 1", "Optional 2"];
const state = loadState();
let tasks = [];

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (saved && Array.isArray(saved.rows) && typeof saved.done === "object") return saved;
  } catch (_) {}
  return { rows: [], done: {} };
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    document.getElementById("notice").textContent = "Saved in this browser.";
  } catch (_) {
    document.getElementById("notice").textContent = "Browser storage is full. Export a backup now.";
  }
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : "";
  } catch (_) { return ""; }
}

function parseCsv(text) {
  const rows = []; let row = [], cell = "", quoted = false;
  text = text.replace(/^\uFEFF/, "");
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (char === '"') quoted = false;
      else cell += char;
    } else if (char === '"') quoted = true;
    else if (char === ",") { row.push(cell); cell = ""; }
    else if (char === "\n") { row.push(cell.replace(/\r$/, "")); rows.push(row); row = []; cell = ""; }
    else cell += char;
  }
  if (cell || row.length) { row.push(cell.replace(/\r$/, "")); rows.push(row); }
  if (quoted) throw new Error("CSV has an unfinished quoted field.");
  return rows;
}

function renderTasks() {
  const list = document.getElementById("task-list");
  list.innerHTML = tasks.map(task => {
    const checked = !!state.done[task.id];
    return `<li><span class="box"><button type="button" class="tick" data-task="${esc(task.id)}" aria-label="Mark ${esc(task.title)} ${checked ? "not done" : "done"}">${checked ? "☑" : "☐"}</button></span><details class="task"><summary><span class="task-title">${esc(task.title)}</span><span class="task-state">${checked ? "Complete" : "To do"}</span></summary><div class="task-detail"><p><b>What to do</b>${esc(task.action)}</p><p><b>Done when</b>${esc(task.doneWhen)}</p></div></details></li>`;
  }).join("");
  list.querySelectorAll("button[data-task]").forEach(button => button.addEventListener("click", () => {
    const id = button.dataset.task;
    state.done[id] = !state.done[id];
    save(); render();
  }));
}

function findings() {
  const ready = state.rows.filter(row => row.status === "Evidence ready");
  const checks = [];
  const counts = Object.fromEntries(CRITERIA.map(criterion => [criterion, 0]));
  const seen = new Set();
  for (const row of ready) {
    const label = row.activity || row.project || "Evidence row";
    if (CRITERIA.includes(row.criterion)) counts[row.criterion]++;
    else checks.push(["Criterion", `${label}: choose one criterion.`]);
    if (!row.impact || !row.proof) checks.push(["Missing detail", `${label}: record the outcome and independent source.`]);
    if (!row.sourceUrl && row.source !== "Proof file") checks.push(["Missing source", `${label}: link a source or retain the original file locally.`]);
    if (row.id && seen.has(row.id)) checks.push(["Duplicate", `${label}: duplicate evidence ID.`]);
    seen.add(row.id);
  }
  if (ready.length > 10) checks.push(["Limit", `${ready.length} rows are ready; the criterion bundle permits no more than 10 documents.`]);
  for (const criterion of CRITERIA) if (counts[criterion] < 2) checks.push(["Coverage", `${criterion}: ${counts[criterion]}/2 ready documents.`]);
  checks.push(["Manual review", "Check authenticity, your contribution, impact, PDF length, CV and referee letters against the current rules. Browser imports do not verify those points."]);
  return checks;
}

function renderRows() {
  const tbody = document.getElementById("evidence-rows");
  if (!state.rows.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-state">No leads imported. Use “Import review CSV” above to bring in the local scanner’s queue.</td></tr>';
    return;
  }
  tbody.innerHTML = state.rows.map((row, index) => {
    const href = safeUrl(row.sourceUrl);
    const link = href ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">Open source</a>` : "";
    const options = ['Needs review', 'Developing', 'Evidence ready', 'Exclude'].map(value => `<option value="${value}" ${row.status === value ? "selected" : ""}>${value}</option>`).join("");
    const criteria = '<option value="">Choose criterion</option>' + CRITERIA.map(value => `<option value="${value}" ${row.criterion === value ? "selected" : ""}>${value}</option>`).join("");
    const edit = `<details><summary>Update</summary><form data-row="${index}"><label>Status<select name="status">${options}</select></label><label>Criterion<select name="criterion">${criteria}</select></label><label>Outcome / impact<input name="impact" value="${esc(row.impact)}"></label><label>Independent proof<input name="proof" value="${esc(row.proof)}"></label><button type="submit">Save</button></form></details>`;
    const cells = [["Date",row.date],["Project",row.project],["Activity",row.activity],["Detail",row.detail],["Status",row.status],["Criterion",row.criterion],["Impact",row.impact],["Third-party proof",row.proof]];
    return `<tr>${cells.map(([label,value]) => `<td data-label="${label}">${esc(value)}</td>`).join("")}<td data-label="Source / action">${link} ${edit}</td></tr>`;
  }).join("");
  tbody.querySelectorAll("form[data-row]").forEach(form => form.addEventListener("submit", event => {
    event.preventDefault();
    const row = state.rows[Number(form.dataset.row)];
    const data = new FormData(form);
    const status = String(data.get("status"));
    const criterion = String(data.get("criterion"));
    const impact = String(data.get("impact")).trim();
    const proof = String(data.get("proof")).trim();
    if (status === "Evidence ready" && (!CRITERIA.includes(criterion) || !impact || !proof)) {
      document.getElementById("notice").textContent = "Ready requires a criterion, outcome and independent proof.";
      return;
    }
    Object.assign(row, { status, criterion, impact, proof });
    save(); render();
  }));
}

function render() {
  const ready = state.rows.filter(row => row.status === "Evidence ready").length;
  const pending = state.rows.filter(row => row.status === "Needs review").length;
  const done = tasks.filter(task => state.done[task.id]).length;
  document.getElementById("task-progress").textContent = `${done}/${tasks.length}`;
  document.getElementById("task-bar").style.width = `${tasks.length ? Math.min(100, done / tasks.length * 100) : 0}%`;
  document.getElementById("evidence-progress").textContent = `${ready}/6`;
  document.getElementById("ready-bar").style.width = `${Math.min(100, ready / 6 * 100)}%`;
  document.getElementById("total-leads").textContent = String(state.rows.length);
  document.getElementById("lead-count").textContent = `${pending} leads to review`;
  document.getElementById("ready-count").textContent = `${ready} documents ready`;
  document.getElementById("folder-count").textContent = String(state.rows.length).padStart(2, "0");
  renderTasks(); renderRows();
  document.getElementById("findings").innerHTML = findings().map(([kind, message]) => `<li><strong>${esc(kind)}</strong><span>${esc(message)}</span></li>`).join("");
}

document.getElementById("today").textContent = new Intl.DateTimeFormat("en-GB", { day:"numeric", month:"short", year:"numeric" }).format(new Date());
document.getElementById("folder-year").textContent = String(new Date().getFullYear());
document.querySelector('label[for="csv-import"]').addEventListener("keydown", event => {
  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); document.getElementById("csv-import").click(); }
});
document.getElementById("csv-import").addEventListener("change", async event => {
  const file = event.target.files[0]; if (!file) return;
  try {
    const parsed = parseCsv(await file.text());
    const header = parsed.shift().map(value => value.trim());
    for (const needed of ["Date","Source","Project","Activity","Detail","Status","ID"]) {
      if (!header.includes(needed)) throw new Error(`Missing CSV column: ${needed}`);
    }
    const value = (row, column) => row[header.indexOf(column)] || "";
    const incoming = parsed.filter(row => row.some(Boolean)).map(row => ({
      id:value(row,"ID"), date:value(row,"Date"), source:value(row,"Source"), project:value(row,"Project"),
      activity:value(row,"Activity"), detail:value(row,"Detail"), sourceUrl:value(row,"URL"),
      status:value(row,"Status") || "Needs review", criterion:value(row,"Potential criterion"),
      impact:value(row,"Impact / outcome"), proof:value(row,"Third-party proof")
    }));
    const existing = new Map(state.rows.map(row => [row.id, row]));
    for (const row of incoming) {
      if (!row.id) continue;
      const old = existing.get(row.id);
      existing.set(row.id, old ? { ...row, status:old.status, criterion:old.criterion, impact:old.impact, proof:old.proof } : row);
    }
    state.rows = [...existing.values()];
    if (incoming.length) state.done.project_inventory = true;
    save(); render();
    document.getElementById("notice").textContent = `Imported ${incoming.length} rows. Original files stayed local.`;
  } catch (error) {
    document.getElementById("notice").textContent = `Import failed: ${error.message}`;
  }
  event.target.value = "";
});

document.getElementById("backup").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify({ exportedAt:new Date().toISOString(), ...state }, null, 2)], { type:"application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a"); link.href = url; link.download = "evidence-desk-backup.json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

fetch("/tasks.json").then(response => { if (!response.ok) throw new Error("Task template unavailable"); return response.json(); })
  .then(data => { tasks = data; render(); })
  .catch(error => { document.getElementById("notice").textContent = error.message; render(); });
