import { createContext, useContext } from "react";
import type { ApiError } from "./api";

export type Condition = { condition_id: string; label: string; status: string; acceptable_by_owner: boolean; confirmed_by?: string; confirmed_at?: string };
export type Sandbox = { account_id: string; available_minor: number; simulated_date: string; ledger_version: number; scenario_id: string;
  ledger: { simulated_date: string; delta_minor: number; balance_after_minor: number; reason: string; event_id: string | null; action_id: string | null }[] };
export type Workspace = {
  user: { username: string; role: string; display_name: string }; csrf_token: string;
  business: { business_id: string; name: string; currency: string; timezone: string; opening_cash_minor: number; opening_date: string;
    buffer_minor: number; horizon_end: string; input_version: number; synthetic: boolean };
  record_count: number; blocking_issue_count: number; review_count: number; sandbox: Sandbox | null;
  agent: { mode: string; live_configured: boolean; model: string; label: string }; conditions: Condition[];
  policy: { policy_version: string; per_payment_limit_minor: number; daily_outgoing_limit_minor: number; min_account_buffer_minor: number; approval_ttl_seconds: number };
  permitted_operations: string[];
};

export type Ctx = {
  ws: Workspace;
  refresh: () => Promise<void>;
  go: (route: string) => void;
  showError: (e: unknown) => void;
  notify: (msg: string) => void;
  isOwner: boolean;
};
export const AppCtx = createContext<Ctx>(null as unknown as Ctx);
export const useApp = () => useContext(AppCtx);

export function errText(e: unknown): string {
  const err = e as ApiError;
  if (err && err.code) {
    const fields = err.field_errors ? " " + Object.entries(err.field_errors).map(([k, v]) => `${k}: ${v}`).join("; ") : "";
    return `${err.code}: ${err.user_message}${fields}${err.request_id ? ` (request ${err.request_id})` : ""}`;
  }
  return String((e as Error)?.message ?? e);
}

export function Chip({ tone, children }: { tone: "ok" | "warn" | "bad" | "info" | "muted"; children: React.ReactNode }) {
  const icon = { ok: "✓", warn: "!", bad: "✕", info: "i", muted: "·" }[tone];
  return <span className={`chip ${tone}`}><span aria-hidden="true">{icon}</span> {children}</span>;
}

export const conditionTone = (s: string) => (s === "accepted" ? "ok" : s === "not_assessed" ? "bad" : "warn");
export const termsTone = (s: string) => (s === "accepted" || s === "no_conditions" ? "ok" : s === "incomplete" ? "bad" : "warn");
export const termsLabel: Record<string, string> = {
  accepted: "Terms accepted", no_conditions: "No conditions", conditional: "Conditional", incomplete: "Incomplete inputs",
};

export function Metric({ label, value, sub, tone, refText }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: string; refText?: string }) {
  return (
    <div className={`metric ${tone ?? ""}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
      {refText && <div className="metric-ref" title="Fact reference: run and metric key">{refText}</div>}
    </div>
  );
}

export const decisionTone: Record<string, "ok" | "warn" | "bad" | "info"> = {
  ready_for_simulation: "ok", conditional_terms: "warn", funding_required: "warn", needs_information: "bad", blocked: "bad",
};
export const decisionLabel: Record<string, string> = {
  ready_for_simulation: "Ready for simulation", conditional_terms: "Conditional terms", funding_required: "Funding required",
  needs_information: "Needs information", blocked: "Blocked",
};
