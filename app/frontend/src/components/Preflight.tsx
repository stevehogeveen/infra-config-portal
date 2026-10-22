import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, ClipboardCheck, X } from "lucide-react";
import { jobsApi, type PreflightItem as Item, type PreflightResult as Result } from "../api";

/** One button on My Rack: checks saved data and this PC before the first change. Contacts no equipment. */
export function PreflightButton({ profileId }: { profileId: string }) {
  const [open, setOpen] = useState(false);
  return <>
    <button type="button" className="secondary-action preflight-btn" onClick={() => setOpen(true)}><ClipboardCheck size={16} />Pre-flight check</button>
    {open && <PreflightDialog profileId={profileId} onClose={() => setOpen(false)} />}
  </>;
}

function PreflightDialog({ profileId, onClose }: { profileId: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
    jobsApi.preflight(profileId)
      .then(setResult).catch(err => setError(err instanceof Error ? err.message : String(err)));
  }, [profileId]);
  const groups = new Map<string, Item[]>();
  for (const item of result?.items ?? []) groups.set(item.group, [...(groups.get(item.group) ?? []), item]);
  const counts = { fail: result?.items.filter(i => i.state === "fail").length ?? 0, warn: result?.items.filter(i => i.state === "warn").length ?? 0 };
  return <dialog ref={dialog} className="inst preflight" aria-label="Pre-flight check" onCancel={event => { event.preventDefault(); onClose(); }}>
    <header className="inst-h">
      <span className="inst-icon"><ClipboardCheck size={22} aria-hidden="true" /></span>
      <div><h2>Pre-flight check</h2><p>Saved settings and this PC. No equipment is contacted.</p></div>
      <button type="button" aria-label="Close pre-flight check" onClick={onClose}><X size={20} /></button>
    </header>
    <div className="preflight-body">
      {!result && !error && <p role="status">Checking…</p>}
      {error && <p role="alert">{error}</p>}
      {result && <p className={`preflight-verdict pf-${result.state}`}>{result.state === "ok" ? "Ready: everything checks out." : result.state === "warn" ? `Ready with ${counts.warn} thing${counts.warn === 1 ? "" : "s"} to look at.` : `Not ready: ${counts.fail} thing${counts.fail === 1 ? "" : "s"} to fix first.`}</p>}
      {[...groups].map(([group, items]) => <section key={group} aria-label={group}>
        <h3>{group}</h3>
        <ul>{items.map(item => <li key={item.name} className={`pf-${item.state}`}>
          <span className="pf-icon" aria-hidden="true">{item.state === "ok" ? <Check size={14} /> : item.state === "warn" ? <AlertTriangle size={14} /> : <X size={14} />}</span>
          <span><b>{item.name}</b><small>{item.detail}</small></span>
          {item.fix && item.state !== "ok" && <a href={item.fix}>Fix</a>}
        </li>)}</ul>
      </section>)}
    </div>
  </dialog>;
}
