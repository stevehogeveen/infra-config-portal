import { FIRMWARE_SCOPE_BLOCKER } from "./studio/WriteScope";
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CircleCheck, Clock, ShieldCheck, X, RefreshCw } from "lucide-react";
import { guardedApi, GuardedUnavailableError, type GuardedReconcile, type DriveReturnOperation, type FirmwareExecutionOperation, type GuardedOperationStatus, type GuardedPreview, type GuardedResource } from "../api";
import { GuidePrimary } from "./studio/Guide";
import { BlockerGuidance, type GuidanceHandlers } from "./BlockerGuidance";
import { FirmwareRecovery } from "./FirmwareRecovery";
import { ProvenanceChip, shortTime } from "./studio/ProvenanceChip";

/*
 * Guarded write flows for the 2026-09-28 contract: recorded status, then a fresh preview, then a
 * typed confirmation and one apply with an idempotency key. The app never retries on its own:
 * uncertain and failed outcomes offer reading the recorded status, not another submission.
 */

type Kind = "firmware" | "drives";
const copy: Record<Kind, { resource: GuardedResource; open: string; title: string; unavailable: string; apply: string; section: string }> = {
  firmware: { resource: "firmware-execution", open: "Review firmware install", title: "Install firmware", section: "Firmware install",
    unavailable: "Not available yet: the app cannot install firmware on this server yet.", apply: "Install" },
  drives: { resource: "drive-return-to-service", open: "Return erased disks to service", title: "Return erased disks to service", section: "Erased disks",
    unavailable: "Not available yet: the app cannot re-enable erased disks on this server yet.", apply: "Confirm and re-enable disks" },
};

const statusText: Record<GuardedOperationStatus["status"], { label: string; detail: string }> = {
  not_started: { label: "No operation recorded", detail: "Nothing has been submitted for this server." },
  blocked: { label: "Blocked", detail: "The last review found blockers. Nothing was sent." },
  submitting: { label: "Submitting", detail: "The request is being sent. Do not close the server's power." },
  accepted: { label: "Accepted, not verified", detail: "The server accepted the request. Accepted is not done; it is verified only by a later read." },
  running: { label: "Running", detail: "The server reports the operation in progress. No time estimate is given." },
  uncertain: { label: "Outcome unknown", detail: "The app cannot tell whether the request took effect. It will not retry. Read the recorded status before deciding anything." },
  failed: { label: "Failed", detail: "The operation did not complete. Nothing is counted as done. Read the recorded status and its details before any new review." },
  verified: { label: "Verified", detail: "A read after the operation confirmed the result." },
};
const activeStates = new Set(["submitting", "accepted", "running"]);

type Availability = "loading" | "available" | "unavailable";

/*
 * An apply whose outcome the browser does not know. Written before the request leaves, bound to
 * profile + resource + device, kept in memory and localStorage so it survives closing the dialog,
 * remounting and reloading. While it exists no new review or apply is offered. It is cleared only
 * when a successful apply response arrives, or GET reconcile returns a recorded operation whose
 * recorded idempotency_key equals the stored key for the same kit, device and resource.
 * requested_idempotency_key is a lookup echo and never unlocks. A missing row, null or different
 * key, or any historical operation (even verified/failed) keeps the attempt uncertain.
 */
export type PendingAttempt = {
  idempotencyKey: string; reviewToken: string; sentAt: string; state: "sending" | "uncertain" | "accepted"; error?: string;
  profileId?: string; deviceId?: string; resource?: GuardedResource;
};
/**
 * What a recorded result means for a pending browser attempt (exact key and scope already matched):
 * accepted keeps the attempt (its review token is needed to fence it); running/uncertain/verified
 * hand the lock to the recorded operation; failed clears only with dispatch_prevented.
 */
function settle(result: GuardedOperationStatus): "clear" | "accepted" | "keep" {
  if (result.status === "accepted") return "accepted";
  if (["running", "uncertain", "verified", "submitting"].includes(result.status)) return "clear";
  if (result.status === "failed" && (result.dispatch_prevented === true || result.resolution === "operator_closed_unverified")) return "clear";
  return "keep";
}
const memoryAttempts = new Map<string, PendingAttempt>();
export const attemptKey = (profileId: string, resource: GuardedResource, deviceId: string) => `lab-builder-guarded-attempt:${profileId}:${resource}:${deviceId}`;
export function readAttempt(key: string): PendingAttempt | null {
  try { const raw = window.localStorage.getItem(key); if (raw) return JSON.parse(raw) as PendingAttempt; } catch { /* memory copy below */ }
  return memoryAttempts.get(key) ?? null;
}
export function writeAttempt(key: string, attempt: PendingAttempt | null) {
  if (attempt) memoryAttempts.set(key, attempt); else memoryAttempts.delete(key);
  try { if (attempt) window.localStorage.setItem(key, JSON.stringify(attempt)); else window.localStorage.removeItem(key); } catch { /* memory copy kept */ }
}
export function reconcilesAttempt(result: GuardedReconcile, attempt: PendingAttempt, scope: { profileId: string; deviceId: string; resource: GuardedResource }) {
  return result.record_found === true && !!result.operation_id
    && typeof result.idempotency_key === "string" && result.idempotency_key === attempt.idempotencyKey
    && result.profile_id === scope.profileId && result.device_id === scope.deviceId && result.resource === scope.resource;
}

export function GuardedExecution({ kind, profileId, deviceId, deviceName, hoist = false, onChanged, onActivity, compact = false, openLabel, showReview = true, onRequestOpen, onStatus, guidance }: {
  kind: Kind; profileId: string; deviceId: string; deviceName: string; hoist?: boolean; onChanged?: () => void;
  /** Compact: no header or recorded-blocker list; the review itself states any real blocker. */
  compact?: boolean; openLabel?: string; showReview?: boolean;
  /** Lets the page run a prerequisite (such as narrowing write scope) before the review opens. */
  onRequestOpen?: (open: () => void) => void;
  onStatus?: (status: GuardedOperationStatus | null) => void;
  /** "How to fix" buttons in the review; each closes the review first. */
  guidance?: GuidanceHandlers;
  /** Reports whether an attempt or recorded operation still needs attention (for a summary elsewhere). */
  onActivity?: (active: boolean) => void;
}) {
  const text = copy[kind];
  const [availability, setAvailability] = useState<Availability>("loading");
  const [status, setStatus] = useState<GuardedOperationStatus | null>(null);
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const [open, setOpen] = useState(false);
  const [recoveryOpen, setRecoveryOpen] = useState(false);
  const targetKey = attemptKey(profileId, text.resource, deviceId);
  const [attempt, setAttempt] = useState<PendingAttempt | null>(() => readAttempt(targetKey));
  // Every read belongs to one target; a late answer for another target is discarded.
  const generation = useRef(0);
  const liveTarget = useRef(targetKey);
  liveTarget.current = targetKey;

  async function read() {
    const id = ++generation.current;
    const key = targetKey;
    const fresh = () => id === generation.current && liveTarget.current === key;
    setReading(true); setError("");
    try {
      const next = await guardedApi.status(profileId, text.resource, deviceId);
      if (!fresh()) return;
      setStatus(next); setAvailability("available");
      const pending = readAttempt(key);
      if (pending) {
        let outcome: "clear" | "accepted" | "keep" = "keep";
        try {
          const result = await guardedApi.reconcile(profileId, text.resource, deviceId, pending.idempotencyKey);
          if (reconcilesAttempt(result, pending, { profileId, deviceId, resource: text.resource })) outcome = settle(result);
        } catch { outcome = "keep"; /* unreachable or missing reconcile keeps the lock */ }
        if (!fresh()) return;
        if (outcome === "clear") { writeAttempt(key, null); setAttempt(null); }
        else if (outcome === "accepted" && pending.state !== "accepted") { const next = { ...pending, state: "accepted" as const }; writeAttempt(key, next); setAttempt(next); }
      }
    } catch (err) {
      if (!fresh()) return;
      if (err instanceof GuardedUnavailableError) setAvailability("unavailable");
      else { setAvailability("available"); setError(`Recorded status could not be read: ${err instanceof Error ? err.message : String(err)}`); }
    } finally { if (fresh()) setReading(false); }
  }
  // A new target closes and resets any open review and drops the old target's state.
  useEffect(() => { setOpen(false); setRecoveryOpen(false); setStatus(null); setError(""); setAttempt(readAttempt(targetKey)); setAvailability("loading"); void read(); }, [targetKey]);

  const [closing, setClosing] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [note, setNote] = useState("");
  async function closeSafely() {
    const pending = readAttempt(targetKey);
    if (!pending?.reviewToken || kind !== "firmware") return;
    const key = targetKey;
    setClosing(true); setError(""); setNote("");
    try {
      const result = await guardedApi.reconcileUnsent(profileId, deviceId, { review_token: pending.reviewToken, idempotency_key: pending.idempotencyKey });
      if (liveTarget.current !== key) return;
      const matches = reconcilesAttempt({ ...result, record_found: result.record_found ?? true }, pending, { profileId, deviceId, resource: text.resource });
      setStatus(result);
      if (matches && result.dispatch_prevented === true) {
        writeAttempt(key, null); setAttempt(null);
        setNote("Closed safely: this attempt was stopped before it could be sent and can never be sent later. Start a new review for another attempt.");
      } else if (matches && settle(result) === "clear") {
        writeAttempt(key, null); setAttempt(null);
        setNote("The server had already taken this attempt, so it could not be closed. It stays locked until its result is verified.");
      } else setNote("The attempt could not be proven closed. It stays locked.");
    } catch (err) {
      if (liveTarget.current === key) setError(`The attempt could not be closed: ${err instanceof Error ? err.message : String(err)} It stays locked.`);
    } finally { if (liveTarget.current === key) setClosing(false); }
  }
  async function verify() {
    if (!status?.operation_id || kind !== "firmware") return;
    const key = targetKey;
    setVerifying(true); setError(""); setNote("");
    try { const result = await guardedApi.verify(profileId, deviceId, status.operation_id); if (liveTarget.current === key) { setStatus(result); onChanged?.(); } }
    catch (err) { if (liveTarget.current === key) setError(`${err instanceof Error ? err.message : String(err)}`); }
    finally { if (liveTarget.current === key) setVerifying(false); }
  }
  const state = status?.status ?? "not_started";
  const busy = activeStates.has(state);
  const reason = availability === "unavailable" ? text.unavailable
    : availability === "loading" ? "Reading the recorded status..."
    : attempt?.state === "accepted" ? "The server accepted this attempt but has not sent it. No new review is offered until it is verified or closed safely."
    : attempt ? "A request was sent and its outcome is unknown. No new review or apply is offered until a status read shows what the server recorded."
    : error ? "The recorded status is unknown, so a new review is not offered until it can be read."
    : state === "uncertain" ? "The last outcome is unknown. A new review is not offered until a read confirms what happened."
    : busy ? "An operation is in progress. Wait for its verified result."
    : "";
  const canReview = !reason;
  const needsAttention = !!attempt || busy || state === "uncertain";
  useEffect(() => { onActivity?.(needsAttention); }, [needsAttention]);
  useEffect(() => { onStatus?.(status); }, [status]);
  const reviewButton = <button type="button" className="primary-action sd-guarded-open" disabled={!canReview || reading} onClick={() => { void read(); if (onRequestOpen) onRequestOpen(() => setOpen(true)); else setOpen(true); }}><ShieldCheck size={17} />{openLabel ?? text.open}</button>;

  return <section className="sd-guarded" aria-label={text.section}>
    {!compact && <header className="sd-guarded-h"><div><p className="eyebrow">{text.section} · {deviceName}</p><h3>{text.title}</h3></div>
      {availability !== "unavailable" && <button type="button" className="secondary-action" disabled={reading || availability === "loading"} onClick={() => void read()}><RefreshCw size={15} />{reading ? "Reading..." : "Read recorded status"}</button>}
    </header>}
    {(showReview || !!attempt || busy) && <div className="sd-guarded-act">
      {!showReview ? null : canReview && hoist ? <GuidePrimary>{reviewButton}</GuidePrimary> : reviewButton}
      {reason && (!compact || availability !== "loading") && <p className="sd-guarded-why" role="note">{reason}</p>}
    </div>}
    {error && <p role="alert" className="workflow-alert">{error}</p>}
    {note && <p role="status" className="sd-guarded-note">{note}</p>}
    {!compact && availability === "available" && !attempt && !!status?.blockers?.length && (state === "not_started" || state === "blocked") && <div className="sd-guarded-gates" role="note">
      <strong>What the server says blocks this</strong><ul>{status.blockers.map(item => <li key={item}>{item}{FIRMWARE_SCOPE_BLOCKER.test(item) && <> <a href="#write-scope">Limit to firmware only</a></>}</li>)}</ul>
      <small>These are the server's own reasons. The app offers no way around them.</small></div>}
    {kind === "firmware" && attempt && <div className="sd-guarded-act">
      <button type="button" className="secondary-action" disabled={closing || !attempt.reviewToken} onClick={() => void closeSafely()}>{closing ? "Closing..." : "Close this attempt safely"}</button>
      <p className="sd-guarded-why" role="note">{attempt.reviewToken
        ? "Asks the server to prevent this exact attempt from ever being sent. It unlocks only if the server confirms nothing was dispatched; a new review is then needed."
        : "This attempt has no server-issued review, so it cannot be closed from here. It stays blocked."}</p>
    </div>}
    {attempt?.state === "accepted" && <GuardedProgress status={{ status: "accepted", evidence_at: null,
      message: `Accepted by the server for this browser attempt (idempotency key ${attempt.idempotencyKey}); not yet sent to the iLO.`,
      next_action: "Wait for the server to send it and then verify, or close this attempt safely." }} />}
    {attempt && attempt.state !== "accepted" && <GuardedProgress status={{ status: "uncertain", evidence_at: null,
      message: `Sent from this browser at ${new Date(attempt.sentAt).toLocaleString()} (idempotency key ${attempt.idempotencyKey}). ${attempt.error ?? "No response was received."}`,
      next_action: "Read the recorded status. The same request is never sent again automatically." }} />}
    {/* "blocked" only describes an earlier review that sent nothing; compact flows re-review instead of showing it. */}
    {status && status.status !== "not_started" && !(compact && status.status === "blocked") && !attempt && <GuardedProgress status={status} />}
    {kind === "firmware" && !attempt && status?.operation_id && (state === "running" || state === "uncertain") && <div className="sd-guarded-act">
      <button type="button" className="secondary-action" disabled={verifying} onClick={() => void verify()}><RefreshCw size={15} />{verifying ? "Reading iLO..." : "Verify iLO version (read-only)"}</button>
      <p className="sd-guarded-why" role="note">Reads the iLO version once to confirm the result. Nothing is sent to install, and nothing is checked automatically.</p>
    </div>}
    {open && !attempt && <GuardedReview key={targetKey} kind={kind} profileId={profileId} deviceId={deviceId} deviceName={deviceName}
      guidance={guidance && Object.fromEntries(Object.entries(guidance).map(([name, run]) => [name, () => { setOpen(false); run?.(); }]))}
      onUnavailable={() => { setOpen(false); setAvailability("unavailable"); }}
      onSending={next => { writeAttempt(targetKey, next); }}
      onUncertain={next => { writeAttempt(targetKey, next); }}
      onClose={result => {
        setOpen(false);
        if (result) {
          const pending = readAttempt(targetKey);
          // Accepted is not sent: keep the attempt (and its review token) so it can be closed safely.
          if (result.status === "accepted" && pending) { const next = { ...pending, state: "accepted" as const }; writeAttempt(targetKey, next); setAttempt(next); }
          else { writeAttempt(targetKey, null); setAttempt(null); }
          setStatus(result); onChanged?.(); void read();
        } else setAttempt(readAttempt(targetKey));
      }} />}
    {kind === "firmware" && !attempt && state === "uncertain" && status?.operation_id && <>
      <button type="button" className="secondary-action" disabled={verifying || reading} onClick={() => setRecoveryOpen(true)}>Cancel upgrade</button>
      {recoveryOpen && <FirmwareRecovery key={targetKey + status.operation_id} profileId={profileId} deviceId={deviceId}
        deviceName={deviceName} operationId={status.operation_id} onClose={result => {
          setRecoveryOpen(false);
          if (result && result.device_id === deviceId && result.profile_id === profileId) { setStatus(result); onChanged?.(); }
        }} />}
    </>}
  </section>;
}

export function GuardedProgress({ status }: { status: GuardedOperationStatus }) {
  const info = status.resolution === "operator_closed_unverified" ? { label: "Closed, outcome unverified", detail: "You closed this unsuccessful attempt. Its previous outcome remains unverified; another installation needs a fresh review." }
    : status.dispatch_prevented ? { label: "Closed before sending", detail: "This attempt was stopped before dispatch and can never be sent. Another attempt needs a new review." } : statusText[status.status];
  const tone = status.status === "verified" ? "complete" : ["failed", "uncertain", "blocked"].includes(status.status) ? "attention" : "running";
  const Icon = tone === "complete" ? CircleCheck : tone === "attention" ? AlertTriangle : Clock;
  return <article className={`sd-guarded-card is-${tone}`} aria-label="Operation status" data-status={status.status}>
    <div className="sd-guarded-card-h"><Icon size={24} /><div><strong>{info.label}</strong><p>{info.detail}</p></div>
      {status.evidence_at && <ProvenanceChip kind="recorded" time={status.evidence_at}>recorded</ProvenanceChip>}</div>
    {status.status === "uncertain" && <p className="sd-guarded-stop"><AlertTriangle size={15} />Do not retry automatically. No retry is offered here.</p>}
    {!!status.blockers?.length && <ul className="sd-guarded-blockers">{status.blockers.map(item => <li key={item}>{item}</li>)}</ul>}
    {!!status.stages?.length && <ol className="sd-guarded-stages">{status.stages.map(stage => <li key={stage.name} data-state={stage.status}><b>{stage.name}</b><span>{stage.status}{stage.at ? ` · ${shortTime(stage.at)}` : ""}</span>{stage.detail && <small>{stage.detail}</small>}</li>)}</ol>}
    {status.next_action && <p className="sd-guarded-next"><b>Next:</b> {status.next_action}</p>}
    {status.message && <details><summary>Operation details</summary><p>{status.message}</p>{status.operation_id && <p>Operation ID: <code>{status.operation_id}</code></p>}
      {status.transport && <p>Stage: {status.transport.stage} · {status.transport.reason}{status.transport.http_status ? ` · HTTP ${status.transport.http_status}` : ""}{status.transport.content_type ? ` · ${status.transport.content_type}` : ""}</p>}</details>}
    {status.status === "verified" && <p className="sd-fine">Recorded result, not a live check.</p>}
  </article>;
}

function GuardedReview({ kind, profileId, deviceId, deviceName, onClose, onUnavailable, onSending, onUncertain, guidance }: {
  kind: Kind; profileId: string; deviceId: string; deviceName: string; guidance?: GuidanceHandlers;
  onClose: (result: GuardedOperationStatus | null) => void; onUnavailable: () => void;
  onSending: (attempt: PendingAttempt) => void; onUncertain: (attempt: PendingAttempt) => void;
}) {
  const text = copy[kind];
  const dialog = useRef<HTMLDialogElement>(null);
  const idempotencyKey = useRef("");
  const [preview, setPreview] = useState<GuardedPreview<FirmwareExecutionOperation | DriveReturnOperation> | null>(null);
  const [busy, setBusy] = useState(true);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");
  const [phrase, setPhrase] = useState("");
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    let active = true;
    dialog.current?.showModal();
    guardedApi.preview<FirmwareExecutionOperation | DriveReturnOperation>(profileId, text.resource, deviceId).then(result => {
      if (!active) return;
      setPreview(result);
      idempotencyKey.current = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    }).catch(err => {
      if (!active) return;
      if (err instanceof GuardedUnavailableError) { onUnavailable(); return; }
      setError(err instanceof Error ? err.message : String(err));
    }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [profileId, deviceId, kind]);
  const expired = !!preview && Date.parse(preview.expires_at) <= now;
  const blocked = !preview || !preview.can_apply || preview.blockers.length > 0 || preview.operations.some(op => op.blockers?.length);
  async function apply() {
    if (!preview || submitted) return;
    setSubmitted(true); setBusy(true); setError("");
    const pending: PendingAttempt = { idempotencyKey: idempotencyKey.current, reviewToken: preview.review_token, sentAt: new Date().toISOString(), state: "sending",
      profileId, deviceId, resource: text.resource };
    onSending(pending);
    try {
      const result = await guardedApi.apply(profileId, text.resource, deviceId, { review_token: preview.review_token, confirmation_phrase: phrase, idempotency_key: idempotencyKey.current });
      onClose(result);
    } catch (err) {
      // The request may or may not have taken effect. Never resend from here.
      const message = err instanceof Error ? err.message : String(err);
      onUncertain({ ...pending, state: "uncertain", error: message });
      setError(`${message} It was sent and the result is unknown. Don't retry: close this and check the status.`);
      setBusy(false);
    }
  }
  const target = preview?.target;
  const ops = preview ? preview.operations.slice().sort((x, y) => x.order - y.order) : [];
  const opBlockers = ops.flatMap(op => op.blockers ?? []);
  // Simple by design: what changes, one effect sentence, blockers, the phrase, one button.
  // Everything else (target identity, hashes, warnings, server notes) sits in closed details.
  return <dialog ref={dialog} className="firmware-upgrade-dialog raid-rebuild-dialog sd-guarded-dialog sd-review-simple" aria-label={text.title} onCancel={event => { if (busy) event.preventDefault(); else onClose(null); }}>
    <header><h2>{text.title} · {deviceName}</h2><button type="button" aria-label="Close review" disabled={busy && !error} onClick={() => onClose(null)}><X size={20} /></button></header>
    {(submitted || (busy && !preview)) && <p role="status">{submitted ? (busy ? "Sending once. Keep the server powered." : "Sent. The result is unknown; see below.") : "Checking the server…"}</p>}
    {error && <p role="alert" className="workflow-alert">{error}</p>}
    {preview && <>
      {ops.length > 0 && <ul className="sd-review-ops">{ops.map(op => kind === "firmware"
        ? (() => { const item = op as FirmwareExecutionOperation; return <li key={item.order + item.component}><strong>{item.component}</strong><span className="fw-path"><b>{item.current_version || "?"}</b><i aria-hidden="true">→</i><b className="next">{item.package_version || "?"}</b></span></li>; })()
        : (() => { const item = op as DriveReturnOperation; return <li key={item.order + item.location}><strong className="sd-mono">{item.location}</strong><span>{item.model || ""}</span></li>; })())}</ul>}
      {kind === "firmware" ? <p className="sd-review-effect">The iLO restarts by itself when it's done. The server stays on; keep its power connected.</p>
        : <p className="sd-review-effect">Each disk is read again afterwards and only counts as back in service if that read shows it.</p>}
      <BlockerGuidance title="Can't install yet" blockers={[...preview.blockers, ...opBlockers]} details={preview.blocker_details} deviceId={deviceId} handlers={guidance} />
      {expired && <p className="sd-guarded-why" role="note">This review expired. Close it and try again.</p>}
      {!blocked && !expired && <label className="workflow-field">Type <strong>{preview.confirmation_phrase}</strong><input aria-label="Confirmation phrase" autoComplete="off" disabled={busy || submitted} value={phrase} onChange={event => setPhrase(event.target.value)} /></label>}
      <footer><button type="button" className="primary-action" disabled={busy || submitted || blocked || expired || phrase !== preview.confirmation_phrase} onClick={() => void apply()}>{busy && submitted ? "Sending..." : text.apply}</button>
        <button type="button" className="secondary-action" disabled={busy && !error} onClick={() => onClose(null)}>Cancel</button></footer>
      {!!preview.warnings?.length && <details className="fw-details" aria-label="Known warnings"><summary>{preview.warnings.length} known warning{preview.warnings.length === 1 ? "" : "s"} (don't block this)</summary>
        <ul className="sd-fine">{preview.warnings.map(item => <li key={item.group + item.title}><b>{item.group}</b> · {item.health}: {item.title}{item.details ? <small> {item.details}</small> : null}</li>)}</ul></details>}
      <details className="fw-details"><summary>Technical details</summary><dl className="sd-kv sd-guarded-target">
        <div><dt>target</dt><dd>{target?.name || deviceName}{target?.host ? ` at ${target.host}` : ""}</dd></div>
        {target?.model && <div><dt>model</dt><dd>{target.model}</dd></div>}
        {target?.serial && <div><dt>serial</dt><dd>{target.serial}</dd></div>}
        {target?.controller && <div><dt>controller</dt><dd>{target.controller}</dd></div>}
        {preview.component_hash && <div><dt>package</dt><dd className="sd-mono">{preview.component_hash}</dd></div>}
        <div><dt>review ends</dt><dd>{shortTime(preview.expires_at)}</dd></div>
        {ops.map(op => (op as FirmwareExecutionOperation).action && <div key={op.order}><dt>step {op.order}</dt><dd>{(op as FirmwareExecutionOperation).action}</dd></div>)}
        {kind === "drives" && ops.map(op => { const item = op as DriveReturnOperation; return <div key={item.order + item.location}><dt>{item.location}</dt><dd>{item.current_status || "not reported"}{item.status_reasons?.length ? ` · ${item.status_reasons.join(", ")}` : ""}</dd></div>; })}
      </dl>{preview.message && <p className="sd-fine">{preview.message}</p>}</details>
    </>}
  </dialog>;
}

/** Disks whose last read reports a completed erase (or an erase-related warning). */
export function erasedDiskCount(drives: Array<{ health: string; label?: string; explanation?: string; reported_health?: string }>) {
  return drives.filter(drive => {
    const text = [drive.label, drive.explanation, drive.reported_health, drive.health].filter(Boolean).join(" ");
    return /erase\s*completed|erasecompleted/i.test(text) || (drive.health === "Warning" && /eras/i.test(text));
  }).length;
}
