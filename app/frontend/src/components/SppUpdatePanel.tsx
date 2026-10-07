import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Circle, Clock, Loader2, RefreshCw, RotateCw, ShieldCheck } from "lucide-react";
import { BlockerGuidance } from "./BlockerGuidance";
import { lockReadOnly } from "./storageInstall";
import { sppUpdateApi, GuardedUnavailableError, type SppUpdatePlan, type SppUpdateStatus } from "../api";

/*
 * Whole-SPP update for one server: Review update -> Yes/No -> Approve and install ->
 * progress -> verified result. The backend owns inventory, dependency order, authentication and
 * write scope; the approval is bound to the exact reviewed plan (can_apply + its credentials).
 * The attempt is saved before the request leaves. It is cleared only by a reply or recorded
 * status for this exact profile, device and idempotency key. Nothing is resent automatically.
 * Contract: backend services/spp_update_contract.py.
 */

type Attempt = { idempotencyKey: string; reviewToken: string; sentAt: string; confirmationPhrase?: string; error?: string };
const attemptKey = (profileId: string, deviceId: string) => `lab-builder-spp-attempt:${profileId}:${deviceId}`;
const memory = new Map<string, Attempt>();
function readAttempt(key: string): Attempt | null {
  try { const raw = window.localStorage.getItem(key); if (raw) return JSON.parse(raw) as Attempt; } catch { /* memory copy */ }
  return memory.get(key) ?? null;
}
function writeAttempt(key: string, attempt: Attempt | null) {
  if (attempt) memory.set(key, attempt); else memory.delete(key);
  try { if (attempt) window.localStorage.setItem(key, JSON.stringify(attempt)); else window.localStorage.removeItem(key); } catch { /* memory copy kept */ }
}
const RUNNING = new Set(["running", "waiting_restart", "verifying"]);
/** Locked: the backend says active, or the vocabulary says in progress, or the outcome is unknown. */
const isLocked = (status: SppUpdateStatus) => status.active || RUNNING.has(status.status) || status.status === "uncertain";
/** A reply settles an attempt only if it is for this exact target and carries the sent key. */
const settles = (reply: SppUpdateStatus, profileId: string, deviceId: string, attempt: Attempt) =>
  reply.profile_id === profileId && reply.device_id === deviceId && !!reply.idempotency_key && reply.idempotency_key === attempt.idempotencyKey;
const minutes = (value?: number | null) => value ? `about ${value} min` : "";
const restartsText = (count: number | null, what: string) => count === null ? `${what} may restart` : count === 0 ? "" : `${what} restarts ${count === 1 ? "once" : count === 2 ? "twice" : `${count} times`}`;

export function useSppAvailability(profileId: string, deviceId: string) {
  const [state, setState] = useState<"loading" | "available" | "unavailable">("loading");
  const [status, setStatus] = useState<SppUpdateStatus | null>(null);
  useEffect(() => {
    let active = true;
    setState("loading");
    sppUpdateApi.status(profileId, deviceId)
      .then(value => { if (active) { setStatus(value); setState("available"); } })
      .catch(err => { if (active) setState(err instanceof GuardedUnavailableError ? "unavailable" : "available"); });
    return () => { active = false; };
  }, [profileId, deviceId]);
  const pending = !!readAttempt(attemptKey(profileId, deviceId));
  return { state, inProgress: pending || (!!status && isLocked(status)) };
}

function StepIcon({ state }: { state: string }) {
  if (state === "done") return <CheckCircle2 size={17} className="spp-i-done" aria-hidden="true" />;
  if (state === "failed" || state === "uncertain") return <AlertTriangle size={17} className="spp-i-bad" aria-hidden="true" />;
  if (state === "installing" || state === "verifying") return <Loader2 size={17} className="spp-i-run" aria-hidden="true" />;
  if (state === "restarting") return <RotateCw size={17} className="spp-i-run" aria-hidden="true" />;
  if (state === "waiting") return <Clock size={17} aria-hidden="true" />;
  return <Circle size={17} aria-hidden="true" />;
}
const stateWord: Record<string, string> = { waiting: "Waiting", installing: "Installing", restarting: "Restarting", verifying: "Verifying", done: "Done", failed: "Failed", not_started: "Not started", uncertain: "Unknown" };

// Another installer (RAID, ESXi) may have left its own write scope on. Firmware work starts from
// read-only, so the panel returns there by itself (the safe direction) and asks once more. The
// backend still refuses that change while another job is running.
async function fromReadOnly<T>(call: () => Promise<T>): Promise<T> {
  try { return await call(); }
  catch (err) {
    if (!(err instanceof Error && /return to read-only/i.test(err.message))) throw err;
    await lockReadOnly();
    return await call();
  }
}

export function SppUpdatePanel({ profileId, deviceId, onActivity, onChanged, onClose }: {
  profileId: string; deviceId: string; onActivity?: (active: boolean) => void; onChanged?: () => void; onClose?: () => void;
}) {
  const key = attemptKey(profileId, deviceId);
  const [status, setStatus] = useState<SppUpdateStatus | null>(null);
  const [attempt, setAttempt] = useState<Attempt | null>(() => readAttempt(key));
  const [plan, setPlan] = useState<SppUpdatePlan | null>(null);
  const [busy, setBusy] = useState<"" | "plan" | "apply" | "status">("");
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [now, setNow] = useState(Date.now());
  const live = useRef(true);
  // Set on every setup: React StrictMode runs setup, cleanup, setup.
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);

  async function readStatus(reconcilePending = false) {
    setBusy("status"); setError("");
    try {
      const pending = readAttempt(key);
      const next = pending && reconcilePending
        ? await sppUpdateApi.reconcile(profileId, deviceId, {
          review_token: pending.reviewToken,
          confirmation_phrase: pending.confirmationPhrase ?? "RECONCILE ONLY",
          idempotency_key: pending.idempotencyKey,
        })
        : reconcilePending && status?.execution_mode === "offline" && status.operation_id && status.active
          ? await sppUpdateApi.verify(profileId, deviceId, status.operation_id)
          : await fromReadOnly(() => sppUpdateApi.status(profileId, deviceId, pending?.idempotencyKey));
      if (!live.current) return;
      if (next.profile_id !== profileId || next.device_id !== deviceId) throw new Error("The recorded status is for a different server. Nothing was changed.");
      setStatus(next);
      // A missing or different key is not proof that nothing was sent; the attempt stays locked.
      if (pending && settles(next, profileId, deviceId, pending)) { writeAttempt(key, null); setAttempt(null); setPlan(null); setConfirming(false); }
    } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(""); }
  }
  useEffect(() => { void readStatus(); }, [profileId, deviceId]);
  const locked = !!status && isLocked(status);
  // Only a running run polls; an active failed or uncertain run waits for an explicit Check status.
  const polling = !!status && RUNNING.has(status.status);
  // Recorded status is stored workflow state; re-reading it does not contact the server.
  useEffect(() => { if (!polling) return; const timer = setInterval(() => void readStatus(), 10000); return () => clearInterval(timer); }, [polling]);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(timer); }, []);
  useEffect(() => { onActivity?.(!!attempt || locked); }, [attempt, locked]);

  async function review() {
    setBusy("plan"); setError(""); setPlan(null); setConfirming(false);
    try {
      let next = await fromReadOnly(() => sppUpdateApi.plan(profileId, deviceId));
      if (next.blockers?.some(item => /return to read-only/i.test(item))) { await lockReadOnly(); next = await sppUpdateApi.plan(profileId, deviceId); }
      if (!live.current) return;
      if (next.profile_id !== profileId || next.device_id !== deviceId) throw new Error("The review came back for a different server. Nothing can be approved from it.");
      setPlan(next);
    }
    catch (err) { if (live.current) setError(err instanceof GuardedUnavailableError ? "The app can't plan a full update on this server yet." : err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(""); }
  }
  async function approve() {
    if (!plan || !confirming || readAttempt(key) || !canApprove || !plan.review_token || !plan.confirmation_phrase) return;
    // A review about to expire would only be refused: fetch a fresh one instead of sending.
    if (Date.parse(plan.expires_at) - Date.now() < 30000) { await review(); return; }
    const next: Attempt = { idempotencyKey: crypto.randomUUID(), reviewToken: plan.review_token, confirmationPhrase: plan.confirmation_phrase, sentAt: new Date().toISOString() };
    writeAttempt(key, next); setAttempt(next); setBusy("apply"); setError("");
    try {
      const result = await sppUpdateApi.apply(profileId, deviceId, { review_token: plan.review_token, confirmation_phrase: plan.confirmation_phrase, idempotency_key: next.idempotencyKey });
      if (settles(result, profileId, deviceId, next)) {
        writeAttempt(key, null);
        if (live.current) { setAttempt(null); setPlan(null); setConfirming(false); setStatus(result); }
      } else {
        const unmatched = { ...next, error: "The server's reply did not name this exact request." };
        writeAttempt(key, unmatched); if (live.current) setAttempt(unmatched);
      }
    } catch (err) {
      const failed = { ...next, error: err instanceof Error ? err.message : String(err) };
      writeAttempt(key, failed); if (live.current) setAttempt(failed);
    } finally { if (live.current) setBusy(""); }
  }

  const expired = !!plan && Date.parse(plan.expires_at) <= now;
  const executable = !!plan && plan.can_apply && !!plan.review_token && !!plan.confirmation_phrase && !plan.blockers.length && plan.updates.length > 0;
  const canApprove = executable && !expired && !attempt && !locked && !busy;
  const checkStatus = <button type="button" className="secondary-action" disabled={!!busy} onClick={() => void readStatus(true)}><RefreshCw size={15} />{busy === "status" ? "Checking…" : "Check status"}</button>;

  // 1. An attempt whose outcome is unknown: nothing else is offered until a matching record settles it.
  if (attempt) return <div className="spp" aria-label="Update status">
    <div className="fw-stop" role="alert"><strong>{busy === "apply" ? "Sending the approval once…" : "We don't know yet whether the update started."}</strong>
      {busy !== "apply" && <p>Sent {new Date(attempt.sentAt).toLocaleString()}. {attempt.error ?? ""} Nothing will be sent again. Check the recorded status to see what the server did.</p>}</div>
    {busy !== "apply" && checkStatus}
    {error && <p className="fw-stop" role="alert">{error}</p>}
    {status && status.status !== "not_started" && <Progress status={status} />}
  </div>;

  // 2. An update is running, locked, or its last outcome needs attention.
  if (status && (locked || (status.status === "failed" && !plan) || (status.status === "verified" && !plan))) return <div className="spp" aria-label="Update status">
    {status.status === "verified" && !locked && <p className="fw-ok"><CheckCircle2 size={17} />{status.execution_mode === "offline" ? "Listed firmware versions verified. Update media disconnected." : "Update finished and verified. The server is back to read-only."}</p>}
    {status.status === "failed" && <div className="fw-stop" role="alert"><strong>The update stopped.</strong><p>{status.message} Updates marked done are installed and verified; the rest were not started. Nothing is retried automatically.</p></div>}
    {status.status === "uncertain" && <div className="fw-stop" role="alert"><strong>The outcome is unknown.</strong><p>{status.message} Nothing is retried automatically.</p></div>}
    {error && <p className="fw-stop" role="alert">{error}</p>}
    {status.execution_mode === "offline" && polling && <p role="status">{status.message}</p>}
    <Progress status={status} />
    {status.next_action && <p className="sd-fine">{status.next_action}</p>}
    {polling ? <p className="sd-fine">Keep the server's power connected. This page updates by itself; you can close it.</p>
      : locked ? <div className="spp-act">{checkStatus}<p className="sd-fine">This server stays locked until the recorded status settles. No new review is offered.</p></div>
      : <div className="spp-act">
        <button type="button" className="secondary-action" onClick={() => void review()} disabled={!!busy}><ShieldCheck size={15} />Review another update</button>
        {status.status === "verified" && onClose && <button type="button" className="primary-action fw-go" onClick={() => { onClose(); onChanged?.(); }}>Done</button>}
      </div>}
  </div>;

  // 3. Review, then one approval.
  return <div className="spp" aria-label="Review update">
    {!plan && <section className="fw-stage">
      <p>Reads this server and your firmware package, then shows exactly what would change. Nothing is installed.</p>
      <button type="button" className="primary-action fw-go" disabled={!!busy} onClick={() => void review()}><ShieldCheck size={17} />{busy === "plan" ? "Reading the server…" : "Review update"}</button>
    </section>}
    {error && <p className="fw-stop" role="alert">{error}</p>}
    {plan && <section className="spp-review" aria-label="Update plan">
      {plan.updates.length ? <>
        <h3>{plan.execution_mode === "offline" ? `Automatic SPP ${plan.package.release}` : `${plan.updates.length} update${plan.updates.length === 1 ? "" : "s"} from SPP ${plan.package.release}`}</h3>
        {plan.execution_mode === "offline" && <p>HPE selects and installs applicable firmware. These versions will be checked afterwards.</p>}
        <ol className="spp-list">{[...plan.updates].sort((a, b) => a.order - b.order).map(item => <li key={item.step_id}>
          <strong>{item.component}</strong>
          <span className="fw-path"><b>{item.from}</b><i aria-hidden="true">→</i><b className="next">{item.to}</b></span>
          {item.restarts !== "none" && <small>{item.restarts === "host" ? "server restarts" : "iLO restarts"}</small>}
        </li>)}</ol>
        <p className="spp-effects"><RotateCw size={15} aria-hidden="true" />{[restartsText(plan.effects.host_restarts, "Server"), restartsText(plan.effects.ilo_restarts, "iLO")].filter(Boolean).join(". ") || "No restarts"}
          {plan.effects.est_total_minutes ? ` · ${minutes(plan.effects.est_total_minutes)} in total` : ""}. Keep power connected.</p>
        {plan.effects.power_on_required && <p className="sd-fine">The server will be powered on for the update.</p>}
      </> : <p className="spp-none">No update can be offered from this review.{plan.not_included.length ? " See what was left out and why below." : ""}</p>}
      {!!plan.not_included.length && <details className="fw-details" open={!plan.updates.length}><summary>Not included ({plan.not_included.length})</summary>
        <ul className="sd-fine">{plan.not_included.map(item => <li key={item.component}><b>{item.component}</b>: {item.reason}</li>)}</ul></details>}
      <BlockerGuidance title="Fix this first" blockers={plan.blockers} details={plan.blocker_details} deviceId={deviceId}
        handlers={{ read_again: () => void review(), prepare_again: () => void review(), check_status: () => void readStatus() }} />
      {!plan.blockers.length && plan.updates.length > 0 && !executable && <p className="fw-stop" role="alert">This review can't be approved. Review again for a fresh plan.</p>}
      {!!plan.warnings.length && <ul className="sd-fine spp-warn">{plan.warnings.map(item => <li key={item}>{item}</li>)}</ul>}
      {plan.details !== undefined && <details className="fw-details"><summary>Technical details</summary><pre className="spp-pre">{JSON.stringify(plan.details, null, 2)}</pre></details>}
      {executable && <div className="spp-approve">
        {expired ? <p className="fw-stop" role="alert">This review has expired. Review again to get a fresh plan.</p> : <>
          {confirming ? <div role="group" aria-label="Confirm firmware update">
            <p>{plan.execution_mode === "offline" ? `Install all applicable firmware from SPP ${plan.package.release} on ${plan.server.name}?` : `Install these ${plan.updates.length} updates on ${plan.server.name}?`}</p>
            <div className="spp-act">
              <button type="button" className="secondary-action" onClick={() => setConfirming(false)}>No</button>
              <button type="button" className="primary-action fw-go" disabled={!canApprove} onClick={() => void approve()}>Yes</button>
            </div>
          </div> : <button type="button" className="primary-action fw-go" disabled={!canApprove} onClick={() => setConfirming(true)}><ShieldCheck size={17} />Approve and install</button>}
        </>}
      </div>}
      <button type="button" className="fw-link" disabled={!!busy} onClick={() => void review()}>{expired ? "Review again" : "Refresh this review"}</button>
    </section>}
  </div>;
}

// What the server shows right now for one part, while the run is still open. Not a verification.
function nowWord(part: NonNullable<SppUpdateStatus["observed"]>["parts"][number] | undefined, restarted: boolean) {
  if (!part) return null;
  if (part.at_target) return restarted ? `Now ${part.installed} · confirming` : `Now ${part.installed} · checked again after the restart`;
  return `Still ${part.installed ?? "unknown"} · ${restarted ? "not at its version yet" : "installs during the restart"}`;
}

function Progress({ status }: { status: SppUpdateStatus }) {
  if (!status.steps.length) return status.message ? <p className="sd-fine">{status.message}</p> : null;
  const observed = status.active && status.execution_mode === "offline" ? status.observed ?? null : null;
  const parts = new Map((observed?.parts ?? []).map(part => [part.component, part]));
  return <>
    {observed && <div className={observed.waiting_for_reboot ? "fw-stop spp-observed" : "spp-observed"} role="status" aria-label="What the server shows now">
      <p>{observed.summary}</p>
      {!!observed.queued.length && <p className="sd-fine">Queued in the iLO for the restart: {observed.queued.join("; ")}.</p>}
      <p className="sd-fine">Read from the server at {new Date(observed.checked_at).toLocaleTimeString()}.</p>
    </div>}
    <ol className="spp-list spp-progress" aria-label="Update progress">{status.steps.map(step => {
      const now = step.state === "done" ? null : nowWord(parts.get(step.component), !!observed?.restarted_after_updater);
      return <li key={step.step_id} data-state={step.state} data-now={now ? (parts.get(step.component)?.at_target ? "at-target" : "pending") : undefined} aria-current={status.current_step === step.step_id ? "step" : undefined}>
        <StepIcon state={step.state} />
        <strong>{step.component}</strong>
        <span className="fw-path"><b>{step.from}</b><i aria-hidden="true">→</i><b className={step.state === "done" ? "" : "next"}>{step.verified_version ?? step.to}</b></span>
        <small>{now ?? (status.execution_mode === "offline" && step.state === "waiting" ? "Awaiting readback" : stateWord[step.state] ?? step.state)}{step.state === "done" && step.verified_version ? " · verified" : ""}</small>
      </li>;
    })}</ol>
  </>;
}
