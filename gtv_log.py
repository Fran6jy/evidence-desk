"""Local, source-linked activity inbox for Global Talent evidence preparation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import re
import sqlite3
import subprocess
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT.parent
INBOX = ROOT / "Proof inbox"
DATA = ROOT / "evidence.sqlite3"
CSV = ROOT / "Review queue.csv"
HTML = ROOT / "Review queue.html"
SINCE = "2026-01-01"
IGNORE = {ROOT.name, ".pytest_cache", "node_modules"}
CRITERIA = ("Recognition", "Optional 1", "Optional 2")
TASKS = [
    ("project_inventory", "Inventory local projects", "Automatic",
     "The scanner lists dated Git activity and project links. Check which work was yours and which repositories are public.",
     "The local inventory has been generated. This is a lead list, not evidence of impact."),
    ("criteria_choice", "Choose your route and two optional criteria", "Manual",
     "Decide whether the evidence supports exceptional talent or exceptional promise. Name the two additional criteria you will document, such as outside-work contribution and significant product contribution.",
     "Your chosen route and two criteria are written down, and every proposed document has one intended criterion."),
    ("project_outcomes", "Document project users, outcomes or usage figures", "Manual",
     "For the strongest projects, record your exact role, launch dates, users or customers, and a measurable result. Save dated analytics exports, customer records, deployment records or comparable source material.",
     "At least one project has a clear contribution, dated outcome and a source that supports the numbers. A README or code commit alone is not an outcome."),
    ("external_validation", "Save independent project validation", "Manual",
     "Look for named customer or peer feedback, public adoption, acknowledged open-source contributions, a credible event invitation or independent coverage that identifies your work.",
     "The original dated third-party source is saved and identifies you or your contribution. Self-written claims alone do not complete this task."),
    ("stem_activity", "Save STEM Ambassador activity confirmation", "Manual",
     "After an actual session, record its date, organiser, your role, audience and what you taught. Save the organiser's confirmation, event page or attendance record and any feedback.",
     "A completed activity and a dated independent record are saved. An application or acceptance email by itself does not prove a contribution."),
    ("codebar_activity", "Save codebar activity confirmation", "Manual",
     "For coaching, talks or Ambassador work, record the date, your role, topic and reach. Save a codebar event listing, organiser confirmation or participant feedback.",
     "At least one completed contribution has independent dated confirmation. A programme application is only a starting point."),
    ("cyf_activity", "Save CodeYourFuture activity confirmation", "Manual",
     "For Tech Products or other volunteering, record the deliverable, your individual role and result. Save a project record, merged contribution and organiser or team confirmation.",
     "A completed contribution and independent confirmation are saved; an expression of interest alone is not enough."),
    ("mandatory_docs", "Review two recognition documents", "Manual",
     "Select two different documents showing recognition by others as a leading or potential talent in digital technology within the relevant five-year period. Prefer named, dated third-party recognition tied to your own work.",
     "Two distinct documents are selected for recognition, each no more than three A4 sides, and neither is reused for another criterion."),
    ("optional_one_docs", "Review two documents for optional criterion one", "Manual",
     "Match both documents to your first chosen criterion. Explain the work, your individual contribution and outcome; attach source material such as an organiser record or verified product result.",
     "Two distinct documents support the same selected criterion, each no more than three A4 sides, with no reuse across criteria."),
    ("optional_two_docs", "Review two documents for optional criterion two", "Manual",
     "Match both documents to your second chosen criterion. If it is product contribution, show your role and significant technical, commercial or entrepreneurial result; if outside-work contribution, show actual activity and recognition.",
     "Two distinct documents support the second selected criterion, each no more than three A4 sides, with no reuse across criteria."),
    ("referee_letters", "Collect three suitable referee letters", "Manual",
     "Choose three different established digital-technology experts who have known your work for at least 12 months. Each letter should give different examples, explain your achievements and UK contribution, and be signed and dated.",
     "Three letters specific to this application are saved with author credentials, contact details and the required content. Each letter is within three single A4 sides, excluding credentials and contact details."),
    ("cv", "Prepare the endorsement CV", "Manual",
     "Include your career and relevant publication history. Check dates, roles and claims against the underlying records.",
     "A typed CV of no more than three A4 sides is final and fact-checked."),
    ("final_bundle", "Check and select the final evidence bundle", "Manual",
     "Choose no more than ten criterion documents: at least two for recognition and two for each of the two selected optional criteria. Keep the CV and letters separate. If you were a founder or senior executive in the last five years, include proof of the business connection.",
     "Every document is dated, legible, no more than three A4 sides, mapped once to a criterion and checked against the current official rules before submission."),
]


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=30)
    return result.stdout.strip() if result.returncode == 0 else ""


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DATA)
    con.execute("""CREATE TABLE IF NOT EXISTS candidates (
        id TEXT PRIMARY KEY, date TEXT NOT NULL, source TEXT NOT NULL,
        project TEXT NOT NULL, activity TEXT NOT NULL, detail TEXT NOT NULL,
        url TEXT NOT NULL, file_path TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Needs review',
        criterion TEXT NOT NULL DEFAULT '', impact TEXT NOT NULL DEFAULT '',
        corroboration TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, done INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT ''
    )""")
    con.executemany("INSERT OR IGNORE INTO tasks(id) VALUES (?)", [(t[0],) for t in TASKS])
    return con


def add(con: sqlite3.Connection, values: tuple[str, ...]) -> int:
    before = con.total_changes
    con.execute("""INSERT OR IGNORE INTO candidates
        (id,date,source,project,activity,detail,url,file_path,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)""", values)
    return con.total_changes - before


def github_url(remote: str) -> str:
    remote = remote.removesuffix(".git")
    if remote.startswith("git@github.com:"):
        return "https://github.com/" + remote.split(":", 1)[1]
    if remote.startswith("https://github.com/"):
        return remote
    return ""


def scan_repos(con: sqlite3.Connection) -> tuple[int, int]:
    new = count = 0
    for repo in sorted(PROJECTS.iterdir(), key=lambda p: p.name.lower()):
        if not repo.is_dir() or repo.name in IGNORE or not (repo / ".git").exists():
            continue
        count += 1
        remote = github_url(git(repo, "remote", "get-url", "origin"))
        raw = git(repo, "log", "--all", f"--since={SINCE}", "--format=%H%x1f%aI%x1f%an%x1f%s%x1e")
        groups: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)
        for record in raw.split("\x1e"):
            fields = record.strip().split("\x1f")
            if len(fields) != 4:
                continue
            sha, dated, author, subject = fields
            if re.match(r"^\d{4}-\d{2}", dated):
                groups[(dated[:7], author)].append((sha, dated[:10], subject))
        for (month, author), commits in groups.items():
            commits.sort(key=lambda x: x[1])
            newest = commits[-1]
            link = f"{remote}/commits" if remote else ""
            detail = f"{len(commits)} local commits by {author}. Latest: {newest[2][:140]}. Verify public visibility, ownership and impact separately."
            key = hashlib.sha256(f"git|{repo.resolve()}|{month}|{author}".encode()).hexdigest()[:20]
            new += add(con, (key, newest[1], "Local Git history", repo.name,
                             f"Project work in {month}", detail, link, str(repo), now()))
    return count, new


def scan_proof(con: sqlite3.Connection) -> int:
    INBOX.mkdir(exist_ok=True)
    new = 0
    for path in INBOX.rglob("*"):
        if not path.is_file():
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:20]
            date = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat()
        except (OSError, PermissionError):
            continue
        new += add(con, (digest, date, "Proof file", path.parent.name if path.parent != INBOX else "Unsorted",
                         path.name, "File captured. Check date, context, source and third-party corroboration.",
                         "", str(path), now()))
    return new


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def progress(current: int, target: int) -> str:
    pct = min(100, round(100 * current / target))
    return f'<div class="meter"><span style="width:{pct}%"></span></div><strong>{current}/{target}</strong>'


def assess(con: sqlite3.Connection) -> list[tuple[str, str]]:
    """Mechanical checks only; they do not establish immigration eligibility."""
    rows = con.execute("""SELECT id,activity,source,url,file_path,status,criterion,impact,corroboration
                          FROM candidates WHERE status='Evidence ready'""").fetchall()
    findings: list[tuple[str, str]] = []
    counts = {criterion: 0 for criterion in CRITERIA}
    seen_files: set[str] = set()
    for ident, activity, source, url, file_path, status, criterion, impact, proof in rows:
        label = f"{activity} ({ident[:8]})"
        if criterion not in CRITERIA:
            findings.append(("Needs correction", f"{label}: choose Recognition, Optional 1 or Optional 2."))
        else:
            counts[criterion] += 1
        if not impact.strip() or not proof.strip():
            findings.append(("Needs correction", f"{label}: add the outcome and independent corroboration."))
        path = Path(file_path) if file_path else None
        if not path or not path.is_file():
            findings.append(("Needs source", f"{label}: no saved evidence file is linked. A project folder or generic commit list is not a submission document."))
        else:
            key = str(path.resolve()).lower()
            if key in seen_files:
                findings.append(("Needs correction", f"{label}: the same file appears in another ready row; one piece cannot be reused across criteria."))
            seen_files.add(key)
            if path.suffix.lower() == ".pdf":
                try:
                    from pypdf import PdfReader
                    pages = len(PdfReader(str(path)).pages)
                    if pages > 3:
                        findings.append(("Page limit", f"{label}: PDF is {pages} pages; criterion evidence is limited to three A4 sides."))
                except Exception:
                    findings.append(("Manual check", f"{label}: PDF page count could not be read."))
            else:
                findings.append(("Manual check", f"{label}: check the document is no more than three A4 sides after final export."))
    if len(rows) > 10:
        findings.append(("Document limit", f"{len(rows)} rows are marked ready; the criterion evidence bundle allows at most 10 documents."))
    for criterion, count in counts.items():
        if count < 2:
            findings.append(("Coverage gap", f"{criterion}: {count}/2 ready documents are mapped here."))
    findings.append(("Manual document check", "This tracker does not classify or authenticate the three recommendation letters, the CV, founder or senior-executive business records where applicable, or A4 sizing. Verify these against the official guidance."))
    findings.append(("Human review", "Confirm source authenticity, dates, your individual contribution, claimed impact, peer recognition, referee suitability and the selected route. These cannot be verified by this tracker."))
    return findings


def dashboard(con: sqlite3.Connection, interactive: bool) -> str:
    rows = con.execute("""SELECT date,source,project,activity,detail,url,file_path,status,
        criterion,impact,corroboration,id FROM candidates ORDER BY date DESC,project""").fetchall()
    states = dict(con.execute("SELECT id,done FROM tasks"))
    # The inventory is completed by the scanner, not by a self-reported tick.
    states["project_inventory"] = int(any(row[1] == "Local Git history" for row in rows))
    task_done = sum(bool(states.get(task_id)) for task_id, *_ in TASKS)
    ready = sum(row[7] == "Evidence ready" for row in rows)
    findings = assess(con)
    safe = lambda x: html.escape(str(x), quote=True)
    checklist = []
    for task_id, title, mode, action, done_when in TASKS:
        checked = bool(states.get(task_id))
        if interactive and mode == "Manual":
            control = f'<form method="post" action="/task"><input type="hidden" name="id" value="{task_id}"><input type="hidden" name="done" value="{0 if checked else 1}"><button class="tick" type="submit" aria-label="Mark {safe(title)} {"not done" if checked else "done"}">{"☑" if checked else "☐"}</button></form>'
        else:
            control = "☑" if checked else "☐"
        checklist.append(f'<li><span class="box">{control}</span><details class="task"><summary><span class="task-title">{safe(title)}</span><span class="task-state">{"Complete" if checked else "To do"}</span></summary><div class="task-detail"><p><b>What to do</b>{safe(action)}</p><p><b>Done when</b>{safe(done_when)}</p></div></details></li>')
    tr = []
    for row in rows:
        date, source, project, activity, detail, url, file_path, status, criterion, impact, proof, ident = row
        link = f'<a href="{safe(url)}">GitHub</a>' if url else ""
        local = f'<a href="{safe(Path(file_path).as_uri())}">File</a>' if file_path and Path(file_path).is_file() else ""
        if interactive:
            options = "".join(
                f'<option value="{safe(v)}" {"selected" if status == v else ""}>{safe(v)}</option>'
                for v in ["Needs review", "Developing", "Evidence ready", "Exclude"]
            )
            criterion_options = '<option value="">Choose criterion</option>' + "".join(
                f'<option value="{safe(v)}" {"selected" if criterion == v else ""}>{safe(v)}</option>' for v in CRITERIA
            )
            edit = f'<details><summary>Update</summary><form method="post" action="/candidate"><input type="hidden" name="id" value="{safe(ident)}"><label>Status<select name="status">{options}</select></label><label>Criterion<select name="criterion">{criterion_options}</select></label><label>Outcome / impact<input name="impact" value="{safe(impact)}"></label><label>Independent proof<input name="corroboration" value="{safe(proof)}"></label><button>Save</button></form></details>'
        else:
            edit = ""
        labels = ["Date", "Project", "Activity", "Detail", "Status", "Criterion", "Impact", "Third-party proof"]
        cells = "".join(
            f'<td data-label="{safe(label)}">{safe(value)}</td>'
            for label, value in zip(labels, (date, project, activity, detail, status, criterion, impact, proof))
        )
        tr.append(f'<tr>{cells}<td data-label="Source / action">{link} {local} {edit}</td></tr>')
    pending = sum(row[7] == "Needs review" for row in rows)
    note = "Tick tasks and update each evidence row here." if interactive else "Open the dashboard with Open dashboard.cmd to tick tasks and update evidence rows."
    findings_html = "".join(f'<li><strong>{safe(kind)}</strong><span>{safe(message)}</span></li>' for kind, message in findings)
    theme = (ROOT / "theme.css").read_text(encoding="utf-8")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GTV evidence tracker</title>
<style>
:root{{color-scheme:light;--ink:#182a3b;--muted:#526577;--line:#dbe3eb;--blue:#195a92;--blue-dark:#123f68;--paper:#fff;--wash:#f4f7fb}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);font:16px/1.55 Arial,Helvetica,sans-serif;color:var(--ink)}}main{{max-width:1320px;margin:auto;padding:32px 24px 72px}}header{{padding:8px 0 22px;border-bottom:1px solid var(--line)}}.eyebrow{{margin:0 0 8px;color:var(--blue);font-size:12px;font-weight:700;letter-spacing:.13em;text-transform:uppercase}}h1{{font-size:clamp(28px,3vw,42px);line-height:1.15;letter-spacing:-.025em;margin:0 0 10px}}h2{{font-size:21px;line-height:1.25;margin:0 0 7px}}p{{color:var(--muted);margin:7px 0;max-width:75ch}}.meta{{font-size:14px}}section{{margin-top:32px}}.section-head{{margin-bottom:15px}}.cards{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:24px}}.card{{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:20px;box-shadow:0 2px 10px #153a5a0a;min-width:0}}.card h2{{font-size:15px;font-weight:700;color:var(--muted);margin:0 0 10px}}.card strong{{font-size:26px;line-height:1.2;letter-spacing:-.02em}}.card p{{font-size:13px;line-height:1.45;margin-top:10px}}.meter{{height:10px;background:#e7edf3;border-radius:20px;overflow:hidden;margin:0 0 11px}}.meter span{{display:block;height:100%;background:var(--blue);border-radius:20px}}.checklist{{padding:0;margin:0;list-style:none;background:var(--paper);border:1px solid var(--line);border-radius:12px;overflow:hidden}}.checklist li{{display:flex;align-items:center;gap:12px;padding:11px 16px;border-bottom:1px solid var(--line);min-height:56px}}.checklist li:last-child{{border:0}}.box{{font-size:23px;width:44px;min-width:44px;text-align:center;color:var(--blue)}}.state{{margin-left:auto;white-space:nowrap;color:var(--muted);font-size:13px}}.tick{{border:0;background:none;width:44px;height:44px;font-size:25px;cursor:pointer;color:var(--blue);border-radius:8px}}.tick:hover{{background:#eaf3fb}}a{{color:var(--blue-dark);text-underline-offset:2px}}button{{cursor:pointer}}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{{outline:3px solid #e38b2c;outline-offset:2px}}.table-wrap{{overflow-x:auto;background:var(--paper);border:1px solid var(--line);border-radius:12px}}table{{border-collapse:collapse;width:100%;font-size:14px}}th{{background:var(--blue-dark);color:#fff;text-align:left;white-space:nowrap}}td,th{{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top}}tbody tr:last-child td{{border-bottom:0}}tbody tr:hover{{background:#f1f6fb}}td:nth-child(4){{min-width:260px}}td:nth-child(8){{min-width:170px}}details{{margin-top:8px}}summary{{cursor:pointer;color:var(--blue-dark);font-weight:700}}details form{{display:grid;gap:10px;min-width:220px;margin:10px 0}}details label{{display:grid;gap:3px;font-size:13px;font-weight:700}}input,select{{font:inherit;padding:8px;border:1px solid #b9c7d4;border-radius:6px;max-width:100%}}details button{{min-height:44px;border:0;background:var(--blue);color:#fff;border-radius:7px;font-weight:700}}
@media(max-width:900px){{.cards{{grid-template-columns:repeat(2,minmax(0,1fr))}}.card:last-child{{grid-column:1/-1}}}}
@media(max-width:680px){{main{{padding:22px 16px 56px}}header{{padding-bottom:16px}}.cards{{grid-template-columns:1fr;gap:10px}}.card:last-child{{grid-column:auto}}section{{margin-top:27px}}.checklist li{{align-items:flex-start;gap:7px;padding:8px 10px}}.checklist li>span:nth-child(2){{padding-top:10px}}.state{{padding-top:11px}}.table-wrap{{background:transparent;border:0;overflow:visible}}table,tbody,tr,td{{display:block;width:100%}}thead{{display:none}}tr{{background:#fff;border:1px solid var(--line);border-radius:12px;margin:0 0 12px;padding:10px 13px;box-shadow:0 2px 10px #153a5a0a}}td,td:nth-child(4),td:nth-child(8){{min-width:0;border:0;padding:6px 0;display:grid;grid-template-columns:112px minmax(0,1fr);gap:10px;overflow-wrap:anywhere}}td:before{{content:attr(data-label);font-weight:700;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.02em}}details form{{min-width:0}}}}
.checklist li{{align-items:flex-start;padding-top:17px;padding-bottom:17px}}
.task-copy{{min-width:0;max-width:85ch}}
.task-copy strong{{display:block;padding-top:5px}}
.task-copy p{{font-size:14px;line-height:1.5;margin:5px 0 0;max-width:none}}
.task-copy b{{color:var(--ink)}}
.findings{{list-style:none;padding:0;margin:0;background:var(--paper);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
.findings li{{display:flex;gap:14px;padding:12px 16px;border-bottom:1px solid var(--line)}}.findings li:last-child{{border:0}}.findings strong{{min-width:125px;color:var(--blue-dark)}}
@media(max-width:680px){{.task-copy p{{font-size:13px}}.state{{font-size:12px}}}}
</style><style>{theme}</style></head><body><div class="menubar"><div class="identity"><span class="mark">FB</span><span>Evidence Desk</span><span class="menu-separator">/</span><span class="menu-muted">Digital technology</span></div><span class="menu-date">{safe(now()[:10])}</span></div><main><header><div class="hero-copy"><p class="eyebrow">FRANCIS BABATUNDE / GLOBAL TALENT</p><h1>Evidence<br><i>desk.</i></h1><p class="hero-description">A working record of the projects, contributions and independent proof behind your application.</p><div class="hero-status"><span class="live-dot"></span>{pending} leads to review <span class="hero-divider"></span> {ready} documents ready</div></div><div class="hero-object" aria-hidden="true"><div class="folder-tab"></div><div class="folder-face"><span class="folder-label">CASE FILE<br><b>2026</b></span><span class="folder-count">{len(rows):02d}</span></div><div class="folder-sheet sheet-one"></div><div class="folder-sheet sheet-two"></div></div></header>
<div class="cards" id="overview"><div class="card"><h2>Steps complete</h2>{progress(task_done,len(TASKS))}<p>Every checked item has its own completion rule.</p></div><div class="card"><h2>Documents ready</h2>{progress(ready,6)}<p>Two recognition documents and two for each selected optional criterion.</p></div><div class="card"><h2>Proof on file</h2><strong>{sum(row[1] == "Proof file" for row in rows)}</strong><p>Originals saved to the Proof inbox.</p></div></div>
<section id="tasks"><div class="section-head"><div><span class="section-kicker">01 / WORK PLAN</span><h2>What remains</h2></div><p>Open a task to see the action and the standard for completion. {note}</p></div><ul class="checklist">{''.join(checklist)}</ul></section>
<section id="checks"><div class="section-head"><div><span class="section-kicker">02 / QUALITY CONTROL</span><h2>Before submission</h2></div><p>Mechanical checks only. The endorsing body decides whether your evidence meets the criteria.</p></div><ul class="findings">{findings_html}</ul><p class="source-note"><a href="https://www.gov.uk/global-talent-digital-technology/documents-you-need-to-apply-endorsement">Official document guidance</a> · <a href="https://www.gov.uk/global-talent-digital-technology/eligibility">Official eligibility criteria</a></p></section>
<section id="evidence"><div class="section-head"><div><span class="section-kicker">03 / SOURCE FILES</span><h2>Evidence queue</h2></div><p>{len(rows)} leads on record. A Git commit is a lead; record the outcome and independent source before marking it ready.</p></div>
<div class="table-wrap"><table><thead><tr>{''.join(f'<th>{safe(h)}</th>' for h in ['Date','Project','Activity','Detail','Status','Criterion','Impact','Third-party proof','Source / action'])}</tr></thead><tbody>{''.join(tr)}</tbody></table></div></section></main><nav class="dock" aria-label="Page sections"><a href="#overview"><span class="dock-icon icon-overview"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/></svg></span><span>Overview</span></a><a href="#tasks"><span class="dock-icon icon-plan"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="m8 12 3 3 5-6"/></svg></span><span>Plan</span></a><a href="#checks"><span class="dock-icon icon-checks"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="8"/><path d="m8.5 12 2.5 2.5 4.5-5"/></svg></span><span>Checks</span></a><a href="#evidence"><span class="dock-icon icon-evidence"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7V5a2 2 0 0 1 2-2h5l2 2h5a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><path d="M4 9h16"/></svg></span><span>Evidence</span></a></nav></body></html>"""


def export(con: sqlite3.Connection) -> None:
    rows = con.execute("""SELECT date,source,project,activity,detail,url,file_path,status,
        criterion,impact,corroboration,id FROM candidates ORDER BY date DESC,project""").fetchall()
    headers = ["Date", "Source", "Project", "Activity", "Detail", "URL", "File path",
               "Status", "Potential criterion", "Impact / outcome", "Third-party proof", "ID"]
    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    HTML.write_text(dashboard(con, False), encoding="utf-8")


def serve() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/":
                self.send_error(404)
                return
            with db() as con:
                body = dashboard(con, True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path not in ("/task", "/candidate"):
                self.send_error(404)
                return
            size = min(int(self.headers.get("Content-Length", "0")), 100000)
            fields = {k: v[0] for k, v in parse_qs(self.rfile.read(size).decode("utf-8"), keep_blank_values=True).items()}
            with db() as con:
                if self.path == "/task":
                    allowed = {task_id for task_id, _, mode, *_ in TASKS if mode == "Manual"}
                    if fields.get("id") not in allowed or fields.get("done") not in ("0", "1"):
                        self.send_error(400)
                        return
                    con.execute("UPDATE tasks SET done=?,updated_at=? WHERE id=?", (int(fields["done"]), now(), fields["id"]))
                else:
                    status = fields.get("status")
                    if status not in ("Needs review", "Developing", "Evidence ready", "Exclude"):
                        self.send_error(400)
                        return
                    criterion = fields.get("criterion", "").strip()[:300]
                    impact = fields.get("impact", "").strip()[:1000]
                    corroboration = fields.get("corroboration", "").strip()[:1000]
                    if status == "Evidence ready" and not (criterion in CRITERIA and impact and corroboration):
                        self.send_error(400, "Evidence ready needs a criterion, outcome and independent proof")
                        return
                    con.execute("""UPDATE candidates SET status=?,criterion=?,impact=?,corroboration=?,updated_at=? WHERE id=?""",
                                (status, criterion, impact, corroboration, now(), fields.get("id", "")))
                export(con)
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

    address = "http://127.0.0.1:8765/"
    print(f"Dashboard: {address}")
    webbrowser.open(address)
    HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="Capture new local Git activity and files in Proof inbox")
    sub.add_parser("serve", help="Open interactive dashboard with tick boxes and progress bars")
    review = sub.add_parser("review", help="Update one candidate after verifying it")
    review.add_argument("id")
    review.add_argument("--status", choices=["Needs review", "Developing", "Evidence ready", "Exclude"])
    review.add_argument("--criterion")
    review.add_argument("--impact")
    review.add_argument("--corroboration")
    args = parser.parse_args()
    with db() as con:
        if args.command == "scan":
            repos, git_new = scan_repos(con)
            proof_new = scan_proof(con)
            export(con)
            print(f"Scanned {repos} repositories. New project-month leads: {git_new}. New proof files: {proof_new}. Review queue: {HTML}")
        elif args.command == "serve":
            export(con)
            serve()
        else:
            updates = {k: getattr(args, k) for k in ("status", "criterion", "impact", "corroboration") if getattr(args, k) is not None}
            if not updates:
                parser.error("Provide at least one review field")
            updates["updated_at"] = now()
            fields = ", ".join(f"{k}=?" for k in updates)
            cur = con.execute(f"UPDATE candidates SET {fields} WHERE id=?", [*updates.values(), args.id])
            if not cur.rowcount:
                parser.error("ID not found in Review queue.csv")
            export(con)
            print(f"Updated {args.id}")


if __name__ == "__main__":
    main()
