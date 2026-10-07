import { useRef, useState } from "react";
import { CheckCircle2, FileCheck2, Lock } from "lucide-react";
import { guardedApi, GuardedUnavailableError, type BridgePreparation, type FirmwareCapabilities, type GuardedOperationStatus } from "../api";
import { ScopeReview, useWriteScope, WRITE_SCOPE_CHANGED } from "./studio/WriteScope";
import { GuardedExecution } from "./GuardedExecution";
import { BlockerGuidance, type GuidanceHandlers } from "./BlockerGuidance";

/*
 * The iLO update as one button at a time: Prepare update -> Upgrade -> Lock to read-only.
 * Prepare is operator-started and read-only (one iLO read, one offline signature check).
 * Upgrade narrows write scope to firmware only first when needed (its own typed phrase),
 * then opens the guarded install review (its own typed phrase). Only real blockers show.
 */
type Prep = { state: "idle" | "busy" | "done" | "error"; caps?: FirmwareCapabilities; prep?: BridgePreparation; error?: string };

export function FirmwareUpdatePanel({ profileId, deviceId, deviceName, step, onActivity, onChanged }: {
  profileId: string; deviceId: string; deviceName: string; step: string; onActivity: (active: boolean) => void; onChanged: () => void;
}) {
  const [prep, setPrep] = useState<Prep>({ state: "idle" });
  const [status, setStatus] = useState<GuardedOperationStatus | null>(null);
  const [active, setActive] = useState(false);
  const [scopeTarget, setScopeTarget] = useState<"firmware_only" | "read_only" | null>(null);
  const [scopeNote, setScopeNote] = useState("");
  const [previousVerified, setPreviousVerified] = useState<string | null>(null);
  const pendingOpen = useRef<(() => void) | null>(null);
  const { read: scope, load: loadScope } = useWriteScope();
  const currentScope = scope.state === "ok" ? scope.data.scope : null;

  async function prepare() {
    if (status?.status === "verified") setPreviousVerified(status.operation_id ?? "legacy-verified");
    setPrep({ state: "busy" });
    try {
      const caps = await guardedApi.capabilities(profileId, deviceId);
      const bridge = await guardedApi.prepareBridge(profileId, deviceId);
      setPrep({ state: "done", caps, prep: bridge });
    } catch (err) {
      setPrep({ state: "error", error: err instanceof GuardedUnavailableError ? "The app can't prepare this update on this server yet." : err instanceof Error ? err.message : String(err) });
    }
  }
  const blockers = prep.caps?.ilo_update_health?.blockers ?? [];
  // "How to fix" buttons: reading and preparing again restart step 1; scope opens its own review.
  const guidance: GuidanceHandlers = {
    read_again: () => void prepare(), prepare_again: () => void prepare(),
    narrow_scope_firmware: () => setScopeTarget("firmware_only"),
  };
  const genuine = !!prep.prep?.authentication?.binary_authenticated;
  const target = prep.prep?.target_version ?? (step === "1.48" ? step : "unknown");
  const supported = target === "1.48" || target === "3.19";
  const ready = prep.state === "done" && genuine && supported && !!prep.caps?.ilo_update_health && !blockers.length;
  const verified = status?.status === "verified" && previousVerified !== (status.operation_id ?? "legacy-verified");
  const stage = verified ? 3 : ready || active ? 2 : 1;

  return <div className="fw-wizard">
    <ol className="fw-stages" aria-label="Update steps">
      {["Prepare", "Upgrade", "Lock"].map((label, index) => <li key={label} className={index + 1 < stage ? "done" : index + 1 === stage ? "now" : ""} aria-current={index + 1 === stage ? "step" : undefined}><span>{index + 1}</span>{label}</li>)}
    </ol>

    {stage === 1 && <section className="fw-stage" aria-label="Prepare update">
      <p>Reads the iLO once and checks the {step} file in your package. Nothing is installed.</p>
      <button type="button" className="primary-action fw-go" disabled={prep.state === "busy"} onClick={() => void prepare()}><FileCheck2 size={17} />{prep.state === "busy" ? "Preparing…" : "Prepare update"}</button>
      {prep.state === "error" && <p className="fw-stop" role="alert">{prep.error}</p>}
      {prep.state === "done" && !genuine && <p className="fw-stop" role="alert">The {step} file in your package could not be verified as HPE's. Don't install it; choose the SPP again.</p>}
      {prep.state === "done" && !supported && <p className="fw-stop" role="alert">This firmware version has no installation adapter.</p>}
      {prep.state === "done" && genuine && !prep.caps?.ilo_update_health && <p className="fw-stop" role="alert">The iLO answered without an update check. Press Prepare update again.</p>}
      <BlockerGuidance title="Fix this first" blockers={blockers} details={prep.caps?.ilo_update_health?.blocker_details} deviceId={deviceId} handlers={guidance} />
    </section>}

    {stage === 2 && !active && <section className="fw-stage" aria-label="Upgrade">
      <p className="fw-ok"><CheckCircle2 size={17} />Ready. The iLO answered and the {target} file is genuine.</p>
      <p>The iLO restarts itself after the update. The server stays on; keep its power connected.</p>
    </section>}

    <GuardedExecution kind="firmware" profileId={profileId} deviceId={deviceId} deviceName={deviceName} compact
      guidance={{ ...guidance, read_again: () => setPrep({ state: "idle" }), prepare_again: () => setPrep({ state: "idle" }) }}
      openLabel={`Upgrade iLO to ${target}`} showReview={stage === 2 && !verified}
      onActivity={next => { setActive(next); onActivity(next); }} onStatus={setStatus} onChanged={onChanged}
      onRequestOpen={open => {
        if (currentScope === "firmware_only") open();
        else { pendingOpen.current = open; setScopeTarget("firmware_only"); }
      }} />

    {stage === 3 && <section className="fw-stage" aria-label="Lock">
      <p className="fw-ok"><CheckCircle2 size={17} />Updated and verified.</p>
      {currentScope === "read_only" ? <><p>Changes are locked again.</p>{target !== "3.19" && <button type="button" className="primary-action fw-go" onClick={() => void prepare()}><FileCheck2 size={17} />Prepare next update</button>}</> : <>
        <p>Last step: lock the server so nothing else can be changed.</p>
        <button type="button" className="primary-action fw-go" onClick={() => setScopeTarget("read_only")}><Lock size={17} />Lock to read-only</button></>}
    </section>}
    {scopeNote && <p className="fw-stop" role="status">{scopeNote}</p>}

    {scopeTarget && <ScopeReview key={scopeTarget} target={scopeTarget}
      onUnavailable={() => { setScopeTarget(null); pendingOpen.current = null; setScopeNote("The app can't change what's allowed on this server yet."); }}
      onClose={applied => {
        const next = pendingOpen.current; pendingOpen.current = null;
        setScopeTarget(null); void loadScope(); window.dispatchEvent(new Event(WRITE_SCOPE_CHANGED));
        // The install review re-checks scope itself; an unapplied change simply leaves it blocked.
        if (applied && next) next();
      }} />}
  </div>;
}
