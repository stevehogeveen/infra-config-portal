import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { guardedApi, type FirmwareRecoveryPreview, type GuardedOperationStatus } from "../api";

export function FirmwareRecovery({ profileId, deviceId, deviceName, operationId, onClose }: {
  profileId: string; deviceId: string; deviceName: string; operationId: string;
  onClose: (result: GuardedOperationStatus | null) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const live = useRef(false);
  const sent = useRef(false);
  const [preview, setPreview] = useState<FirmwareRecoveryPreview | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [now, setNow] = useState(Date.now());
  const matches = (value: { profile_id?: string; device_id?: string; operation_id?: string | null }) =>
    value.profile_id === profileId && value.device_id === deviceId && value.operation_id === operationId;
  useEffect(() => {
    live.current = true;
    let current = true;
    dialog.current?.showModal();
    const timer = setInterval(() => setNow(Date.now()), 1000);
    guardedApi.recoveryPreview(profileId, deviceId, operationId).then(result => {
      if (!current) return;
      if (!matches(result)) throw new Error("The review does not match this server and attempt.");
      setPreview(result);
    }).catch(err => { if (current) setError(err instanceof Error ? err.message : String(err)); })
      .finally(() => { if (current) setBusy(false); });
    return () => { current = false; live.current = false; clearInterval(timer); };
  }, [profileId, deviceId, operationId]);
  async function checkAgain() {
    setBusy(true); setError("");
    try {
      const result = await guardedApi.recoveryPreview(profileId, deviceId, operationId);
      if (!matches(result)) throw new Error("The review does not match this server and attempt.");
      if (live.current) setPreview(result);
    } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(false); }
  }
  const expires = Date.parse(preview?.expires_at ?? "");
  const eligible = !!preview?.can_close && !preview.blockers.length && !!preview.review_token
    && !!preview.confirmation_phrase && Number.isFinite(expires) && expires > now;
  function accept(result: GuardedOperationStatus) {
    if (!matches(result) || result.resource !== "firmware-execution" || result.status !== "failed"
        || result.resolution !== "operator_closed_unverified" || result.dispatch_prevented !== false)
      throw new Error("Closure is not confirmed for this attempt. Read its recorded status.");
    onClose(result);
  }
  async function closeAttempt() {
    if (!eligible || !preview?.review_token || sent.current) return;
    sent.current = true; setSubmitted(true); setBusy(true); setError("");
    try {
      const result = await guardedApi.closeUnverified(profileId, deviceId,
        { operation_id: operationId, review_token: preview.review_token, confirmation_phrase: preview.confirmation_phrase! });
      if (live.current) accept(result);
    } catch (err) { if (live.current) setError(`${err instanceof Error ? err.message : String(err)} No automatic retry was sent.`); }
    finally { if (live.current) setBusy(false); }
  }
  async function readResult() {
    setBusy(true); setError("");
    try { const result = await guardedApi.status(profileId, "firmware-execution", deviceId); if (live.current) accept(result); }
    catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(false); }
  }
  return <dialog ref={dialog} className="firmware-upgrade-dialog raid-rebuild-dialog sd-guarded-dialog sd-review-simple"
    aria-label="Cancel upgrade" onCancel={event => { if (busy) event.preventDefault(); else onClose(null); }}>
    <header><h2>Cancel upgrade · {deviceName}</h2><button type="button" aria-label="Close review" disabled={busy} onClick={() => onClose(null)}><X size={20} /></button></header>
    {busy && <p role="status">{submitted ? "Cancelling…" : "Checking…"}</p>}
    {error && <p role="alert">{error}</p>}
    {preview && <>
      <p>Dismiss this attempt and unlock {deviceName}? Its outcome is unknown. This does not stop an update already running on the iLO.</p>
      {!!preview.blockers.length && <ul>{preview.blockers.map(blocker => <li key={blocker}>{blocker}</li>)}</ul>}
      {!eligible && <button type="button" className="secondary-action" disabled={busy} onClick={() => void checkAgain()}>Refresh status</button>}
      <details className="fw-details"><summary>Details</summary><p className="sd-fine">{preview.message}</p>
        {preview.evidence_at && <p className="sd-fine">Last read of the iLO: {new Date(preview.evidence_at).toLocaleString()}</p>}</details>
    </>}
    <footer>
      {!submitted && <button className="primary-action" type="button" disabled={busy || !eligible} onClick={() => void closeAttempt()}>Yes</button>}
      {submitted && <button className="secondary-action" type="button" disabled={busy} onClick={() => void readResult()}>Read recorded status</button>}
      <button className="secondary-action" type="button" disabled={busy} onClick={() => onClose(null)}>No</button>
    </footer>
  </dialog>;
}
