"""Export the generic task template for the browser app; never include personal data."""

import json
from pathlib import Path

from gtv_log import TASKS


root = Path(__file__).resolve().parent
public = root / "public"
public.mkdir(exist_ok=True)
tasks = [
    {"id": task_id, "title": title, "mode": mode, "action": action, "doneWhen": done_when}
    for task_id, title, mode, action, done_when in TASKS
]
(public / "tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(public / "style.css").write_text((root / "theme.css").read_text(encoding="utf-8"), encoding="utf-8")
print(f"Prepared {len(tasks)} generic tasks; no local evidence exported.")
