# Limitations

## Implemented (works and is tested)
- Deterministic cash engine, six scenarios, financing constraint assessment, decision envelope.
- CSV import (staging, validation, duplicates and conflicts, correction, versioned commit), evidence browser, corrections with edit history.
- Owner-recorded synthetic term acceptance. Sandbox bootstrap. Immutable prepare, exact-hash approval, atomic idempotent execution and receipt.
- Sessions, CSRF and Origin checks, two tenants, owner and viewer roles, audit log, evidence export.
- Rule-based replay agent. Live adapter code, tested only with a scripted fake client.

## Simulated
- The sandbox account, payments, settlements and the "simulated date" are not connected to any bank. The receipt is a sandbox record.
- Counterparty acceptance is simulated by the owner pressing "Mark accepted in this synthetic case". No counterparty is contacted.

## Illustrative
- All three financing products are fictional, with fictional rates and fees. They are not offers and not WeBank pricing. Credit eligibility is never assessed.
- The business, customers, suppliers, documents and amounts are synthetic.

## Unverified
- The live model loop against the real Anthropic API (no key was available). See `test-report.md`.
- Behaviour under concurrent multi-user load beyond the 8-thread execution test. Browsers other than Chromium. Screen readers.
- Whether the forecast's end-of-day netting reflects intraday liquidity. It does not prove that payments and receipts on the same day can be netted.

## Known modelling simplifications
- Tax-inclusive cash amounts only. No VAT, FX or interest on deposits.
- A settlement linked to a scenario-only event (for example ORD-001-MAT-1) applies only to scenarios containing that event. A post-payment comparison of other scenarios does not show the sandbox payment.
- The sandbox is bootstrapped only for the accepted combined-terms case. Demonstrating another scenario needs a fresh workspace (`scripts/reset_demo.py`), so settled history is never rewritten.
- The order contribution is incremental cash contribution before fixed overhead, not net profit.
- The buyer receipt is a projection, never a guarantee.

## Deferred (out of scope for this submission)
- P1: invoice text or PDF extraction, extra partial-payment and credit-note handling, a delayed-receipt stress scenario, a recorded video.
- Excluded by the brief: real payments, credit applications, loan disbursement, FX, custody, crypto or blockchain, tax portals, WeChat, model training, multi-agent infrastructure.
