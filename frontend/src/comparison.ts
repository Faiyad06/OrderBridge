import { useEffect, useState } from "react";
import { api } from "./api";
import type { DailyRow } from "./CashChart";
import { useApp } from "./shared";

export type ScenarioRow = { scenario_id: string; label: string; run_id: string; terms_status: string; complete: boolean; lowest_balance_minor: number;
  lowest_balance_date: string; first_negative_date: string | null; required_support_minor: number; ending_balance_minor: number;
  borrowed_principal_minor: number; financing_cost_minor: number; repayment_date: string | null; contribution_before_financing_minor: number;
  contribution_after_financing_minor: number; meets_buffer: boolean; conditions: { condition_id: string; label: string; status: string }[];
  unresolved_conditions: { condition_id: string; label: string; status: string }[] };
export type Run = { run_id: string; scenario_id: string; label: string; input_version: number; complete: boolean; issues: { event_id: string; message: string }[];
  assumptions: string[]; daily: DailyRow[]; metrics: Record<string, number | string | null>; economics: Record<string, number | string>;
  financing: Record<string, number | string> | null; ledger: { event_id: string; date: string | null; direction: string; amount_minor: number | null;
  origin: string; source_ref: string; replaces_event_id: string | null; condition_id: string | null; category: string }[] };
export type Envelope = { decision_code: string; summary: string; fact_refs: { run_id: string; metric_key: string }[]; evidence_refs: string[];
  assumptions: string[]; unresolved_conditions: unknown[]; proposed_actions: { type: string; action_id?: string; state?: string; scenario_id?: string }[];
  execution_mode: string; mode_label?: string; tool_log?: { tool: string; outcome: string; elapsed_ms: number; result_ids: string[]; error_code: string | null; args_summary: unknown }[];
  model_output_error?: unknown; agent_run_id?: string; receipt?: unknown };
export type Financing = { product_id: string; label: string; passes_hard_constraints: boolean; reasons: string[]; max_principal_minor: number; max_term_days: number;
  annual_simple_rate: string; fee_minor: number; required_evidence: string[]; credit_approval: string; disclaimer: string; simulated_total_cost_minor?: number };
export type Comparison = { input_version: number; scenarios: ScenarioRow[]; runs: Record<string, Run>; decision: Envelope; financing_options: Financing[] };

let cache: { key: string; data: Comparison } | null = null;

export function useComparison() {
  const { ws, showError } = useApp();
  const key = `${ws.business.input_version}:${ws.sandbox?.ledger_version ?? 0}`;
  const [data, setData] = useState<Comparison | null>(cache?.key === key ? cache.data : null);
  useEffect(() => {
    if (ws.record_count === 0) return;
    if (cache?.key === key) { setData(cache.data); return; }
    api.post<Comparison>("/api/comparisons", {}).then((d) => { cache = { key, data: d }; setData(d); }).catch(showError);
  }, [key, ws.record_count]);
  return data;
}

export const runFor = (c: Comparison, sid: string) => c.runs[c.scenarios.find((s) => s.scenario_id === sid)!.run_id];
