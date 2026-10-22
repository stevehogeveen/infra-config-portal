import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Copy, Pencil, FileText, X, Save, Printer, FolderOpen } from "lucide-react";
import { api, jobsApi, type KitReport } from "../api";
import type { LabProfileList } from "../types";
import "../kitLibrary.css";
import { FirmwareAssessmentTable } from "./FirmwareAssessmentTable";
import { KIT_DIALOG_EVENT, type KitDialogMode } from "./studio/studioEvents";
import { useTheme } from "./studio/theme";

export function KitLibrary({ state, onReload, variant = "bar" }: { state: LabProfileList | null; onReload: () => Promise<void>; variant?: "bar" | "menu" }) {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [theme, setTheme] = useTheme();
  const [mode, setMode] = useState<"copy" | "rename" | "reports" | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reports, setReports] = useState<KitReport[]>([]);
  const [reportId, setReportId] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const profile = state?.active_profile;
  // The top-bar kit menu is on every screen; the legacy bar only on the rack and setup screens.
  const visible = variant === "menu" || location.pathname.startsWith("/setup/") || location.pathname === "/simple";
  useEffect(() => {
    const onOpen = (event: Event) => { setMenuOpen(false); openRef.current((event as CustomEvent<KitDialogMode>).detail); };
    window.addEventListener(KIT_DIALOG_EVENT, onOpen);
    return () => window.removeEventListener(KIT_DIALOG_EVENT, onOpen);
  }, []);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: MouseEvent) => { if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false); };
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") setMenuOpen(false); };
    document.addEventListener("mousedown", close); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", key); };
  }, [menuOpen]);
  const openRef = useRef<(next: KitDialogMode) => void>(() => {});
  useEffect(() => {
    if (new URLSearchParams(location.search).get("report") === "1") setMode("reports");
  }, [location.search]);
  useEffect(() => {
    if (mode && visible) dialog.current?.showModal();
    else dialog.current?.close();
  }, [mode, visible, profile?.id]);
  useEffect(() => {
    if (mode !== "reports" || !profile) return;
    let active = true;
    setBusy(true); setReports([]); setReportId("");
    api.kitReports(profile.id).then(rows => { if (active) { setReports(rows); setReportId(rows[0]?.id || ""); } })
      .catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [mode, profile?.id]);
  if (!visible || !profile || !state) return null;
  const selectedReport = reports.find(report => report.id === reportId);
  const options = [...state.profiles, ...(state.profiles.some(p => p.id === profile.id) ? [] : [profile])];
  openRef.current = next => { if (next === "rename" && profile.id === "runtime") return; open(next); };
  function open(next: typeof mode) { setError(""); setNotice(""); setName(next === "copy" ? `${profile!.name} copy` : profile!.name); setMode(next); }
  async function loadKit(id: string) {
    if (id === profile!.id || !window.confirm("Open this kit? Save any unfinished form entries first. Unsaved entries on this page will be lost.")) return;
    setBusy(true); setError("");
    try { await api.activateLabProfile(id); window.location.assign("/setup/guide"); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); setBusy(false); }
  }
  /** Build it again: a new kit from a recipe file (design only; passwords and addresses asked again). */
  async function startFromRecipe(file: File) {
    setBusy(true); setError("");
    try {
      const recipe = JSON.parse(await file.text());
      const name = `${String(recipe?.name || "Kit")} (rebuild ${new Date().toLocaleDateString()})`;
      const result = await jobsApi.applyRecipe(name, recipe);
      await api.activateLabProfile(result.kit.id);
      window.alert(`New kit "${result.kit.name}" is ready.\n\nStill to do:\n- ${result.todo.join("\n- ")}`);
      window.location.assign("/setup/guide");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); setBusy(false); }
  }
  async function saveName() {
    setBusy(true); setError("");
    try {
      if (mode === "copy") { await api.saveKitAs(profile!.id, name.trim()); setNotice(`Saved "${name.trim()}". Select it from Kit to open it. The current kit is unchanged.`); }
      else { await api.renameKit(profile!.id, name.trim()); setNotice("Kit name saved."); }
      await onReload(); setMode(null);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  async function capture() {
    setBusy(true); setError("");
    try { const report = await api.saveKitReport(profile!.id); setReports(rows => [report, ...rows]); setReportId(report.id); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  const kitDialog = <dialog ref={dialog} className="kit-dialog" onCancel={event => { if (busy) event.preventDefault(); else setMode(null); }} onClose={() => setMode(null)}>
      <header><h2>{mode === "copy" ? "Save as new kit" : mode === "rename" ? "Name this kit" : "Build reports"}</h2><button aria-label="Close" disabled={busy} onClick={() => setMode(null)}><X size={20} /></button></header>
      {mode === "reports" ? <><div className="kit-report-tools"><button disabled={busy} onClick={() => void capture()}><Save size={16} />Save report snapshot</button><button disabled={!selectedReport || busy} onClick={() => { const title = document.title; document.title = `${selectedReport!.name} - Build report`; window.print(); document.title = title; }}><Printer size={16} />Print / PDF</button><label>Saved report<select value={reportId} onChange={e => setReportId(e.target.value)} disabled={busy || !reports.length}>{reports.map(report => <option key={report.id} value={report.id}>{new Date(report.captured_at).toLocaleString()}</option>)}</select></label></div>
        {busy && <p role="status">Loading...</p>}{!busy && !reports.length && <p>No reports saved for this kit yet.</p>}
        {selectedReport && <article className="kit-report"><h1>{selectedReport.name}</h1><p>Build report snapshot · {new Date(selectedReport.captured_at).toLocaleString()}</p><p>Kit reference: {selectedReport.profile_id} · Rack revision {selectedReport.rack_revision}</p><p className="kit-report-warning">{selectedReport.limitations}</p><h2>Equipment and observed versions</h2>{selectedReport.equipment.map((item, i) => <section key={item.device_id || i}><h3>U{item.position} · {item.name}</h3><p>{item.model || "Model unspecified"} (planned) · {item.host || "No address saved"}</p><p>Connection: {item.connection} {item.checked_at ? `· ${new Date(item.checked_at).toLocaleString()}` : ""}</p>{item.versions.map((v, index) => <p key={index}>{v.component}: {v.version}</p>)}{item.firmware_assessment && <><h4>SPP comparison</h4><p>{item.firmware_assessment.reason}</p><FirmwareAssessmentTable result={item.firmware_assessment}/><p>{item.firmware_assessment.limitations}</p></>}</section>)}<h2>Recorded activity</h2>{!selectedReport.activity.length && <p>No linked activity recorded.</p>}{selectedReport.activity.map(event => <p key={event.id}>{new Date(event.at).toLocaleString()} · {event.action} · {event.from_status || ""}{event.from_status ? " → " : ""}{event.to_status || "Recorded; not hardware verification"}</p>)}</article>}</> : <form onSubmit={event => { event.preventDefault(); void saveName(); }}><label>Kit name<input autoFocus required minLength={2} maxLength={120} value={name} disabled={busy} onChange={event => setName(event.target.value)} /></label>{mode === "copy" && <p>Copies the last saved rack layout and shared network settings. Save unfinished edits first. Device addresses, credentials, checks and build history are not copied. The original stays open.</p>}<button disabled={busy} type="submit"><Save size={16} />{busy ? "Saving..." : "Save"}</button></form>}
      {error && <p role="alert">{error}</p>}
    </dialog>;
  if (variant === "menu") return <div className="sd-kit" ref={menuRef}>
    <button type="button" className="sd-kit-btn" aria-expanded={menuOpen} aria-haspopup="true" onClick={() => setMenuOpen(value => !value)} title="Kit: open, rename, save as, reports and appearance">
      <span><small>Kit</small><b>{profile.name}</b></span>
      <svg className="sd-ic sd-ic-s" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 6.5L8 10l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </button>
    {menuOpen && <div className="sd-menu" aria-label="Kit menu">
      <label className="sd-menu-field">Open a saved kit<select aria-label="Kit" value={profile.id} disabled={busy} onChange={event => { setMenuOpen(false); void loadKit(event.target.value); }}>{options.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <hr />
      <button type="button" disabled={busy || profile.id === "runtime"} onClick={() => { setMenuOpen(false); open("rename"); }}><Pencil size={14} />Rename</button>
      <button type="button" disabled={busy} onClick={() => { setMenuOpen(false); open("copy"); }}><Copy size={14} />Save as new kit</button>
      <button type="button" disabled={busy} onClick={() => { setMenuOpen(false); open("reports"); }}><FileText size={14} />Build reports</button>
      <label className="sd-menu-file"><FolderOpen size={14} />Start a kit from a recipe…<input type="file" accept=".json,application/json" disabled={busy} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; setMenuOpen(false); if (file) void startFromRecipe(file); }} /></label>
      <hr />
      <div className="sd-menu-label">Settings · appearance</div>
      <div className="sd-theme-row"><span>Theme</span><span className="sd-seg" role="group" aria-label="Theme"><button type="button" aria-pressed={theme === "light"} onClick={() => setTheme("light")}>Light</button><button type="button" aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}>Dark</button></span></div>
    </div>}
    {notice && !menuOpen && <p className="sd-kit-note" role="status">{notice}</p>}{error && !mode && !menuOpen && <p className="sd-kit-note" role="alert">{error}</p>}
    {kitDialog}
  </div>;
  return <section className="kit-library" aria-label="Saved kits">
    <label><FolderOpen size={18} />Kit<select aria-label="Kit" value={profile.id} disabled={busy} onChange={event => void loadKit(event.target.value)}>{options.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <div className="kit-library-actions"><button type="button" disabled={busy || profile.id === "runtime"} title="Rename kit" onClick={() => open("rename")}><Pencil size={16} /><span>Rename</span></button><button type="button" disabled={busy} onClick={() => open("copy")}><Copy size={16} />Save as new kit</button><button type="button" disabled={busy} onClick={() => open("reports")}><FileText size={16} />Build reports</button></div>
    {notice && <p role="status">{notice}</p>}{error && !mode && <p role="alert">{error}</p>}
    {kitDialog}
  </section>;
}
