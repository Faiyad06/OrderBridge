import { useState } from "react";
import { api } from "../api";
import { cny } from "../format";
import { Chip, Metric, useApp } from "../shared";

type ImportRow = { row_number: number; status: string; original: Record<string, string>; normalized: Record<string, unknown>;
  issues: { field: string; message: string; severity: string }[]; duplicate: string };
type ImportPreview = { import_id: string; filename: string; status: string; counts: Record<string, number>; can_commit: boolean; rows: ImportRow[] };

const rowTone = (s: string) => (s === "valid" ? "ok" : s === "duplicate_identical" ? "muted" : s === "conflict" ? "warn" : "bad");
const rowLabel: Record<string, string> = { valid: "Valid, new", duplicate_identical: "Exact duplicate (no change)", conflict: "Conflict, review", invalid: "Invalid" };

export function Overview() {
  const { ws, refresh, go, showError, notify, isOwner } = useApp();
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const b = ws.business;

  const loadExample = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ loaded: { created: number }[] }>("/api/workspace/load-example");
      const created = r.loaded.reduce((s, x) => s + x.created, 0);
      notify(created ? `Synthetic example loaded: ${created} records added.` : "Synthetic example already loaded; exact duplicates were not added again.");
      await refresh();
    } catch (e) { showError(e); } finally { setBusy(false); }
  };

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    const form = new FormData();
    form.append("file", f);
    try { setPreview(await api.upload<ImportPreview>("/api/imports/preview", form)); } catch (x) { showError(x); }
  };

  const fixRow = async (row: number, changes: Record<string, unknown>) => {
    try { setPreview(await api.patch<ImportPreview>(`/api/imports/${preview!.import_id}/rows/${row}`, { changes })); } catch (x) { showError(x); }
  };

  const commit = async () => {
    try {
      const r = await api.post<{ created: number; unchanged: number; input_version: number }>(`/api/imports/${preview!.import_id}/commit`, { expected_version: ws.business.input_version });
      notify(`Import committed: ${r.created} new records, ${r.unchanged} exact duplicates unchanged. Data is now v${r.input_version}.`);
      setPreview(null);
      await refresh();
    } catch (x) { showError(x); }
  };

  return (
    <section>
      <div className="page-head">
        <div>
          <p className="kicker">Fictional business</p>
          <h1>{b.name}</h1>
          <ul className="meta">
            <li>Time zone <strong>{b.timezone}</strong></li>
            <li>Opening date <strong>{b.opening_date}</strong></li>
            <li>Forecast to <strong>{b.horizon_end}</strong></li>
          </ul>
        </div>
        <button className="primary big" onClick={() => go("decision")} disabled={ws.record_count === 0}>Analyze new order</button>
      </div>
      <div className="metrics">
        <Metric label="Opening cash" value={cny(b.opening_cash_minor)} sub={`on ${b.opening_date}`} />
        <Metric label="Owner buffer" value={cny(b.buffer_minor)} sub="minimum projected cash you want to keep" />
        <Metric label="Cash records" value={ws.record_count} sub={<a href="#/evidence">View evidence</a>} />
        <Metric label="Records requiring review" value={ws.review_count + ws.blocking_issue_count}
                tone={ws.blocking_issue_count ? "bad" : ws.review_count ? "warn" : "ok"}
                sub={ws.blocking_issue_count ? `${ws.blocking_issue_count} critical issue(s) block a complete decision` : "no blocking issues"} />
      </div>

      <div className="card">
        <h2>Get data in</h2>
        {ws.record_count === 0 && <p>No cash records yet. Load the labelled synthetic reference case or import a supported CSV.</p>}
        <div className="row">
          <button onClick={loadExample} disabled={!isOwner || busy}>Load synthetic example</button>
          <label className={`button ${!isOwner ? "disabled" : ""}`}>
            Import CSV
            <input type="file" accept=".csv,text/csv" onChange={onFile} disabled={!isOwner} className="sr-only" />
          </label>
          <a href="#/evidence">Open evidence</a>
        </div>
        <p className="muted small">Supported: UTF-8 cash_events.csv with columns event_id, date, direction, amount_cny, currency, category, counterparty_id,
          source_document_id, source_ref, confirmation_status, description. Max 5 MiB / 10,000 rows (local project policy). CNY only.</p>
        {!isOwner && <p className="muted small">You are signed in as a viewer: read-only.</p>}
      </div>

      {preview && (
        <div className="card">
          <h2>Review import: {preview.filename}</h2>
          <p>
            {Object.entries(preview.counts).map(([k, v]) => <Chip key={k} tone={rowTone(k)}>{v} {rowLabel[k] ?? k}</Chip>)}
          </p>
          <p className="muted small">Nothing is committed until you press Commit. Invalid and conflicting rows must be corrected or removed first; a partial subset is never committed silently.</p>
          <div className="table-scroll">
            <table className="data">
              <thead><tr><th>Row</th><th>Status</th><th>event_id</th><th>Original date</th><th>Original amount</th><th>Direction</th><th>Issues</th><th>Fix</th></tr></thead>
              <tbody>
                {preview.rows.map((r) => <ImportRowView key={r.row_number} r={r} onFix={fixRow} />)}
              </tbody>
            </table>
          </div>
          <div className="row">
            <button className="primary" disabled={!preview.can_commit} onClick={commit}>Commit import as new data version</button>
            <button onClick={() => setPreview(null)}>Discard preview</button>
          </div>
        </div>
      )}
    </section>
  );
}

function ImportRowView({ r, onFix }: { r: ImportRow; onFix: (row: number, c: Record<string, unknown>) => void }) {
  const [date, setDate] = useState(r.original.date ?? "");
  const [amount, setAmount] = useState(r.original.amount_cny ?? "");
  const editable = r.status === "invalid" || r.status === "conflict";
  return (
    <tr>
      <td>{r.row_number}</td>
      <td><Chip tone={rowTone(r.status)}>{rowLabel[r.status] ?? r.status}</Chip></td>
      <td>{r.original.event_id}</td>
      <td>{r.original.date}</td>
      <td className="num">{r.original.amount_cny}</td>
      <td>{r.original.direction}</td>
      <td>{r.issues.map((i, k) => <div key={k} className={`issue ${i.severity}`}>{i.field}: {i.message}</div>)}</td>
      <td>
        {editable && (
          <div className="fix">
            <input aria-label={`Date for row ${r.row_number}`} value={date} onChange={(e) => setDate(e.target.value)} placeholder="YYYY-MM-DD" />
            <input aria-label={`Amount for row ${r.row_number}`} value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
            <button onClick={() => onFix(r.row_number, { date, amount_cny: amount })}>Apply correction</button>
            <button onClick={() => onFix(r.row_number, { _remove: true })}>Remove row</button>
          </div>
        )}
      </td>
    </tr>
  );
}
