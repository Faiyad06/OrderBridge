import { useState } from "react";
import { api } from "../api";
import { CashChart } from "../CashChart";
import { runFor, useComparison } from "../comparison";
import { cny } from "../format";
import { Chip, conditionTone, termsLabel, termsTone, useApp } from "../shared";

export function Compare() {
  const { ws, refresh, showError, notify, isOwner, go } = useApp();
  const comp = useComparison();
  const [selected, setSelected] = useState(() => sessionStorage.getItem("ob_selected_plan") ?? "combined_terms");
  const [confirming, setConfirming] = useState<string | null>(null);
  if (ws.record_count === 0) return <section><h1>Compare plans</h1><p>Load the synthetic example on <a href="#/overview">Overview</a> first.</p></section>;
  if (!comp) return <section><h1>Compare plans</h1><p>Calculating…</p></section>;
  const pick = (sid: string) => { setSelected(sid); sessionStorage.setItem("ob_selected_plan", sid); };
  const sel = comp.scenarios.find((s) => s.scenario_id === selected)!;

  const accept = async (cid: string, accept: boolean) => {
    try {
      await api.post(`/api/scenarios/combined_terms/conditions`, { condition_id: cid, accept });
      notify(accept ? `Recorded: ${cid} marked accepted in this synthetic case by ${ws.user.username}.` : `${cid} returned to proposed.`);
      setConfirming(null);
      await refresh();
    } catch (e) { showError(e); }
  };
  const allAccepted = ws.conditions.filter((c) => c.acceptable_by_owner).every((c) => c.status === "accepted");

  return (
    <section>
      <h1>Compare plans</h1>
      <p className="muted">Selecting a plan only changes what you are viewing. It does not accept any terms, borrow, or change account cash.</p>
      <div className="table-scroll">
        <table className="data plans">
          <thead><tr><th>Plan</th><th>Terms status</th><th>Keeps buffer</th><th className="num">Lowest cash</th><th>First below zero</th><th className="num">Support to keep buffer</th>
            <th className="num">Borrowed</th><th className="num">Finance cost</th><th>Repayment</th><th className="num">Contribution after financing</th><th className="num">Ending day 46</th><th>Unresolved conditions</th></tr></thead>
          <tbody>
            {comp.scenarios.map((s) => (
              <tr key={s.scenario_id} className={s.scenario_id === selected ? "selected" : ""} onClick={() => pick(s.scenario_id)}>
                <td><label className="radio"><input type="radio" name="plan" checked={s.scenario_id === selected} onChange={() => pick(s.scenario_id)} /> {s.label}</label></td>
                <td><Chip tone={termsTone(s.terms_status)}>{termsLabel[s.terms_status] ?? s.terms_status}</Chip></td>
                <td><Chip tone={s.meets_buffer ? "ok" : "bad"}>{s.meets_buffer ? "Yes" : "No"}</Chip></td>
                <td className={`num ${s.lowest_balance_minor < 0 ? "neg" : ""}`}>{cny(s.lowest_balance_minor)}<div className="small muted">{s.lowest_balance_date}</div></td>
                <td>{s.first_negative_date ?? "None"}</td>
                <td className="num">{cny(s.required_support_minor)}{s.borrowed_principal_minor > 0 && <div className="small muted">additional after the loan</div>}</td>
                <td className="num">{s.borrowed_principal_minor ? cny(s.borrowed_principal_minor) : "—"}</td>
                <td className="num">{s.financing_cost_minor ? cny(s.financing_cost_minor) : "—"}</td>
                <td>{s.repayment_date ?? "—"}</td>
                <td className="num">{cny(s.contribution_after_financing_minor)}</td>
                <td className="num">{cny(s.ending_balance_minor)}</td>
                <td className="small">{s.unresolved_conditions.length ? s.unresolved_conditions.map((c) => <div key={c.condition_id}><Chip tone={conditionTone(c.status)}>{c.status.replace("_", " ")}</Chip> {c.label}</div>) : "None"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <CashChart title={`Selected: ${sel.label} vs current terms`} bufferMinor={ws.business.buffer_minor}
        series={[{ key: "sel", label: sel.label, daily: runFor(comp, selected).daily, color: "primary" },
                 ...(selected !== "current_terms" ? [{ key: "cur", label: "Accept on current terms", daily: runFor(comp, "current_terms").daily, color: "compare" as const }] : [])]} />
      {selected === "illustrative_loan" && (
        <div className="banner warn">Illustrative product, fictional terms (not WeBank pricing). Loan draw {cny(sel.borrowed_principal_minor)} is reported separately from residual support {cny(sel.required_support_minor)}.
          Credit eligibility is not assessed, borrowing cannot be executed here, and order acceptance is never recommended on the basis of an unapproved loan.</div>
      )}

      <div className="card">
        <h2>Negotiated terms for the combined plan</h2>
        <p className="small muted">These are proposals until you record that the counterparty agreed. Use this only to represent acceptance within the synthetic case.</p>
        {ws.conditions.map((c) => (
          <div key={c.condition_id} className="condition">
            <div>
              <Chip tone={conditionTone(c.status)}>{c.status === "not_assessed" ? "Not assessed" : c.status === "accepted" ? "Accepted" : "Proposed"}</Chip> {c.label}
              {c.confirmed_by && c.status === "accepted" && <div className="small muted">Recorded by {c.confirmed_by} at {c.confirmed_at} (UTC)</div>}
            </div>
            {c.acceptable_by_owner && isOwner && (
              c.status === "accepted" ? <button onClick={() => accept(c.condition_id, false)}>Revert to proposed</button> :
              confirming === c.condition_id ? (
                <span className="row">
                  <button className="primary" onClick={() => accept(c.condition_id, true)}>Confirm: counterparty agreed</button>
                  <button onClick={() => setConfirming(null)}>Cancel</button>
                </span>
              ) : <button onClick={() => setConfirming(c.condition_id)}>Mark accepted in this synthetic case</button>
            )}
            {!c.acceptable_by_owner && <span className="small muted">Cannot be accepted here</span>}
          </div>
        ))}
        {allAccepted && <div className="row"><button className="primary" onClick={() => go("action")}>Continue to sandbox action</button></div>}
      </div>

      {comp.financing_options.length > 0 && (
        <div className="card">
          <h2>Illustrative financing catalogue</h2>
          <p className="small muted">Fictional products. Hard purpose, currency, amount and timing constraints are checked first; credit approval stays not assessed.</p>
          <div className="fin-grid">
            {comp.financing_options.map((f) => (
              <div key={f.product_id} className={`fin ${f.passes_hard_constraints ? "pass" : "fail"}`}>
                <div className="row between"><strong>{f.label}</strong><Chip tone={f.passes_hard_constraints ? "ok" : "bad"}>{f.passes_hard_constraints ? "Fits constraints" : "Excluded"}</Chip></div>
                <div className="small">Max {cny(f.max_principal_minor)} · up to {f.max_term_days} days · fictional {(Number(f.annual_simple_rate) * 100).toFixed(0)}% simple · fee {cny(f.fee_minor)}</div>
                <ul className="small">{f.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                <div className="small">Credit approval: <Chip tone="bad">Not assessed</Chip></div>
                <div className="small muted">Evidence a lender would ask for: {f.required_evidence.join(", ")}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
