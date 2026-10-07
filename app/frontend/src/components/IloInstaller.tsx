import { useEffect, useRef, useState } from "react";
import { Cpu, X } from "lucide-react";
import { guardedApi, writeScopeApi, type GuardedOperationStatus, type FirmwareExecutionOperation } from "../api";
import { GuardedExecution, attemptKey, readAttempt, writeAttempt, type PendingAttempt } from "./GuardedExecution";
import { WRITE_SCOPE_CHANGED } from "./studio/WriteScope";

const RESOURCE = "firmware-execution" as const;
const ACTIVE = new Set(["submitting", "accepted", "running", "uncertain"]);

export function IloInstaller({ profileId, deviceId, deviceName, installed, onClose, onChanged }: {
  profileId: string; deviceId: string; deviceName: string; installed: string | null;
  onClose: () => void; onChanged: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const live = useRef(false);
  const sending = useRef(false);
  const key = attemptKey(profileId, RESOURCE, deviceId);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState<GuardedOperationStatus | null>(null);
  const [started, setStarted] = useState(false);
  const [verificationMessage, setVerificationMessage] = useState("");
  const version = installed?.match(/(\d+)\.(\d+)/);
  const target = version && (Number(version[1]) < 1 || (Number(version[1]) === 1 && Number(version[2]) < 48)) ? "1.48" : "3.19";

  useEffect(() => {
    live.current = true;
    let current = true;
    dialog.current?.showModal();
    guardedApi.status(profileId, RESOURCE, deviceId).then(recorded => {
      if (!current) return;
      setStatus(recorded);
      setStarted(!!readAttempt(key) || ACTIVE.has(recorded.status));
    }).catch(err => { if (current) setError(String(err)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; live.current = false; };
  }, [profileId, deviceId, key]);

  const installing = !!status && ["submitting", "accepted", "running"].includes(status.status);
  useEffect(() => {
    if (!installing) return;
    const timer = setInterval(() => {
      guardedApi.status(profileId, RESOURCE, deviceId).then(result => {
        if (live.current) setStatus(result);
      }).catch(() => {});
    }, 5000);
    return () => clearInterval(timer);
  }, [installing, profileId, deviceId]);

  // Steve: "just show me when complete". While installing, the installer asks the iLO for its
  // version every 20 s by itself (read-only); done only comes from that read, never from the send.
  const operationId = status?.operation_id;
  useEffect(() => {
    if (!installing || !operationId) return;
    const timer = setInterval(() => {
      if (sending.current) return;
      guardedApi.verify(profileId, deviceId, operationId).then(result => {
        if (live.current && result.operation_id === operationId && result.status === "verified") setStatus(result);
      }).catch(() => { /* still installing or restarting; try again next tick */ });
    }, 20000);
    return () => clearInterval(timer);
  }, [installing, operationId, profileId, deviceId]);

  async function install() {
    if (sending.current || readAttempt(key) || (status && ACTIVE.has(status.status))) return;
    sending.current = true;
    setBusy("Preparing the update..."); setError("");
    let attempt: PendingAttempt | null = null;
    try {
      await guardedApi.capabilities(profileId, deviceId);
      const prepared = await guardedApi.prepareBridge(profileId, deviceId);
      if (prepared.profile_id !== profileId || prepared.device_id !== deviceId || prepared.target_version !== target)
        throw new Error("The available update changed. Close this window and select the update again.");
      const scope = await writeScopeApi.get();
      if (scope.scope !== "firmware_only") {
        const review = await writeScopeApi.preview("firmware_only");
        if (review.blockers?.length) throw new Error(review.blockers.join(" "));
        const changed = await writeScopeApi.apply({ review_token: review.review_token, confirmation_phrase: review.confirmation_phrase ?? "" });
        window.dispatchEvent(new Event(WRITE_SCOPE_CHANGED));
        if (changed.scope !== "firmware_only") throw new Error("Firmware access could not be enabled.");
      }
      const review = await guardedApi.preview<FirmwareExecutionOperation>(profileId, RESOURCE, deviceId);
      const blockers = [...review.blockers, ...review.operations.flatMap(op => op.blockers ?? [])];
      if (!review.can_apply || blockers.length) throw new Error(blockers.join(" ") || "This firmware cannot be installed on this server.");
      if (review.operations.length !== 1 || review.operations[0].package_version !== target)
        throw new Error("The available update changed. Select the update again.");
      const idempotencyKey = crypto.randomUUID();
      attempt = { idempotencyKey, reviewToken: review.review_token, sentAt: new Date().toISOString(), state: "sending", profileId, deviceId, resource: RESOURCE };
      writeAttempt(key, attempt);
      if (live.current) { setStatus(null); setStarted(true); setBusy("Sending the update to the iLO... This can take a minute."); }
      const result = await guardedApi.apply(profileId, RESOURCE, deviceId, {
        review_token: review.review_token, confirmation_phrase: review.confirmation_phrase, idempotency_key: idempotencyKey,
      });
      if (result.profile_id !== profileId || result.device_id !== deviceId || result.resource !== RESOURCE)
        throw new Error("The response did not identify this server. Read recorded status before another update.");
      writeAttempt(key, result.status === "accepted" ? { ...attempt, state: "accepted" } : null);
      if (live.current) setStatus(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (attempt) writeAttempt(key, { ...attempt, state: "uncertain", error: message });
      if (live.current) {
        setError(message);
        if (attempt) setStatus(await guardedApi.status(profileId, RESOURCE, deviceId).catch(() => null));
      }
    } finally {
      sending.current = false;
      if (live.current) setBusy("");
    }
  }

  async function verify() {
    if (!status?.operation_id || sending.current) return;
    setBusy("Checking the installed version..."); setError("");
    try {
      const result = await guardedApi.verify(profileId, deviceId, status.operation_id)
        .catch(() => guardedApi.status(profileId, RESOURCE, deviceId));
      if (!live.current) return;
      if (result.operation_id !== status.operation_id) throw new Error("The recorded operation changed. Reopen this update to see its status.");
      setStatus(result);
      setVerificationMessage(result.status === "verified" ? "" : "Not finished yet, give it a minute.");
    } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(""); }
  }

  function close() { if (started && !busy) onChanged(); onClose(); }

  return <dialog ref={dialog} className="inst" aria-label={`iLO firmware update on ${deviceName}`}
    onCancel={event => { event.preventDefault(); close(); }}>
    <header className="inst-h"><span className="inst-icon"><Cpu size={22} /></span>
      <div><h2>iLO firmware update</h2><p>{deviceName} · {installed || "iLO"} → {target}</p></div>
      <button type="button" aria-label="Close installer" onClick={close}><X size={20} /></button>
    </header>
    <section className="inst-main" aria-live="polite">
      {loading ? <p>Loading...</p> : !started ? <>
        <h3>Install iLO {target} on {deviceName}?</h3>
        <p>This enables firmware access and installs the update. The iLO will restart; keep power connected.</p>
      </> : <>
        <h3>{status?.status === "verified" ? "Complete" : status?.status === "uncertain" ? "Update outcome unknown" : `Installing iLO ${target}…`}</h3>
        {status?.status === "verified" && <p className="inst-ok">The iLO is now on {target}.</p>}
        {!busy && installing && <p>The iLO installs the update and restarts itself. This takes a few minutes; this window will say when it's complete.</p>}
        {!busy && !installing && status?.status !== "verified" && <GuardedExecution kind="firmware" profileId={profileId} deviceId={deviceId} deviceName={deviceName} compact showReview={false}
          onStatus={next => { if (next && live.current) setStatus(next); }} onChanged={onChanged} />}
        {verificationMessage && <p>{verificationMessage}</p>}
        {status?.status === "failed" && <button type="button" className="secondary-action" onClick={() => { setStarted(false); setError(""); }}>Start again</button>}
      </>}
      {busy && <p role="status">{busy}</p>}
      {(busy || installing) && <progress aria-label="Firmware update in progress" />}
      {error && <p role="alert">{error}</p>}
    </section>
    <footer className="inst-f">
      <button type="button" className="secondary-action" onClick={close}>{started || busy ? "Close" : "No"}</button>
      {!started && <button type="button" className="primary-action" disabled={loading || !!busy || !!readAttempt(key)} onClick={() => void install()}>Yes</button>}
    </footer>
  </dialog>;
}
