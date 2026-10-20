import { useEffect, useState } from "react";
import { api } from "../api";
import { cny } from "../format";
import { Chip, useApp } from "../shared";
import type { ActionView } from "./Action";

type Audit = { audit_id: number; ts: string; actor_type: string; actor_id: string | null; event_type: string; action_id: string | null; tool_name: string | null; decision_code: string | null; detail: Record<string, unknown> };

export function Receipt() {
  const { ws, showError, notify, go } = useApp();
  const [actions, setActions] = useState<ActionView[]>([]);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const load = async () => {
    try {
      const a = await api.get<ActionView[]>("/api/actions");
      setActions(a);
      setAudit(await api.get<Audit[]>("/api/audit"));
      setSelected((s) => s ?? a.find((x) => x.state === "succeeded")?.action_id ?? null);
    } catch (e) { showError(e); }
  };
  useEffect(() => { load(); }, [ws.business.input_version, ws.sandbox?.ledger_version]);
  const act = actions.find((a) => a.action_id === selected);
  const refreshState = async () => {
    if (!act) return;
    try {
      const fresh = await api.get<ActionView>(`/api/actions/${act.action_id}`);
      setActions((list) => list.map((x) => (x.action_id === fresh.action_id ? fresh : x)));
      notify(`State refreshed from the server: ${fresh.state}. Refreshing never re-executes an action.`);
    } catch (e) { showError(e); }
  };
  const r = act?.receipt;
  return (
    <section>
      <h1>Receipt &amp; audit</h1>
      <div className="row">
        <label>Action <select value={selected ?? ""} onChange={(e) => setSelected(e.target.value || null)}>
          <option value="">Select…</option>
          {actions.map((a) => <option key={a.action_id} value={a.action_id}>{a.action_id} · {a.state} · {cny(a.payload.amount_minor as number)}</option>)}
        </select></label>
        <button onClick={refreshState} disabled={!act}>Refresh action state</button>
        <button onClick={() => go("decision")}>Return to decision</button>
      </div>
      {act && !r && <div className="banner warn">Action {act.action_id} is <strong>{act.state}</strong>; there is no receipt. {act.failure_reason}</div>}
      {r && (
        <div className="card receipt">
          <div className="row between"><h2>Sandbox receipt {r.receipt_id}</h2><Chip tone="ok">{r.status as string}</Chip></div>
          <p className="small muted">{r.note as string}</p>
          <dl className="kv">
            <dt>Action</dt><dd>{r.action_id}</dd>
            <dt>Settled amount</dt><dd><strong>{cny(r.settled_amount_minor as number)}</strong> to {r.recipient_name as string} ({r.recipient_id}) · {r.recipient_account_masked}</dd>
            <dt>Sandbox balance</dt><dd>{cny(r.balance_before_minor as number)} → <strong>{cny(r.balance_after_minor as number)}</strong></dd>
            <dt>Simulated date</dt><dd>{r.simulated_date}</dd>
            <dt>Settlement</dt><dd>{r.settlement_id} linked to obligation <a href={`#/evidence`}>{r.obligation_event_id}</a>; the remaining CNY 70,000 instalment stays scheduled for 2026-11-16.</dd>
            <dt>Sources</dt><dd>run {r.financial_run_id} · input v{r.input_version} · account v{r.account_version_before} → v{r.account_version_after} · policy {r.policy_version}</dd>
            <dt>Approval</dt><dd>{r.approval_id} by {r.approved_by} at {r.approved_at} (expires {r.approval_expires_at})</dd>
            <dt>Executed</dt><dd>{r.executed_at} (UTC) via {r.executed_via}</dd>
            <dt>Payload hash</dt><dd className="mono">{r.payload_hash}</dd>
          </dl>
        </div>
      )}
      <div className="card">
        <div className="row between">
          <h2>Evidence export</h2>
          <span className="row">
            <a className="button" href="/api/export?format=zip" download>Download evidence ZIP</a>
            <a className="button" href="/api/export?format=json" download="orderbridge-evidence.json">Download JSON</a>
            <a className="button" href="/api/export?format=csv" download>Download records CSV</a>
          </span>
        </div>
        <p className="small muted">Contains input versions, assumptions, run IDs, actions, approvals, settlements, agent tool logs and the audit trail. No passwords, session tokens or API keys.</p>
      </div>
      <div className="card">
        <h2>Audit trail</h2>
        <div className="table-scroll">
          <table className="data compact">
            <thead><tr><th>#</th><th>UTC time</th><th>Actor</th><th>Event</th><th>Action</th><th>Tool</th><th>Decision</th><th>Detail</th></tr></thead>
            <tbody>{audit.map((a) => (
              <tr key={a.audit_id}><td>{a.audit_id}</td><td className="small">{a.ts}</td><td>{a.actor_type}</td><td>{a.event_type}</td><td className="small">{a.action_id}</td>
                <td>{a.tool_name}</td><td>{a.decision_code}</td><td className="small detail">{JSON.stringify(a.detail)}</td></tr>))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
