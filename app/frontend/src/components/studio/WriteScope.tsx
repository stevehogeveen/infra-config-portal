import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { KeyRound, X } from "lucide-react";
import { GuardedUnavailableError, writeScopeApi, type WriteScopeOperation, type WriteScopePreview, type WriteScopeState } from "../../api";
import { shortTime } from "./ProvenanceChip";
import { BlockerGuidance } from "../BlockerGuidance";

/*
 * Runtime write scope. The app only ever offers two transitions: firmware_only and read_only.
 * Storage, power and mixed scopes are displayed exactly as the server reports them and are
 * never granted from here. Nothing reads as a grant unless GET /runtime/write-scope says so.
 */
export const WRITE_SCOPE_CHANGED = "studio:write-scope-changed";
export const FIRMWARE_SCOPE_BLOCKER = /Exclusive firmware maintenance scope is required/i;
const scopeLabel: Record<string, string> = { read_only: "read-only", firmware_only: "firmware only", storage_only: "disks & RAID only", esxi_install_only: "ESXi install only", vm_deploy_only: "Windows deploy only", switch_setup_only: "switch setup only", storage: "storage only", power: "power only", mixed: "several kinds" };
export const describeScope = (scope: string) => scopeLabel[scope] ?? scope;
const operationText = (op: WriteScopeOperation) => typeof op === "string" ? op
  : [op.description || op.name || op.resource || op.kind || "operation", op.device_id ? `on ${op.device_id}` : "", op.status ? `(${op.status})` : "", op.operation_id ? `· ${op.operation_id}` : ""].filter(Boolean).join(" ");

type Read = { state: "loading" } | { state: "unavailable" } | { state: "error"; message: string } | { state: "ok"; data: WriteScopeState };

export function useWriteScope() {
  const [read, setRead] = useState<Read>({ state: "loading" });
  const generation = useRef(0);
  async function load() {
    const id = ++generation.current;
    try { const data = await writeScopeApi.get(); if (id === generation.current) setRead({ state: "ok", data }); }
    catch (err) {
      if (id !== generation.current) return;
      setRead(err instanceof GuardedUnavailableError ? { state: "unavailable" } : { state: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }
  useEffect(() => {
    void load();
    const reload = () => void load();
    window.addEventListener(WRITE_SCOPE_CHANGED, reload);
    return () => window.removeEventListener(WRITE_SCOPE_CHANGED, reload);
  }, []);
  return { read, load };
}

/** Top-bar pill. A missing service is neutral: the server's own configuration decides. */
export function WriteScopePill() {
  const { read, load } = useWriteScope();
  const location = useLocation();
  useEffect(() => { void load(); }, [location.pathname]);
  const text = read.state === "ok" ? (read.data.scope === "read_only" ? "Read-only mode" : `Changes allowed: ${describeScope(read.data.scope)}`) : read.state === "loading" ? "Changes allowed: reading…"
    : read.state === "unavailable" ? "Changes allowed: set by server configuration" : "Changes allowed: unknown";
  const tone = read.state === "ok" && read.data.scope !== "read_only" ? "grant" : "neutral";
  const title = read.state === "ok" ? `Reported by the server${read.data.source ? ` (source: ${read.data.source})` : ""}${read.data.changed_at ? `, changed ${shortTime(read.data.changed_at)}${read.data.changed_by ? ` by ${read.data.changed_by}` : ""}` : ""}.`
    : read.state === "error" ? read.message : "The app cannot change write scope yet; the server configuration decides which writes are allowed.";
  return <span className={`sd-scope-pill ${tone}`} role="status" title={title}><KeyRound size={13} aria-hidden="true" />{text}</span>;
}

/** Check firmware entry: preview, effects and blockers, typed phrase, one apply, then re-read. */
export function WriteScopeControl() {
  const { read, load } = useWriteScope();
  const [target, setTarget] = useState<"firmware_only" | "read_only" | null>(null);
  const [previewUnavailable, setPreviewUnavailable] = useState(false);
  const [notice, setNotice] = useState("");
  const current = read.state === "ok" ? read.data.scope : null;
  const unavailable = read.state === "unavailable" || previewUnavailable;
  const locks = read.state === "ok" ? read.data.active_operations ?? [] : [];
  const scopeBlockers = read.state === "ok" ? read.data.blockers ?? [] : [];
  return <section className="sd-guarded sd-scope" id="write-scope" aria-label="Write scope">
    <header className="sd-guarded-h"><div><p className="eyebrow">Allowed changes</p><h3>Limit changes to firmware only</h3></div></header>
    {read.state === "ok" && <p>Right now the server allows: <strong>{read.data.scope === "read_only" ? "nothing (read-only)" : describeScope(read.data.scope)}</strong>
      {read.data.changed_at ? <> · set in the app {shortTime(read.data.changed_at)}{read.data.changed_by ? ` by ${read.data.changed_by}` : ""}</> : read.data.source === "server_configuration" ? <> · from the server's configuration file</> : null}</p>}
    {read.state === "ok" && !["read_only", "firmware_only"].includes(read.data.scope) && <p className="sd-fine">Before the update, limit this to firmware only so nothing else can be sent. The app can only narrow what's allowed, never widen it.</p>}
    {read.state === "error" && <p role="alert" className="workflow-alert">Write scope could not be read: {read.message}</p>}
    <div className="sd-guarded-act">
      <button type="button" className="secondary-action" disabled={unavailable || read.state !== "ok" || current === "firmware_only"} onClick={() => { setNotice(""); setTarget("firmware_only"); }}>Limit to firmware only</button>
      <button type="button" className="secondary-action" disabled={unavailable || read.state !== "ok" || current === "read_only"} onClick={() => { setNotice(""); setTarget("read_only"); }}>Lock to read-only</button>
      {unavailable && <p className="sd-guarded-why" role="note">Not available yet: the app cannot change write scope on this server yet.</p>}
    </div>
    {!!scopeBlockers.length && <div className="sd-guarded-gates" role="note"><strong>The server reports</strong><ul>{scopeBlockers.map(item => <li key={item}>{item}</li>)}</ul></div>}
    {!!locks.length && <div className="sd-guarded-gates" role="note" aria-label="Unresolved operation locks"><strong>Unresolved operation locks stay in place</strong>
      <ul>{locks.map((op, index) => <li key={index}>{operationText(op)}</li>)}</ul><small>Changing scope never releases these. Each must be verified or reconciled in its own workflow.</small></div>}
    {notice && <p role="status" className="sd-guarded-note">{notice}</p>}
    {target && <ScopeReview key={target} target={target} onUnavailable={() => { setTarget(null); setPreviewUnavailable(true); }}
      onClose={applied => { setTarget(null); if (applied) { setNotice(`Change sent. What's allowed above is the server's new reading.`); void load(); window.dispatchEvent(new Event(WRITE_SCOPE_CHANGED)); } }} />}
  </section>;
}

export function ScopeReview({ target, onClose, onUnavailable }: { target: "firmware_only" | "read_only"; onClose: (applied: boolean) => void; onUnavailable: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [preview, setPreview] = useState<WriteScopePreview | null>(null);
  const [busy, setBusy] = useState(true);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [phrase, setPhrase] = useState("");
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    let active = true;
    dialog.current?.showModal();
    writeScopeApi.preview(target).then(result => { if (active) setPreview(result); })
      .catch(err => { if (!active) return; if (err instanceof GuardedUnavailableError) onUnavailable(); else setError(err instanceof Error ? err.message : String(err)); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [target]);
  const needsPhrase = !!preview?.confirmation_phrase;
  const expired = !!preview && Date.parse(preview.expires_at) <= now;
  const blocked = !preview || !!preview.blockers?.length || preview.target_scope !== target;
  const ready = !!preview && !blocked && !expired && !sent && (!needsPhrase || phrase === preview.confirmation_phrase);
  async function apply() {
    if (!preview || sent) return;
    setSent(true); setBusy(true); setError("");
    try { await writeScopeApi.apply({ review_token: preview.review_token, confirmation_phrase: needsPhrase ? phrase : "" }); onClose(true); }
    catch (err) { setError(`${err instanceof Error ? err.message : String(err)} It may or may not have changed. Close and check again; nothing is resent.`); setBusy(false); }
  }
  const title = target === "firmware_only" ? "Only update the iLO firmware" : "Lock to read-only";
  // One sentence of effect, the phrase, one button. Blockers and failures are the only extras.
  return <dialog ref={dialog} className="firmware-upgrade-dialog raid-rebuild-dialog sd-guarded-dialog sd-scope-dialog" aria-label={title} onCancel={event => { if (busy) event.preventDefault(); else onClose(sent); }}>
    <header><h2>{title}</h2><button type="button" aria-label="Close review" disabled={busy && !error} onClick={() => onClose(sent)}><X size={20} /></button></header>
    {sent && <p role="status">{busy ? "Sending once…" : "Sent; the result is unknown. Close and check again. Nothing is resent."}</p>}
    {!preview && busy && !sent && <p role="status">Checking with the server…</p>}
    {error && <p role="alert" className="workflow-alert">{error}</p>}
    {preview && <>
      {!!preview.effects?.length && <p className="sd-scope-effect">{preview.effects.join(" ")} Reading the server still works.</p>}
      <BlockerGuidance title="Can't do this yet" blockers={preview.blockers ?? []} details={preview.blocker_details} />
      {preview.target_scope !== target && <p className="sd-guarded-why" role="note">The server answered for a different setting, so this can't be applied.</p>}
      {expired && <p className="sd-guarded-why" role="note">This review expired. Close and try again.</p>}
      {needsPhrase && <label className="workflow-field">Type <strong>{preview.confirmation_phrase}</strong><input aria-label="Confirmation phrase" autoComplete="off" disabled={busy || sent || blocked || expired} value={phrase} onChange={event => setPhrase(event.target.value)} /></label>}
      <footer><button type="button" className="primary-action" disabled={!ready || busy} onClick={() => void apply()}>{target === "firmware_only" ? "Confirm" : "Lock"}</button>
        <button type="button" className="secondary-action" disabled={busy && !error} onClick={() => onClose(sent)}>Cancel</button></footer>
    </>}
  </dialog>;
}
