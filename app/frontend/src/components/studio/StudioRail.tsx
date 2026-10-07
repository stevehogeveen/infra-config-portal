import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useStudio, type DeviceEvidence, type StudioData } from "./StudioContext";
import { shortTime } from "./ProvenanceChip";

export const studioSteps = [
  { path: "/setup/guide", name: "Add equipment", detail: "Choose hardware and rack positions" },
  { path: "/setup/defaults", name: "Network settings", detail: "Shared DNS, NTP and management network" },
  { path: "/setup/connect", name: "Connect equipment", detail: "First contact and a read of each server" },
  { path: "/setup/check-firmware", name: "Check firmware", detail: "Compare versions, then upgrade" },
  { path: "/setup/disks", name: "Disks & RAID", detail: "See every bay, clear old data, build RAID" },
  { path: "/setup/prepare-esxi", name: "Prepare ESXi", detail: "Host settings and installation" },
  { path: "/setup/install-windows", name: "Install Windows", detail: "Deploy your OVF or OVA" },
];

export type StepState = "done" | "now" | "next" | "lock" | "open" | "unassessed";

/** Storage status per saved server. A failed or pending read is unknown, never "none". */
export function storageSummary(data: StudioData | null) {
  const servers = data?.devices.filter(item => item.kind === "server" && item.deviceId) ?? [];
  let active = 0, unknown = 0, unresolved = 0, createVerified = 0;
  for (const item of servers) {
    const read = item.storageRead;
    if (!read || read.state !== "ok") { unknown++; continue; }
    if (read.status.operation === "create" && read.status.status === "verified" && !read.status.active) createVerified++;
    if (read.status.active) active++;
    else if (["staged", "waiting", "uncertain", "needs_attention", "failed"].includes(read.status.status)) unresolved++;
  }
  return { servers: servers.length, active, unknown, unresolved, createVerified };
}
export type RailStep = { path: string; name: string; state: StepState; note: string };

/*
 * Step status comes only from saved data and recorded evidence. "Done" on a planning step
 * means saved in the plan (never proof, never green). Firmware, ESXi and Windows are done when every
 * server has a recorded, verified run; otherwise they say "not assessed here" rather than guessing
 * a blocker, and their pages stay open because planning there is allowed and every apply is guarded.
 */
export function computeSteps(data: StudioData | null): RailStep[] {
  if (!data || !data.plan) return studioSteps.map(step => ({ path: step.path, name: step.name, state: "open", note: step.detail }));
  const pieces = data.plan.equipment.length;
  const servers = data.devices.filter(item => item.kind === "server" && item.deviceId);
  const answered = servers.filter(item => item.proven).length;
  const s1: StepState = data.planSaved && !data.draftPending ? "done" : "open";
  const s1note = !pieces ? "Add your first piece" : data.draftPending ? "Draft not saved yet" : data.planSaved ? `Done · saved plan · ${pieces} piece${pieces === 1 ? "" : "s"}` : "Save the rack layout";
  const s2: StepState = data.networkSaved ? "done" : "open";
  const s2note = data.networkSaved ? "Done · saved plan" : "Not saved yet";
  // Connect is done when every saved server has answered. Disks & RAID is one step: it reports
  // recorded storage activity and is done only with recorded evidence of a
  // verified RAID create on every server (the backend's readback matched the reviewed layout).
  const storage = storageSummary(data);
  const connected = servers.length > 0 && answered === servers.length;
  const raidVerified = servers.length > 0 && storage.createVerified === servers.length;
  const s3: StepState = connected ? "done" : "open";
  const answeredText = `${answered} of ${servers.length} server${servers.length === 1 ? "" : "s"} answered`;
  const s3note = !servers.length ? "No saved server yet" : connected ? `Done · ${answeredText}` : answeredText;
  const storageNote = raidVerified ? "Done · RAID create verified (recorded)"
    : !servers.length ? "No saved server yet" : storage.unknown ? "storage status unknown"
    : storage.active ? "storage operation in progress" : storage.unresolved ? "storage needs attention"
    : storage.createVerified ? `${storage.createVerified} of ${servers.length} verified (recorded)` : "Not built yet";
  // Firmware, ESXi and Windows are done only with a recorded, verified run on every server.
  const all = (key: "firmware" | "esxi" | "windows") => servers.length > 0 && servers.every(item => item.milestones?.[key]);
  const firmwareDone = all("firmware"), esxiDone = all("esxi"), windowsDone = all("windows");
  const states: StepState[] = [s1, s2, s3, firmwareDone ? "done" : "open", raidVerified ? "done" : "unassessed",
    esxiDone ? "done" : "unassessed", windowsDone ? "done" : "unassessed"];
  const notes = [s1note, s2note, s3note,
    firmwareDone ? "Done · firmware update verified (recorded)" : "Not assessed here · open the page to compare",
    storageNote,
    esxiDone ? "Done · ESXi installed and verified (recorded)" : "Readiness not assessed here · page open",
    windowsDone ? "Done · Windows running (recorded)" : "Readiness not assessed here · page open"];
  // "Not assessed" never holds the build back: firmware review does not wait for disks or RAID.
  const current = states.findIndex((state, index) => index < 4 && state !== "done" && state !== "unassessed");
  if (current >= 0) {
    states[current] = "now";
    if (current + 1 < 4 && states[current + 1] === "open") states[current + 1] = "next";
  }
  return studioSteps.map((step, index) => ({ path: step.path, name: step.name, state: states[index], note: states[index] === "now" ? `Now · ${notes[index]}` : notes[index] }));
}

function Dot({ state, index }: { state: StepState; index: number }) {
  if (state === "done") return <span className="sd-dot"><svg className="sd-ic sd-ic-s" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg></span>;
  if (state === "lock") return <span className="sd-dot"><svg className="sd-ic sd-ic-s" viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="7" width="9" height="6.5" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M5.5 7V5.3a2.5 2.5 0 015 0V7" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg></span>;
  return <span className="sd-dot">{index + 1}</span>;
}

function deviceLight(item: DeviceEvidence) {
  if (item.accessUnavailable) return { led: "", time: "unknown", tone: "" };
  if (item.proven) return { led: "ok", time: shortTime(item.answeredAt), tone: "ok" };
  if (item.attention === "failed") return { led: "bad", time: "failed", tone: "bad" };
  if (item.attention === "stale") return { led: "", time: "stale", tone: "" };
  if (item.kind !== "server") return { led: "", time: "no check", tone: "" };
  return { led: "", time: item.deviceId ? "never" : "draft", tone: "" };
}

export function StudioRail({ viewing }: { viewing: number | null }) {
  const studio = useStudio();
  const location = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  useEffect(() => { setOpen(false); }, [location.pathname, location.search]);
  const steps = computeSteps(studio);
  const query = new URLSearchParams(location.search).get("device");
  const suffix = query ? `?device=${encodeURIComponent(query)}` : "";
  const nowIndex = steps.findIndex(step => step.state === "now");
  const servers = studio?.devices.filter(item => item.kind === "server" && item.deviceId) ?? [];
  const answered = servers.filter(item => item.proven).length;
  const storage = storageSummary(studio);
  const storageText = !studio ? "" : studio.loading ? "reading…"
    : storage.unknown ? `status unknown for ${storage.unknown} server${storage.unknown === 1 ? "" : "s"}`
    : storage.active ? `${storage.active} active`
    : storage.unresolved ? `${storage.unresolved} need attention`
    : storage.servers ? "none active (recorded)" : "no saved server";
  const summaryStep = nowIndex >= 0 ? nowIndex : viewing ?? 0;
  return <nav className={`sd-rail ${open ? "open" : ""}`} aria-label="Build steps and equipment">
    <button type="button" className="sd-rail-sum" aria-expanded={open} onClick={() => setOpen(value => !value)}>
      <span className="sd-dot">{summaryStep + 1}</span>
      <span><b>{steps.every(step => step.state === "done") && viewing === null ? `All ${steps.length} steps done · kit built` : `Step ${summaryStep + 1} of ${steps.length} · ${steps[summaryStep].name}`}</b><small>{viewing !== null && viewing !== summaryStep ? `Viewing ${steps[viewing].name}` : steps[summaryStep].note}{servers.length ? ` · ${answered} of ${servers.length} answered` : ""}</small></span>
      <svg className="sd-ic sd-ic-s" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 6.5L8 10l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </button>
    <div className="sd-rail-group">
      <h4>Build steps</h4>
      <ol className="sd-steps">
        {steps.map((step, index) => <li key={step.path}>
          <Link to={step.path + suffix} className={`sd-st ${step.state} ${viewing === index ? "viewing" : ""}`} aria-current={viewing === index ? "step" : undefined}
            title={step.state === "unassessed" ? "The rail cannot read this step's readiness. The page stays open; every change there is previewed and confirmed separately." : undefined}>
            <Dot state={step.state} index={index} />
            <span><b>{step.name}</b>{" "}<small>{viewing === index ? `Viewing · ${step.note}` : step.note}</small>
              {index === 2 && servers.length > 0 && <span className="sd-lights" aria-label={`${answered} of ${servers.length} answered`}>{servers.map(item => <i key={item.id} className={item.proven ? "ok" : item.attention === "failed" ? "bad" : ""} />)}</span>}
            </span>
          </Link>
        </li>)}
      </ol>
    </div>
    {studio && studio.devices.length > 0 && <div className="sd-rail-group">
      <h4>Equipment · last answer</h4>
      <ul className="sd-devs">
        {studio.devices.map(item => {
          const light = deviceLight(item);
          return <li key={item.id}><button type="button" className={studio.selectedId === item.id ? "cur" : undefined} aria-pressed={studio.selectedId === item.id}
            onClick={() => { studio.select(item.id); navigate(`${location.pathname}?device=${encodeURIComponent(item.deviceId || item.id)}`, { replace: true }); }}>
            <span className={`sd-led ${light.led}`} aria-hidden="true" /><span className="sd-dev-name">{item.name}</span><time className={light.tone}>{light.time}</time>
          </button></li>;
        })}
      </ul>
    </div>}
    <div className="sd-rail-foot">
      {studio && <div className="row"><span>Storage operations</span><b>{storageText}</b></div>}
      <div className="row"><span>Hardware changes</span><b>preview, then confirm</b></div>
      <div className="sd-keys"><span><kbd>Ctrl K</kbd>commands</span></div>
    </div>
  </nav>;
}
