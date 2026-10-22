import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { contractApi, type Certificate, type Contract, type Progress } from "../contractApi";
import { HandoverPage } from "./HandoverPage";
import { useStudio } from "./studio/StudioContext";
import "../kitContract.css";

function Value({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") return <>Not saved</>;
  if (Array.isArray(value)) return <>{value.length ? value.map((v, i) => <span className="kc-value" key={i}><Value value={v} /></span>) : "None"}</>;
  if (typeof value === "object") return <dl className="kc-values">{Object.entries(value).map(([key, v]) => <div key={key}><dt>{key.replace(/_/g, " ")}</dt><dd><Value value={v} /></dd></div>)}</dl>;
  return <>{String(value)}</>;
}

export function KitContract({ profileId: given }: { profileId?: string } = {}) {
  const studio = useStudio();
  const profileId = given ?? studio?.profileId;
  const [document, setDocument] = useState<Contract | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [certificate, setCertificate] = useState<Certificate | null>(null);
  const [error, setError] = useState("");
  const [approving, setApproving] = useState(false);
  const epoch = useRef(0);
  const busy = useRef(false);
  useEffect(() => {
    const version = ++epoch.current;
    setDocument(null); setProgress(null); setCertificate(null); setError("");
    if (profileId) contractApi.get(profileId).then(data => { if (version === epoch.current) setDocument(data); }).catch(err => { if (version === epoch.current) setError(String(err)); });
    return () => { ++epoch.current; };
  }, [profileId]);

  useEffect(() => {
    if (!profileId || progress?.state !== "converging") return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const version = epoch.current;
    async function poll() {
      if (stopped || version !== epoch.current) return;
      try {
        const next = await contractApi.reconcile(profileId!);
        if (stopped || version !== epoch.current) return;
        if (next.state === "converged") {
          const proof = await contractApi.certificate(profileId!);
          if (!stopped && version === epoch.current) { setCertificate(proof); setProgress(next); }
        } else {
          setProgress(next);
          if (next.state === "converging") timer = setTimeout(() => void poll(), 10000);
        }
      } catch (err) {
        if (!stopped && version === epoch.current) {
          setError(err instanceof Error ? err.message : String(err));
          setProgress(p => p ? { ...p, state: "blocked", message: "Polling stopped. Review the recorded run before resuming.", href: "/contract" } : p);
        }
      }
    }
    // Approval starts the first tick; subsequent ticks wait ten seconds after each response.
    timer = setTimeout(() => void poll(), 0);
    return () => { stopped = true; clearTimeout(timer); };
  }, [profileId, progress?.state]);

  async function approve() {
    if (!profileId || !document || busy.current) return;
    busy.current = true; setApproving(true); setError("");
    const version = epoch.current;
    try {
      await contractApi.approve(profileId, document.digest);
      if (version === epoch.current) setProgress({ state: "converging", item: null, message: "Approved. Starting the first contract tick.", items: document.items });
    } catch (err) { if (version === epoch.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { busy.current = false; if (version === epoch.current) setApproving(false); }
  }

  if (!profileId) return <p>Select a kit to review its contract.</p>;
  if (!document) return <p role={error ? "alert" : "status"}>{error || "Reading the saved contract…"}</p>;
  const items = progress?.items ?? document.items;
  return <article className="kit-contract">
    <header><p className="kc-eyebrow">{document.kit} · Saved plan</p><h1>Kit contract</h1>
      <p>Review the desired kit below. Approval authorizes the build, firmware updates, RAID creation, ESXi installation, Windows deployment and its acceptance restart. Existing RAID volumes stop the build.</p>
      <p>Observed values are historical records with their check times. Opening this page sends no equipment requests. Leaving stops polling; active equipment runs may continue.</p>
    </header>
    <section><h2>Network <Link to="/setup/defaults">Edit</Link></h2><Value value={document.network} /></section>
    {items.map(item => <section key={item.id} className="kc-item"><h2>{item.title} <Link to={item.href}>Edit</Link></h2>
      <div className="kc-columns"><div><h3>Desired · saved plan</h3><Value value={item.desired} /></div>
        {progress && <div><h3>Observed · recorded evidence</h3><p>{item.state || "Not checked"}</p><Value value={item.observed} /></div>}</div>
    </section>)}
    <p className="kc-digest">Contract SHA-256 <code>{document.digest}</code></p>
    {error && <p role="alert">{error}</p>}
    {progress && <aside role={progress.state === "blocked" ? "alert" : "status"}><strong>{progress.state}</strong><p>{progress.message}</p>{progress.href && <Link to={progress.href}>Open settings to resolve this</Link>}</aside>}
    {(!progress || progress.state === "unapproved") && <button className="primary-action" disabled={approving} onClick={() => void approve()}>{approving ? "Approving…" : "Approve contract"}</button>}
    {progress?.state === "blocked" && <p><Link to="/contract" onClick={() => window.location.reload()}>Reload the contract for a new review</Link></p>}
    {certificate && <section><h2>As-built certificate</h2><p>Recorded evidence · prepared {new Date(certificate.generated_at).toLocaleString()} · {certificate.state}</p>
      <div className="kc-table"><table><thead><tr><th>Item</th><th>Desired</th><th>Verified</th><th>Verified at</th></tr></thead><tbody>{certificate.items.map(item => <tr key={item.id}><th>{item.title}</th><td><Value value={item.desired} /></td><td><Value value={item.verified} /></td><td>{item.verified_at || "No recorded timestamp"}</td></tr>)}</tbody></table></div>
      <HandoverPage profileId={profileId} />
    </section>}
  </article>;
}
