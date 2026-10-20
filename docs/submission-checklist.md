# Submission checklist

The deadline from earlier research was **20 October 2026, 21:59 Bangladesh time**. Working target: **18:00 BST that day**. Check the organiser's current published rules first; they override everything below.

## Ravi's manual actions (Claude did not and must not do these)
- [ ] Confirm team eligibility and registration status on the official FinTechathon site, and prepare any required identity documents yourself.
- [ ] Read the current Topic E brief, judging criteria, file-format and size limits, video length and language rules.
- [ ] Check whether a public code link is required. If so, create the repository, push it and check that no `.env` or `data/` is committed (`.gitignore` covers both).
- [ ] Optional but strongly recommended: add an API key locally and close the **live-agent gate** (`docs/test-report.md`, "Blocked or not run").
- [ ] Record the demo video using `docs/demo-script.md` (recording is still pending).
- [ ] Build the slide deck from `docs/pitch-deck-outline.md`. Only an outline exists; there is no deck file.
- [ ] Review every claim in the deck and video against `docs/limitations.md`.
- [ ] Submit through the published process.

## Package contents (prepared)
- [x] Runnable code: `backend/`, `frontend/`, `scripts/`, `fixtures/`, and a README with setup, run, test, build and reset commands
- [x] Technical document: `docs/technical-design.md`
- [x] Security self-assessment: `docs/security-self-assessment.md`
- [x] Actual test report: `docs/test-report.md`
- [x] Limitations: `docs/limitations.md`
- [x] Demo script: `docs/demo-script.md`
- [x] Browser screenshots: `docs/screenshots/`
- [x] Execution evidence: `GET /api/export?format=zip` after running the journey. Generate it fresh before submitting.
- [x] Pitch outline: `docs/pitch-deck-outline.md`
- [ ] Video file (pending, manual)
- [ ] Slide deck file (pending, manual)

## Claims hygiene (re-check before submitting)
- [ ] The words "Synthetic demo" appear on screen in every screenshot and in the video
- [ ] No bank logos, no implied WeBank partnership, no "approved loan" language
- [ ] No invented customers, savings percentages, approval rates or market-size figures without a cited source
- [ ] "Live AI" is only claimed if the live gate has actually been run
