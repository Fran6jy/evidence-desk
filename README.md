# Evidence Desk

Evidence Desk is a personal evidence tracker for a digital technology Global Talent endorsement application. It has two parts:

- **Local scanner:** `gtv_log.py` reads Git activity in sibling project folders and captures files placed in `Proof inbox`. It creates a local SQLite database, review CSV, and HTML dashboard.
- **Browser companion:** the static site in `public/` can import the local review CSV, track checklist progress, and export a JSON backup. Browser data stays in that browser's local storage. It does not sync with the local scanner.

This repository contains code and a generic task template. Personal evidence files, the SQLite database, generated review queue, and local deployment settings are excluded by `.gitignore` and must not be committed.

## Run locally

Use Python 3 with Git installed. `pypdf` enables PDF page-count checks.

```text
python gtv_log.py scan
python gtv_log.py serve
```

Or double-click `Open dashboard.cmd` on Windows. The server binds to `127.0.0.1:8765`. Put original supporting files in `Proof inbox`. Each scan deduplicates activity and preserves review notes.

To update a row from the command line, copy its ID from `Review queue.csv`:

```text
python gtv_log.py review ID --status "Developing" --criterion "Optional 1" --impact "Verified outcome" --corroboration "Named third-party source"
```

Run `python prepare_web.py` after changing `TASKS` or `theme.css`; it regenerates `public/tasks.json` and `public/style.css` without exporting personal evidence. The `public/` directory is the Vercel output directory. It is plain HTML, CSS and JavaScript with no backend.

## What the checks mean

The local pre-submission review flags missing files, duplicate files, missing review fields, PDF page counts, criterion coverage and the ten-document maximum. The browser copy flags missing details and criterion coverage, but cannot inspect files on the user's computer. Neither version authenticates sources or decides endorsement eligibility. Check the [current GOV.UK document guidance](https://www.gov.uk/global-talent-digital-technology/documents-you-need-to-apply-endorsement) before submitting.

## Privacy and authorship

The hosted page starts empty. Importing a CSV reads it in the browser; no import endpoint exists. Browser edits are saved on that device, so export a backup before clearing browser storage. The repository is maintained by Francis Babatunde. Outside pull requests are not part of this project.
