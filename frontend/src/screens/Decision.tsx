import { useState } from "react";
import { api } from "../api";
import { CashChart } from "../CashChart";
import { Envelope, Run, runFor, useComparison } from "../comparison";
import { cny } from "../format";
import { decisionLabel, decisionTone, Metric, useApp } from "../shared";

export function Decision() {
  const { ws, go } = useApp();
  const comp = useComparison();
  if (ws.record_count === 0) return <section><h1>Order decision</h1><p>Load the synthetic example on <a href="#/overview">Overview</a> first.</p></section>;
  if (!comp) return <section><h1>Order decision</h1><p>Calculating…</p></section>;
  const cur = runFor(comp, "current_terms");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const m = cur.metrics as Record<string, any>;
  const e = cur.economics as Record<string, number>;
  const ref = (k: string) => `${cur.run_id} · ${k}`;
  return (
    <section>
      <p className="kicker">Order decision for ORDER-001</p>
      <h1 className="question">Can I accept this CNY 220,000 order without missing payroll?</h1>
      <DecisionBanner env={comp.decision} />
      {!cur.complete && (
        <div className="banner bad">Incomplete forecast. {cur.issues.map((i) => i.message).join(" ")} <a href="#/evidence">Fix in Evidence</a></div>
      )}
      <h2>Order economics</h2>
      <p className="small muted">Whether the order pays, kept separate from when the cash moves.</p>
      <div className="metrics">
        <Metric label="Order revenue" value={cny(e.order_revenue_minor)} sub="buyer receipt due day 45 (2026-11-15)" />
        <Metric label="Incremental costs" value={cny(e.incremental_cost_minor)} sub="materials day 3 + fulfilment day 10" />
        <Metric label="Contribution before financing" value={cny(e.contribution_before_financing_minor)} sub="incremental cash contribution, fixed overhead excluded; not net profit" />
      </div>
      <h2>Cash on current terms</h2>
      <div className="metrics">
        <Metric label="First shortfall (below zero)" value={m.first_negative_date ?? "None"} sub={m.first_negative_day !== null ? `day ${m.first_negative_day}` : ""} tone={m.first_negative_date ? "bad" : "ok"} refText={ref("first_negative_date")} />
        <Metric label="Lowest balance" value={cny(m.lowest_balance_minor)} sub={`first reached ${m.lowest_balance_date} (day ${m.lowest_balance_day})`} tone={m.lowest_balance_minor < ws.business.buffer_minor ? "bad" : "ok"} refText={ref("lowest_balance_minor")} />
        <Metric label="Support needed to keep buffer" value={cny(m.required_support_minor)} sub={`buffer ${cny(ws.business.buffer_minor)} − lowest balance`} tone={m.required_support_minor > 0 ? "warn" : "ok"} refText={ref("required_support_minor")} />
        <Metric label="Ending balance" value={cny(m.ending_balance_minor)} sub={`on ${cur.daily[cur.daily.length - 1].date}`} refText={ref("ending_balance_minor")} />
      </div>
      <CashChart title="Projected end-of-day cash: current terms vs no order" bufferMinor={ws.business.buffer_minor}
        series={[{ key: "cur", label: "Accept on current terms", daily: cur.daily, color: "primary" }, { key: "no", label: "No order (baseline)", daily: runFor(comp, "no_order").daily, color: "compare" }]} />
      <Why run={cur} buffer={ws.business.buffer_minor} />
      <AgentPanel />
      <div className="row"><button className="primary" onClick={() => go("compare")}>Compare plans</button></div>
    </section>
  );
}

export function DecisionBanner({ env }: { env: Envelope }) {
  const tone = decisionTone[env.decision_code] ?? "info";
  const mark = { ok: "✓", warn: "!", bad: "✕", info: "i" }[tone];
  return (
    <div className={`decision ${tone}`}>
      <div className="verdict">
        <span className="verdict-mark" aria-hidden="true">{mark}</span>
        <span className="verdict-label">{decisionLabel[env.decision_code] ?? env.decision_code}</span>
      </div>
      <div className="decision-body">
        <p className="summary">{env.summary}</p>
        {env.fact_refs.length > 0 && <p className="small muted">Facts: {env.fact_refs.map((f) => `${f.metric_key} @ ${f.run_id}`).join(", ")}</p>}
        <p className="small muted">Source: {env.mode_label ?? (env.execution_mode === "calculation" ? "Deterministic calculation (no model)" : env.execution_mode)}</p>
      </div>
    </div>
  );
}

function Why({ run, buffer }: { run: Run; buffer: number }) {
  const [open, setOpen] = useState(false);
  const minDay = run.metrics.lowest_balance_day as number;
  const ledger = Object.fromEntries(run.ledger.map((l) => [l.event_id, l]));
  const steps = run.daily.filter((d) => d.day === 0 || d.event_refs.length > 0);
  return (
    <div className="card">
      <button className="link-btn h3" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "▾" : "▸"} Why this result</button>
      {open && (
        <>
          <p className="small">Daily closing cash = prior day's closing + that day's receipts − that day's payments. Opening cash {cny(run.metrics.opening_cash_minor as number)} on {run.daily[0].date}. This is calculation output, not model reasoning.</p>
          <table className="data compact">
            <thead><tr><th>Day</th><th>Date</th><th>Events</th><th className="num">In</th><th className="num">Out</th><th className="num">Closing</th></tr></thead>
            <tbody>
              {steps.map((d) => (
                <tr key={d.day} className={d.day === minDay ? "selected" : ""}>
                  <td>{d.day}</td><td>{d.date}</td>
                  <td>{d.event_refs.map((r) => <a key={r} href={`#/evidence?id=${r}`} className="ref">{r}{ledger[r]?.origin !== "record" ? "*" : ""}</a>)}</td>
                  <td className="num">{d.inflow_minor ? cny(d.inflow_minor) : ""}</td><td className="num">{d.outflow_minor ? cny(d.outflow_minor) : ""}</td>
                  <td className={`num ${d.closing_minor < 0 ? "neg" : ""}`}>{cny(d.closing_minor)}{d.day === minDay ? " ← lowest" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small">Support needed = max(0, buffer {cny(buffer)} − lowest {cny(run.metrics.lowest_balance_minor as number)}) = {cny(run.metrics.required_support_minor as number)}. The material payment on day 3 lands 42 days before the buyer pays on day 45.</p>
          <ul className="small muted">{run.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
        </>
      )}
    </div>
  );
}

function AgentPanel() {
  const { ws, showError, refresh } = useApp();
  const [q, setQ] = useState("Can I accept this CNY 220000 order without missing payroll?");
  const [env, setEnv] = useState<Envelope | null>(null);
  const [busy, setBusy] = useState(false);
  const live = ws.agent.mode === "live";
  const ask = async () => {
    setBusy(true);
    try { setEnv(await api.post<Envelope>("/api/agent/tasks", { task: "analyze_order", question: q })); await refresh(); }
    catch (e) { showError(e); setEnv(null); } finally { setBusy(false); }
  };
  return (
    <div className="card">
      <h2>Ask OrderBridge <span className={`badge ${live ? "live" : "replay"}`}>{live ? "Live AI" : "Rule-based replay, no live model"}</span></h2>
      <p className="small muted">The agent may only call bounded read and calculation tools, and may draft (never approve) a sandbox payment. Numbers come from the engine.</p>
      <div className="row">
        <input className="grow" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Question for the agent" maxLength={500} disabled={!live} />
        <button className="primary" onClick={ask} disabled={busy || ws.user.role !== "owner"}>{busy ? "Running…" : live ? "Ask live agent" : "Run replay"}</button>
      </div>
      {!live && <p className="small muted">Replay runs a fixed, deterministic tool sequence for the reference question.</p>}
      {env && (
        <>
          <DecisionBanner env={env} />
          {Boolean(env.model_output_error) && <div className="banner warn small">Model output error flagged: {JSON.stringify(env.model_output_error)}</div>}
          {env.proposed_actions.filter((p) => p.action_id).map((p) => (
            <div key={p.action_id} className="banner info small">Drafted sandbox action {p.action_id} ({p.state}). Review and approve it yourself on <a href="#/action">Approval &amp; action</a>.</div>
          ))}
          <details>
            <summary>Tool calls ({env.tool_log?.length ?? 0}) · run {env.agent_run_id}</summary>
            <table className="data compact"><thead><tr><th>#</th><th>Tool</th><th>Outcome</th><th>Result IDs</th><th className="num">ms</th></tr></thead>
              <tbody>{env.tool_log?.map((t, i) => <tr key={i}><td>{i + 1}</td><td>{t.tool}</td><td>{t.outcome}{t.error_code ? ` (${t.error_code})` : ""}</td><td className="small">{t.result_ids.join(", ")}</td><td className="num">{t.elapsed_ms}</td></tr>)}</tbody></table>
          </details>
        </>
      )}
    </div>
  );
}
