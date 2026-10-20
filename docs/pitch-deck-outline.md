# Pitch deck outline (10 slides, ~5 minutes)

Mentor notes are in *italics*. Every market statement must be either cited from a source you have checked yourself, or phrased as a hypothesis. Do not add numbers that are not in this project or a source you have read.

1. **Title.** OrderBridge: accept the order, keep payroll safe. Topic E, SME Finance Copilot. *Put the "synthetic prototype" label on the slide.*

2. **The moment of decision.** A trading SME gets a large order with a healthy margin. Suppliers want paying on day 3, payroll is due on day 7, and the buyer pays on day 45. *This is the reference case. Tell it as a story with the step chart.*

3. **Why it is hard today.** Spreadsheets mix profit with cash timing. Financing options arrive before the owner knows the real gap. Negotiation levers (a deposit, supplier deferral) are rarely priced against each other. *Phrase these as observed problems or hypotheses to validate. If you have interviews or a cited study, add them here; otherwise say "hypothesis".*

4. **What OrderBridge does.** One question in, then: evidence → daily cash with and without the order → six plans compared → missing evidence flagged → one exact simulated action, approved by the owner.

5. **Demo screenshots.** Decision (−90,000 on day 10, 110,000 support needed) → Compare (deposit plus deferral gives a minimum of 46,000 without debt; illustrative loan costs 2,055.07) → Approval (176,000 → 106,000).

6. **Trust by design (the differentiator).**
   - The AI explains; the deterministic engine calculates.
   - Fact references point to stored runs.
   - Negotiated terms stay *proposed* until the owner records acceptance.
   - Approval binds the exact payload hash and expires in 10 minutes.
   - A server policy gateway enforces limits.
   - Execution is idempotent and audited.

   *Say plainly: cash planning itself is not new; the evidence → decision → controlled-action chain is the contribution.*

7. **Responsible finance.** It recommends debt-free terms before credit. Loans are illustrative, eligibility is never assessed, and it never optimises for commission. It does not guarantee the buyer's payment. *Judges in bank-sponsored contests look for this.*

8. **Evidence it works.** 59 backend tests, 3 browser tests, independent reference verifier 10/10, and the prompt-injection and stale-approval tests (from `docs/test-report.md`). Live-model status: report it honestly.

9. **Path to a pilot (hypotheses, not commitments).**
   - Possible next steps: bank-statement and e-invoice import, multi-currency, a partner-bank sandbox API, real counterparty e-signature for terms.
   - Possible business models to test: a feature inside a bank's SME app, or a SaaS for SME accountants.
   - *Do not claim partnerships or pricing.*

10. **Ask and team.** What you want from the judges or mentors (pilot data, sandbox access, feedback). Team roles.

**Appendix:** architecture diagram (from `technical-design.md` section 1), limitations slide (from `limitations.md`).
