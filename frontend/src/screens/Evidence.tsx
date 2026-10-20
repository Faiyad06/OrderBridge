import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { cny, statusLabel, toDecimalString } from "../format";
import { Chip, useApp } from "../shared";

export type EvRecord = { event_id: string; date: string | null; direction: string; amount_minor: number | null; currency: string; category: string;
  counterparty_id: string | null; source_document_id: string; source_ref: string; confirmation_status: string; description: string; order_id: string | null;
  record_version: number; settled_minor: number; issues: { field: string; severity: string; message: string }[]; original: Record<string, string> };
type Detail = EvRecord & { edits: { field: string; old_value: string | null; new_value: string | null; actor: string; ts: string; input_version: number }[];
  source: { source_id: string; label: string; sha256: string; source_type: string; created_at: string } | null };

const statusTone = (s: string) => (s === "user_confirmed" ? "ok" : s === "missing" ? "bad" : s === "parsed_unconfirmed" ? "warn" : "info");
type SortKey = "date" | "event_id" | "amount_minor" | "confirmation_status" | "direction";

export function Evidence() {
  const { ws, refresh, showError, notify, isOwner } = useApp();
  const [records, setRecords] = useState<EvRecord[]>([]);
  const [sort, setSort] = useState<{ key: SortKey; asc: boolean }>({ key: "date", asc: true });
  const [selected, setSelected] = useState<string | null>(() => new URLSearchParams(window.location.hash.split("?")[1]).get("id"));
  const [detail, setDetail] = useState<Detail | null>(null);

  const load = async () => {
    try { setRecords((await api.get<{ records: EvRecord[] }>("/api/evidence")).records); } catch (e) { showError(e); }
  };
  useEffect(() => { load(); }, [ws.business.input_version]);
  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    api.get<Detail>(`/api/evidence/${encodeURIComponent(selected)}`).then(setDetail).catch(showError);
  }, [selected, ws.business.input_version]);

  const sorted = useMemo(() => {
    const r = [...records];
    r.sort((a, b) => {
      const av = a[sort.key] ?? "", bv = b[sort.key] ?? "";
      return (av < bv ? -1 : av > bv ? 1 : 0) * (sort.asc ? 1 : -1);
    });
    return r;
  }, [records, sort]);

  const th = (key: SortKey, label: string, cls = "") => (
    <th className={cls} aria-sort={sort.key === key ? (sort.asc ? "ascending" : "descending") : "none"}>
      <button className="th-btn" onClick={() => setSort({ key, asc: sort.key === key ? !sort.asc : true })}>{label}{sort.key === key ? (sort.asc ? " ▲" : " ▼") : ""}</button>
    </th>
  );
  const blocking = records.filter((r) => r.issues.some((i) => i.severity === "critical"));

  return (
    <section>
      <h1>Evidence</h1>
      <p className="muted">Every cash record with its source document, row reference and confirmation status. The evidence index is provenance only; it is not a second transaction source.</p>
      {blocking.length > 0 && (
        <div className="banner bad" role="alert">
          {blocking.length} record(s) have missing critical fields, so the decision is blocked: {blocking.map((r) => r.event_id).join(", ")}. Select a record and add the missing value.
        </div>
      )}
      <div className="split">
        <div className="table-scroll grow">
          <table className="data clickable">
            <thead><tr>{th("event_id", "Record")}{th("date", "Date")}{th("direction", "Direction")}{th("amount_minor", "Amount", "num")}<th>Counterparty</th><th>Source</th>{th("confirmation_status", "Status")}</tr></thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.event_id} className={selected === r.event_id ? "selected" : ""} onClick={() => setSelected(r.event_id)}>
                  <td><button className="link-btn" onClick={() => setSelected(r.event_id)}>{r.event_id}</button>{r.order_id && <span className="tag">{r.order_id}</span>}</td>
                  <td>{r.date ?? <Chip tone="bad">Missing</Chip>}</td>
                  <td>{r.direction === "in" ? "Receipt" : "Payment"}</td>
                  <td className="num">{r.amount_minor === null ? <Chip tone="bad">Missing</Chip> : cny(r.amount_minor)}</td>
                  <td>{r.counterparty_id}</td>
                  <td className="small">{r.source_document_id}<br /><span className="muted">{r.source_ref}</span></td>
                  <td><Chip tone={statusTone(r.confirmation_status)}>{statusLabel[r.confirmation_status] ?? r.confirmation_status}</Chip>
                    {r.settled_minor > 0 && <div className="small muted">Settled in sandbox {cny(r.settled_minor)}</div>}</td>
                </tr>
              ))}
              {sorted.length === 0 && <tr><td colSpan={7}>No records. Load the synthetic example from Overview.</td></tr>}
            </tbody>
          </table>
        </div>
        {detail && <DetailPanel d={detail} isOwner={isOwner} onClose={() => setSelected(null)}
          onSaved={async (msg) => { notify(msg); await refresh(); await load(); }} onError={showError} />}
      </div>
    </section>
  );
}

function DetailPanel({ d, isOwner, onClose, onSaved, onError }: { d: Detail; isOwner: boolean; onClose: () => void; onSaved: (m: string) => void; onError: (e: unknown) => void }) {
  const [date, setDate] = useState(d.date ?? "");
  const [amount, setAmount] = useState(d.amount_minor === null ? "" : toDecimalString(d.amount_minor));
  const [status, setStatus] = useState(d.confirmation_status);
  useEffect(() => { setDate(d.date ?? ""); setAmount(d.amount_minor === null ? "" : toDecimalString(d.amount_minor)); setStatus(d.confirmation_status); }, [d]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const changes: Record<string, unknown> = {};
    if (date !== (d.date ?? "")) changes.date = date || null;
    if (amount !== (d.amount_minor === null ? "" : toDecimalString(d.amount_minor))) changes.amount_cny = amount || null;
    if (status !== d.confirmation_status) changes.confirmation_status = status;
    if (!Object.keys(changes).length) return;
    try {
      await api.patch(`/api/records/${encodeURIComponent(d.event_id)}`, { changes, expected_record_version: d.record_version });
      onSaved(`${d.event_id} corrected. A new data version was created and any pending approvals were invalidated.`);
    } catch (x) { onError(x); }
  };
  const norm: [string, string][] = [["date", d.date ?? "(missing)"], ["direction", d.direction], ["amount", d.amount_minor === null ? "(missing)" : cny(d.amount_minor)],
    ["currency", d.currency], ["category", d.category], ["counterparty", d.counterparty_id ?? ""], ["status", statusLabel[d.confirmation_status] ?? d.confirmation_status]];
  return (
    <aside className="side card" aria-label={`Source details for ${d.event_id}`}>
      <div className="row between"><h2>{d.event_id}</h2><button className="link-btn" onClick={onClose}>Close</button></div>
      {d.issues.map((i, k) => <div key={k} className="banner bad small">{i.message}</div>)}
      <h3>Original source values vs normalized</h3>
      <table className="data compact">
        <thead><tr><th>Field</th><th>Original</th><th>Normalized</th></tr></thead>
        <tbody>
          {norm.map(([k, v]) => {
            const ok = k === "amount" ? "amount_cny" : k === "counterparty" ? "counterparty_id" : k === "status" ? "confirmation_status" : k;
            return <tr key={k}><td>{k}</td><td>{d.original[ok] ?? <span className="muted">—</span>}</td><td>{v}</td></tr>;
          })}
          <tr><td>description</td><td colSpan={2} className="untrusted">{d.description}</td></tr>
        </tbody>
      </table>
      <p className="small muted">Source: {d.source ? `${d.source.label} (${d.source.source_type}, sha256 ${d.source.sha256.slice(0, 12)}…)` : d.source_document_id} · {d.source_ref}</p>
      {isOwner && (
        <form onSubmit={save} className="edit-form">
          <h3>Correct this record</h3>
          <label>Date<input value={date} onChange={(e) => setDate(e.target.value)} placeholder="YYYY-MM-DD (empty = missing)" /></label>
          <label>Amount (CNY)<input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="e.g. 70000.00" inputMode="decimal" /></label>
          <label>Confirmation status
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {Object.entries(statusLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <button className="primary" type="submit">Save correction (new data version)</button>
        </form>
      )}
      <h3>Edit history</h3>
      {d.edits.length === 0 ? <p className="small muted">No edits. The original source representation is retained.</p> : (
        <table className="data compact"><thead><tr><th>Field</th><th>Old</th><th>New</th><th>By</th><th>When (UTC)</th></tr></thead>
          <tbody>{d.edits.map((e, k) => <tr key={k}><td>{e.field}</td><td>{e.old_value ?? "null"}</td><td>{e.new_value ?? "null"}</td><td>{e.actor}</td><td>{e.ts}</td></tr>)}</tbody></table>
      )}
    </aside>
  );
}
