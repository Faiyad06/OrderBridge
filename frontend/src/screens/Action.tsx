import { useEffect, useState } from "react";
import { api } from "../api";
import { cny } from "../format";
import { Chip, useApp } from "../shared";

export type ActionView = {
  action_id: string; state: string; payload: Record<string, string | number | null>; payload_hash: string; idempotency_key: string;
  policy_checks: { check: string; passed: boolean; detail: string; code: string | null }[]; failure_code: string | null; failure_reason: string | null;
  prepared_by: string; created_at: string; recipient: { recipient_id: string; display_name: string; test_account_masked: string | null; allowlisted: boolean };
  balance_before_minor: number | null; balance_after_minor: number | null;
  approval: { approval_id: string; actor_user_id: string; approved_at: string; expires_at: string; state: string } | null;
  receipt: Record<string, string | number> | null; obligation_source: Record<string, string>;
};

const stateTone = (s: string) => (s === "succeeded" ? "ok" : s === "approved" || s === "awaiting_approval" ? "warn" : ["blocked", "expired", "failed", "cancelled"].includes(s) ? "bad" : "info");
const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `k-${Date.now()}-${Math.random()}`);
const RECIPIENTS = [["SUP-MAT-001", "Demo Pearl Materials Co. (allowlisted)"], ["SUP-OTH-201", "Demo Packaging Supplier (not allowlisted)"], ["ATTACKER-0001", "Unknown recipient ATTACKER-0001"]];

export function ActionScreen() {
  const { ws, refresh, showError, notify, isOwner, go } = useApp();
  const [actions, setActions] = useState<ActionView[]>([]);
  const [current, setCurrent] = useState<string | null>(() => sessionStorage.getItem("ob_current_action"));
  const [amount, setAmount] = useState("70000.00");
  const [recipient, setRecipient] = useState("SUP-MAT-001");
  const [busy, setBusy] = useState(false);
  const accepted = ws.conditions.filter((c) => c.acceptable_by_owner).every((c) => c.status === "accepted");

  const load = async () => { try { setActions(await api.get<ActionView[]>("/api/actions")); } catch (e) { showError(e); } };
  useEffect(() => { load(); }, [ws.business.input_version, ws.sandbox?.ledger_version]);
  const pickCurrent = (id: string | null) => { setCurrent(id); id ? sessionStorage.setItem("ob_current_action", id) : sessionStorage.removeItem("ob_current_action"); };
  const act = actions.find((a) => a.action_id === current) ?? null;

  const run = async (fn: () => Promise<unknown>, msg?: string) => {
    setBusy(true);
    try { await fn(); if (msg) notify(msg); } catch (e) { showError(e); }
    finally { await refresh(); await load(); setBusy(false); }
  };

  const initialize = () => run(() => api.post("/api/sandbox/initialize"), "Synthetic sandbox initialized at simulated date 2026-10-04 (synthetic seeding, not a bank deposit).");
  const prepare = (amt = amount, rec = recipient) => run(async () => {
    // Keep the key across a reload so an accidental resubmit returns the same action.
    const sig = `${amt}|${rec}`;
    const stored = JSON.parse(sessionStorage.getItem("ob_prepare_key") ?? "null");
    const key = stored?.sig === sig ? stored.key : newKey();
    sessionStorage.setItem("ob_prepare_key", JSON.stringify({ sig, key }));
    const a = await api.post<ActionView>("/api/actions/prepare", { scenario_id: "combined_terms", obligation_event_id: "ORD-001-MAT-1", recipient_id: rec, amount: amt, idempotency_key: key });
    sessionStorage.removeItem("ob_prepare_key");
    pickCurrent(a.action_id);
  });
  const approve = (a: ActionView) => run(() => api.post(`/api/actions/${a.action_id}/approve`, { payload_hash: a.payload_hash }), `Approved exact payload ${a.payload_hash.slice(0, 12)}…. Approval expires in ${ws.policy.approval_ttl_seconds / 60} minutes.`);
  const execute = (a: ActionView) => run(() => api.post(`/api/actions/${a.action_id}/execute`, {}, { "Idempotency-Key": a.idempotency_key }), "Executed in the sandbox.");
  const executeViaAgent = (a: ActionView) => run(() => api.post("/api/agent/tasks", { task: "execute_approved", action_id: a.action_id }), "Agent run executed the one approved action.");
  const tryExecuteUnapproved = (a: ActionView) => run(() => api.post(`/api/actions/${a.action_id}/execute`, {}));
  const cancel = (a: ActionView) => run(() => api.post(`/api/actions/${a.action_id}/cancel`), "Action cancelled.");

  if (ws.record_count === 0) return <section><h1>Approval &amp; action</h1><p>Load the synthetic example on <a href="#/overview">Overview</a> first.</p></section>;

  return (
    <section>
      <h1>Approval &amp; sandbox action</h1>
      <p className="muted">Only a simulated supplier payment in an isolated sandbox. Every check is enforced on the server at execution time; buttons are a convenience, not the control.</p>
      {!ws.sandbox ? (
        <div className="card">
          <h2>Isolated day-3 sandbox</h2>
          <p>The sandbox starts immediately before the day-3 material payment for the <strong>accepted combined-terms</strong> case: CNY 100,000 opening + 66,000 deposit + 60,000 day-1 receipt − 50,000 day-2 payment = CNY 176,000 available.</p>
          {!accepted && <div className="banner warn">Record acceptance of both negotiated terms on <a href="#/compare">Compare plans</a> first.</div>}
          <button className="primary" disabled={!accepted || !isOwner || busy} onClick={initialize}>Initialize synthetic sandbox (simulated 2026-10-04)</button>
        </div>
      ) : (
        <div className="card">
          <div className="row between">
            <h2>Sandbox account {ws.sandbox.account_id}</h2>
            <span className="badge sim">Simulated date {ws.sandbox.simulated_date}</span>
          </div>
          <p className="sandbox-cash">Available sandbox cash: <strong>{cny(ws.sandbox.available_minor)}</strong></p>
          <p className="small muted">Account version {ws.sandbox.ledger_version}. Future receipts are not spendable here until settled.</p>
          {isOwner && (
            <div className="prepare">
              <label>Recipient
                <select value={recipient} onChange={(e) => setRecipient(e.target.value)}>{RECIPIENTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              </label>
              <label>Amount (CNY)<input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" /></label>
              <span className="small muted">Obligation: ORD-001-MAT-1 (instalment 1 of the deferred material payment)</span>
              <button className="primary" disabled={busy} onClick={() => prepare()}>Prepare payment preview</button>
              <button disabled={busy} onClick={() => { setAmount("120000.00"); setRecipient("SUP-MAT-001"); prepare("120000.00", "SUP-MAT-001"); }}>Demo: try CNY 120,000 (over limit)</button>
            </div>
          )}
        </div>
      )}

      {act && <ActionPreview a={act} busy={busy} isOwner={isOwner} onApprove={approve} onExecute={execute} onAgent={executeViaAgent}
                             onTryUnapproved={tryExecuteUnapproved} onCancel={cancel} onReceipt={() => go("receipt")} ttl={ws.policy.approval_ttl_seconds} />}

      {actions.length > 0 && (
        <div className="card">
          <h2>Actions</h2>
          <div className="table-scroll">
          <table className="data compact clickable">
            <thead><tr><th>Action</th><th>State</th><th className="num">Amount</th><th>Recipient</th><th>Prepared by</th><th>Created (UTC)</th><th>Reason</th></tr></thead>
            <tbody>{actions.map((a) => (
              <tr key={a.action_id} className={a.action_id === current ? "selected" : ""} onClick={() => pickCurrent(a.action_id)}>
                <td><button className="link-btn" onClick={() => pickCurrent(a.action_id)}>{a.action_id}</button></td>
                <td><Chip tone={stateTone(a.state)}>{a.state}</Chip></td><td className="num">{cny(a.payload.amount_minor as number)}</td>
                <td>{a.recipient.recipient_id}</td><td>{a.prepared_by}</td><td className="small">{a.created_at}</td><td className="small">{a.failure_reason}</td>
              </tr>))}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </section>
  );
}

function ActionPreview({ a, busy, isOwner, ttl, onApprove, onExecute, onAgent, onTryUnapproved, onCancel, onReceipt }: {
  a: ActionView; busy: boolean; isOwner: boolean; ttl: number; onApprove: (a: ActionView) => void; onExecute: (a: ActionView) => void; onAgent: (a: ActionView) => void;
  onTryUnapproved: (a: ActionView) => void; onCancel: (a: ActionView) => void; onReceipt: () => void }) {
  const p = a.payload;
  const amt = cny(p.amount_minor as number);
  return (
    <div className={`card preview ${a.state}`}>
      <div className="row between"><h2>Immutable action preview</h2><Chip tone={stateTone(a.state)}>{a.state.replace("_", " ")}</Chip></div>
      {a.failure_reason && <div className={`banner ${a.state === "succeeded" ? "ok" : "bad"}`}>{a.failure_code}: {a.failure_reason}</div>}
      <dl className="kv">
        <dt>Action</dt><dd>{a.action_id} · synthetic sandbox supplier payment</dd>
        <dt>Recipient</dt><dd>{a.recipient.display_name} ({a.recipient.recipient_id}) · test account {a.recipient.test_account_masked ?? "none"} · {a.recipient.allowlisted ? "allowlisted" : "NOT allowlisted"}</dd>
        <dt>Amount</dt><dd><strong>{amt}</strong> ({p.currency})</dd>
        <dt>Simulated execution date</dt><dd>{p.simulated_execution_date}</dd>
        <dt>Cash before → after</dt><dd>{cny(a.balance_before_minor)} → {cny(a.balance_after_minor)}</dd>
        <dt>Obligation</dt><dd>{p.obligation_event_id} {a.obligation_source.source_ref ?? a.obligation_source.note}</dd>
        <dt>Versions</dt><dd>plan {p.scenario_id} · run {p.financial_run_id} · input v{p.input_version} · account v{p.account_version} · policy {p.policy_version}</dd>
        <dt>Payload hash</dt><dd className="mono">{a.payload_hash}</dd>
        <dt>Approval</dt><dd>{a.approval ? `${a.approval.state} · by ${a.approval.actor_user_id} at ${a.approval.approved_at} · expires ${a.approval.expires_at} (UTC)` : `none yet · will expire ${ttl / 60} min after approval`}</dd>
      </dl>
      <h3>Policy checks (server-side)</h3>
      <ul className="checks">
        {a.policy_checks.map((c) => <li key={c.check} className={c.passed ? "pass" : "fail"}><span aria-hidden="true">{c.passed ? "✓" : "✕"}</span> <strong>{c.check}</strong> — {c.detail}{c.code ? ` (${c.code})` : ""}</li>)}
      </ul>
      {isOwner && (
        <div className="row wrap">
          {a.state === "awaiting_approval" && <button className="primary" disabled={busy} onClick={() => onApprove(a)}>Approve this exact {amt} payment</button>}
          {a.state === "awaiting_approval" && <button disabled={busy} onClick={() => onTryUnapproved(a)}>Demo: execute without approval</button>}
          {a.state === "approved" && <button className="primary" disabled={busy} onClick={() => onExecute(a)}>Execute approved sandbox payment</button>}
          {a.state === "approved" && <button disabled={busy} onClick={() => onAgent(a)}>Let the agent execute this approved action</button>}
          {(a.state === "awaiting_approval" || a.state === "approved") && <button disabled={busy} onClick={() => onCancel(a)}>Cancel action</button>}
          {a.state === "succeeded" && <button className="primary" onClick={onReceipt}>View receipt</button>}
        </div>
      )}
      <p className="small muted">To change the amount or recipient, prepare a new preview: a prepared payload never changes, and any changed amount, recipient, evidence, account or policy version needs a fresh approval.</p>
    </div>
  );
}
