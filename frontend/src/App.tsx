import { useCallback, useEffect, useState } from "react";
import { api, setCsrf } from "./api";
import { cny } from "./format";
import { AppCtx, Ctx, errText, type Workspace } from "./shared";
import { Overview } from "./screens/Overview";
import { Evidence } from "./screens/Evidence";
import { Decision } from "./screens/Decision";
import { Compare } from "./screens/Compare";
import { ActionScreen } from "./screens/Action";
import { Receipt } from "./screens/Receipt";

const ROUTES = [
  ["overview", "Overview"], ["evidence", "Evidence"], ["decision", "Order decision"],
  ["compare", "Compare plans"], ["action", "Approval & action"], ["receipt", "Receipt & audit"],
] as const;

// Small bridge glyph: one span over a gap.
export function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 30 18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M2 16V9M28 16V9M2 9Q15 -1 28 9M2 16h5M23 16h5" />
    </svg>
  );
}

// Which steps are finished, read from workspace state (not from where the user has clicked).
function doneSteps(ws: Workspace): Set<string> {
  const d = new Set<string>();
  const accepted = ws.conditions.filter((c) => c.acceptable_by_owner).every((c) => c.status === "accepted");
  const executed = Boolean(ws.sandbox?.ledger.some((l) => l.action_id));
  if (ws.record_count > 0) d.add("overview");
  if (ws.record_count > 0 && ws.blocking_issue_count === 0) d.add("evidence");
  if (ws.record_count > 0 && accepted) { d.add("decision"); d.add("compare"); }
  if (executed) { d.add("action"); d.add("receipt"); }
  return d;
}

const currentRoute = () => {
  const r = window.location.hash.replace(/^#\/?/, "").split("?")[0];
  return ROUTES.some(([k]) => k === r) ? r : "overview";
};

export default function App() {
  const [ws, setWs] = useState<Workspace | null>(null);
  const [needLogin, setNeedLogin] = useState(false);
  const [route, setRoute] = useState(currentRoute());
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const w = await api.get<Workspace>("/api/workspace");
      setCsrf(w.csrf_token);
      setWs(w);
      setNeedLogin(false);
    } catch (e) {
      if ((e as { status?: number }).status === 401) setNeedLogin(true);
      else setError(errText(e));
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    const f = () => setRoute(currentRoute());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);

  if (needLogin) return <Login onDone={refresh} />;
  if (!ws) return <div className="loading">{error ?? "Loading…"}</div>;

  const ctx: Ctx = {
    ws, refresh, isOwner: ws.user.role === "owner",
    go: (r) => { window.location.hash = `#/${r}`; window.scrollTo(0, 0); },
    showError: (e) => { setError(errText(e)); setNote(null); },
    notify: (m) => { setNote(m); setError(null); },
  };
  const liveUnavailable = ws.agent.mode === "live" && !ws.agent.live_configured;
  const done = doneSteps(ws);

  const switchMode = async () => {
    try { await api.post("/api/agent/mode", { mode: ws.agent.mode === "live" ? "replay" : "live" }); await refresh(); }
    catch (e) { ctx.showError(e); }
  };
  const logout = async () => { await api.post("/api/auth/logout"); setWs(null); setNeedLogin(true); };

  return (
    <AppCtx.Provider value={ctx}>
      <header className="topbar">
        <div className="brand"><BrandMark />OrderBridge</div>
        <div className="status-strip" aria-label="Workspace status">
          <span className="badge synthetic">Synthetic demo</span>
          <span className="badge">Base currency {ws.business.currency}</span>
          {ws.sandbox && <span className="badge sim">Simulated date {ws.sandbox.simulated_date}</span>}
          <span className="badge">Data v{ws.business.input_version}</span>
          <span className={`badge ${ws.agent.mode === "live" ? (liveUnavailable ? "bad" : "live") : "replay"}`}>
            {ws.agent.mode === "live" ? (liveUnavailable ? "Live AI unavailable" : `Live AI, ${ws.agent.model}`) : "Rule-based replay, no live model"}
          </span>
          <button className="link-btn" onClick={switchMode}>Switch to {ws.agent.mode === "live" ? "replay" : "live AI"}</button>
        </div>
        <div className="user">
          <span>{ws.user.display_name}, <strong>{ws.user.role}</strong></span>
          <button className="link-btn" onClick={logout}>Sign out</button>
        </div>
      </header>
      <div className="frame">
        <nav className="tabs" aria-label="Workflow">
          {ROUTES.map(([k, label], i) => (
            <a key={k} href={`#/${k}`} className={[route === k ? "active" : "", done.has(k) ? "done" : ""].join(" ").trim() || undefined}
               aria-current={route === k ? "page" : undefined}>
              <span className="step-n">{i + 1}</span> <span>{label}</span>
              {done.has(k) && <span className="sr-only">(done)</span>}
            </a>
          ))}
        </nav>
        <main>
          {error && <div className="banner bad" role="alert"><span>{error}</span><button className="link-btn" onClick={() => setError(null)}>Dismiss</button></div>}
          {note && <div className="banner ok" role="status"><span>{note}</span><button className="link-btn" onClick={() => setNote(null)}>Dismiss</button></div>}
          {liveUnavailable && <div className="banner warn">Live AI is selected but no model API key is configured on the server. Financial tools still work; switch to Rule-based replay explicitly to run the agent workflow.</div>}
          {route === "overview" && <Overview />}
          {route === "evidence" && <Evidence />}
          {route === "decision" && <Decision />}
          {route === "compare" && <Compare />}
          {route === "action" && <ActionScreen />}
          {route === "receipt" && <Receipt />}
        </main>
      </div>
      <ul className="foot" aria-label="Demo limits">
        <li>Synthetic data</li>
        <li>Sandbox simulation only</li>
        <li>No real payments, credit or FX</li>
        <li>Amounts are end-of-day</li>
        <li>Owner buffer {cny(ws.business.buffer_minor)}</li>
        <li>Policy {ws.policy.policy_version}</li>
      </ul>
    </AppCtx.Provider>
  );
}

function Login({ onDone }: { onDone: () => void }) {
  const [username, setU] = useState("owner@demo-gba");
  const [password, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const r = await api.post<{ csrf_token: string }>("/api/auth/login", { username, password });
      setCsrf(r.csrf_token);
      onDone();
    } catch (x) { setErr(errText(x)); }
  };
  return (
    <div className="login">
      <div className="login-pitch">
        <div className="brand"><BrandMark />OrderBridge</div>
        <div>
          <h1>Can I accept this order without breaching my cash buffer?</h1>
          <p>OrderBridge projects your daily cash with and without a new order, shows the days you would fall short, and compares the terms or funding that close the gap.</p>
        </div>
        <svg className="login-gap" viewBox="0 0 440 120" aria-hidden="true">
          <defs>
            <pattern id="login-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="6" stroke="currentColor" strokeWidth="1.5" />
            </pattern>
          </defs>
          <path d="M60 60H128V100H300V60" fill="url(#login-hatch)" opacity="0.7" />
          <line x1="0" y1="60" x2="440" y2="60" stroke="currentColor" strokeWidth="1" opacity="0.6" />
          <path d="M0 30H60V60M60 60V100H128V100H300V60M300 60V18H440" fill="none" stroke="currentColor" strokeWidth="2.5" />
          <path d="M60 60Q180 -10 300 60" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 4" />
        </svg>
      </div>
      <div className="login-form-wrap">
        <form onSubmit={submit}>
          <h2>Sign in</h2>
          <p className="muted small">Synthetic local demo. Not a WeBank product. No real money moves.</p>
          <label>Username<input value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" /></label>
          <label>Password<input type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></label>
          {err && <div className="banner bad" role="alert">{err}</div>}
          <button className="primary" type="submit">Sign in</button>
          <p className="muted small">Demo accounts: owner@demo-gba, viewer@demo-gba and owner@demo-other. The password is set by ORDERBRIDGE_DEMO_PASSWORD (see README).</p>
        </form>
      </div>
    </div>
  );
}
