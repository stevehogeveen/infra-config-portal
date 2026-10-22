import { WriteScopePill } from "./WriteScope";
import { JobBell } from "../KitJobs";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useStudio } from "./StudioContext";
import { openIssueReporter, openKitDialog } from "./studioEvents";
import { useTheme } from "./theme";

const icons = {
  search: <svg className="sd-ic" viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M10.4 10.4L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>,
  doc: <svg className="sd-ic sd-ic-s" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 1.8h5.2L12 4.6v9.6H4z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" /><path d="M6 8h4M6 10.6h4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>,
  clock: <svg className="sd-ic sd-ic-s" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M8 4.8V8l2.2 1.4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>,
  flag: <svg className="sd-ic sd-ic-s" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 14V2.5M3.5 3h8l-1.6 3 1.6 3h-8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" /></svg>,
  moon: <svg className="sd-ic" viewBox="0 0 16 16" aria-hidden="true"><path d="M13 9.6A5.5 5.5 0 016.4 3a5.5 5.5 0 106.6 6.6z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>,
  sun: <svg className="sd-ic" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="3" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>,
  dots: <svg className="sd-ic" viewBox="0 0 16 16" aria-hidden="true"><circle cx="3.5" cy="8" r="1.4" fill="currentColor" /><circle cx="8" cy="8" r="1.4" fill="currentColor" /><circle cx="12.5" cy="8" r="1.4" fill="currentColor" /></svg>,
};

export function BrandMark() {
  return <svg viewBox="0 0 30 30" aria-hidden="true"><defs><linearGradient id="sd-brand-grad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#1F6FA3" /><stop offset="1" stopColor="#0A3150" /></linearGradient></defs><rect x="1" y="1" width="28" height="28" rx="8" fill="url(#sd-brand-grad)" /><rect x="8" y="7.5" width="14" height="3.6" rx="1" fill="#fff" opacity=".95" /><rect x="8" y="13.2" width="14" height="3.6" rx="1" fill="#fff" opacity=".7" /><rect x="8" y="18.9" width="14" height="3.6" rx="1" fill="#fff" opacity=".45" /><circle cx="19.6" cy="9.3" r="1.25" fill="#F26B24" /></svg>;
}

export function ThemeButton() {
  const [theme, setTheme] = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return <button type="button" className="sd-icon-btn" onClick={() => setTheme(next)} aria-label={`Use the ${next} theme`} title={`Appearance: ${theme}. Switch to ${next}.`}>{theme === "dark" ? icons.sun : icons.moon}</button>;
}

export function StudioTopBar({ kitMenu }: { kitMenu?: ReactNode }) {
  const studio = useStudio();
  const location = useLocation();
  const navigate = useNavigate();
  const [more, setMore] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);
  useEffect(() => { setMore(false); }, [location.pathname]);
  useEffect(() => {
    if (!more) return;
    const close = (event: MouseEvent) => { if (!moreRef.current?.contains(event.target as Node)) setMore(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [more]);
  const onRack = location.pathname === "/simple";
  return <header className="sd-top workbench-topbar">
    <Link className="sd-brand workbench-brand" to="/simple"><BrandMark /><span>Lab Builder</span></Link>
    <nav className="sd-mainnav" aria-label="Main navigation">
      <Link className={onRack ? "active" : ""} aria-current={onRack ? "page" : undefined} to="/simple">My Rack</Link>
      <Link className={!onRack ? "active" : ""} aria-current={!onRack ? "page" : undefined} to="/setup/guide">Setup</Link>
    </nav>
    {kitMenu}
    <span className="sd-grow" />
    {studio && <button type="button" className="sd-cmdk" onClick={() => studio.setPaletteOpen(true)} aria-label="Search or run a command">{icons.search}<span>Search or run…</span><kbd>Ctrl K</kbd></button>}
    <span className="sd-sep" aria-hidden="true" />
    <button type="button" className="sd-install" title="The whole build, installer style" onClick={() => navigate("/install")}>Build my kit</button>
    <button type="button" className="sd-lnk" aria-label="Build reports" title="Build reports" onClick={() => openKitDialog("reports")}>{icons.doc}<span className="l">Build reports</span></button>
    <button type="button" className="sd-lnk" aria-label="Run history" title="Run history" onClick={() => navigate("/setup/history")}>{icons.clock}<span className="l">Run history</span></button>
    <button type="button" className="sd-lnk" aria-label="Report an issue" title="Report an issue" onClick={openIssueReporter}>{icons.flag}<span className="l">Report an issue</span></button>
    <div className="sd-more-wrap" ref={moreRef}>
      <button type="button" className="sd-icon-btn" aria-label="More: build reports, run history, report an issue" aria-expanded={more} aria-haspopup="true" onClick={() => setMore(value => !value)}>{icons.dots}</button>
      {more && <div className="sd-menu sd-menu-right" role="menu">
        <button type="button" role="menuitem" onClick={() => { setMore(false); openKitDialog("reports"); }}>{icons.doc}Build reports</button>
        <button type="button" role="menuitem" onClick={() => { setMore(false); navigate("/setup/history"); }}>{icons.clock}Run history</button>
        <button type="button" role="menuitem" onClick={() => { setMore(false); navigate("/handover"); }}>{icons.doc}Hand-over pack</button>
        <button type="button" role="menuitem" onClick={() => { setMore(false); navigate("/labels"); }}>{icons.doc}Print equipment labels</button>
        <button type="button" role="menuitem" onClick={() => { setMore(false); navigate("/ask"); }}>{icons.search}Ask the lab</button>
        <button type="button" role="menuitem" onClick={() => { setMore(false); navigate("/contract"); }}>{icons.doc}Kit contract</button>
        <button type="button" role="menuitem" onClick={() => { setMore(false); navigate("/trace"); }}>{icons.doc}Trace the path</button>
        <button type="button" role="menuitem" onClick={() => { setMore(false); navigate("/rehearsal"); }}>{icons.clock}Practice run (rehearsal rack)</button>
        <button type="button" role="menuitem" onClick={() => { setMore(false); navigate("/reset"); }}>{icons.flag}Reset for the next person</button>
        <button type="button" role="menuitem" onClick={() => { setMore(false); openIssueReporter(); }}>{icons.flag}Report an issue</button>
      </div>}
    </div>
    <JobBell />
    <WriteScopePill />
    <ThemeButton />
  </header>;
}
