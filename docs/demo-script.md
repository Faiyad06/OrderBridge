# Four-minute demo script

**Before recording:** run `backend/.venv/bin/python scripts/reset_demo.py`, then `scripts/start.sh`, and open <http://127.0.0.1:8000> at 1366×900. Sign in as `owner@demo-gba`. Say once, at the start: **"Everything you see is synthetic; no real money, credit or bank is involved."**

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00–0:20 | Header | Point at the header badges: Synthetic demo, CNY, data version, Rule-based replay | "Demo GBA Trading has CNY 100,000 and wants to keep at least 20,000. A buyer offers a CNY 220,000 order." |
| 0:20–0:40 | 1 Overview | **Load synthetic example** | "Nine source records load through the same validated import path a real CSV would use." |
| 0:40–1:00 | 2 Evidence | Click ORD-001-MAT and show original vs normalized values and the source ref | "Every number traces to a source row. Missing fields stay missing; they never become zero." |
| 1:00–1:45 | 3 Order decision | Show the metric cards, then open **Why this result**, then **Run replay** | "The order earns CNY 60,000 of contribution, but materials (140,000) are due on day 3 and the buyer pays on day 45. Cash first goes negative on 2026-10-04 and bottoms at −90,000 on day 10. Keeping the buffer would need 110,000 of support. The agent badge says Rule-based replay: no live model is pretending here." |
| 1:45–2:30 | 4 Compare plans | Point at the six rows | "A 30% deposit alone still dips to −24,000. Supplier deferral alone dips to −20,000. Both together keep cash at or above 46,000 without borrowing. The illustrative loan works on paper: 110,000 drawn, CNY 2,055.07 in fictional cost. But credit is *not assessed*." |
| | | **Mark accepted in this synthetic case** → Confirm, for each term | "Picking a plan accepts nothing. I record each counterparty's agreement myself, and the time and actor are logged." |
| 2:30–3:20 | 5 Approval & action | **Initialize synthetic sandbox**, then **Prepare payment preview** | "The sandbox starts on day 3 with 176,000 actually settled. Future receipts don't count as spendable." |
| | | Show the recipient, masked account, 176,000 → 106,000, versions, hash and the 10 green checks | "This exact payload is frozen." |
| | | **Demo: execute without approval** | "The server refuses: APPROVAL_REQUIRED. The button state isn't the control; the server is." |
| | | **Approve this exact CNY 70,000.00 payment**, then **Execute approved sandbox payment** | |
| 3:20–3:40 | 6 Receipt & audit | Show the receipt, then **Refresh action state** | "176,000 to 106,000, settled once, linked to the day-3 obligation. The second 70,000 instalment stays scheduled for day 46. Refreshing never pays twice." |
| 3:40–4:00 | 5 → 6 | **Demo: try CNY 120,000 (over limit)**, then **Download evidence ZIP** | "Over the per-payment limit: blocked, even though cash would cover it. Everything (versions, runs, approvals, tool calls) exports for review." |

## Optional extra (if a live key is configured)

Click **Switch to live AI**, then **Ask live agent**. Show the tool-call list and the fact references. After you approve an action, click **Let the agent execute this approved action**.

## Recording

Recording is **pending**: no video was produced in the build environment. Suggested approach: OBS or the OS screen recorder at 1366×900, 30 fps, with microphone narration. Rehearse once after a fresh reset, because acceptance and execution change the database.
