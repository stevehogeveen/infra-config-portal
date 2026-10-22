import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { RackPlan } from "./RackPlanner";
import { FirmwarePackageSource } from "./FirmwarePackageSource";
import { FirmwareOverview } from "./FirmwareOverview";
import type { FirmwarePackageSource as PackageSource } from "../api";
import { Guide, GuideActionProvider, useGuideActions } from "./studio/Guide";
import { ArrowRight } from "lucide-react";
import { computeSteps } from "./studio/StudioRail";
import { useStudio } from "./studio/StudioContext";

export function RackFirmwareReview({ profileId }: { profileId?: string }) {
  const [plan, setPlan] = useState<RackPlan | null>(null);
  const [error, setError] = useState("");
  const [source, setSource] = useState<PackageSource|null>(null);
  const [changing, setChanging] = useState(false);
  const actions = useGuideActions();
  useEffect(() => {
    let active = true;
    setPlan(null); setError("");
    if (!profileId) return;
    api.rackPlan(profileId).then(value => { if (active) setPlan(value); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : String(err)); });
    return () => { active = false; };
  }, [profileId]);
  const servers = plan?.equipment.filter(item => item.kind === "server" && /hpe|proliant|dl360|dl380/i.test(item.model)) ?? [];
  const others = plan?.equipment.filter(item => item.kind === "switch" && /cisco|catalyst/i.test(item.model) || item.kind === "storage" && /netapp/i.test(item.model)) ?? [];
  const selected = source?.selected;
  // The package picker stays mounted: it loads the saved selection for every server card.
  const showPicker = changing || (source !== null && !selected);
  const firmwareDone = computeSteps(useStudio())[3]?.state === "done";
  return <GuideActionProvider value={actions.value}><section className="rack-firmware-review fw-page">
    <Guide eyebrow={<><b>Step 4 of 7</b></>}
      say={firmwareDone ? "Firmware is up to date." : "Check each server, then update the firmware."}
      reassure="Checking only reads. Updating asks for one confirmation, then installs and reads every part back."
      primary={firmwareDone ? <Link className="sd-primary" to={"/setup/disks" + window.location.search}>Next: Disks &amp; RAID<ArrowRight size={17} /></Link> : undefined}
      actionRef={actions.ref} />
    <header className="journey-heading"><h1>Check firmware</h1><p>What's installed, and what your package can take it to.</p></header>
    {error && <p role="alert">Could not load this rack. {error}</p>}
    {!profileId ? <p>Select a kit to review firmware.</p> : !plan && !error ? <p role="status">Loading rack equipment...</p> : null}
    {plan && !servers.length && !others.length && <p>No supported firmware-check hardware in this rack. <Link to="/setup/guide">Review equipment</Link></p>}
    {profileId && servers.length > 0 && <>
      <div className="fw-bar">
        <span>Package: <b>{selected ? (selected.release_hint ? `HPE SPP ${selected.release_hint}` : selected.file_name) : source ? "none chosen" : "reading…"}</b></span>
        {selected && !source?.selection_current && <span className="sd-chip sd-chip-warn sd-chip-xs">missing or changed</span>}
        {selected && <button type="button" className="fw-link" aria-expanded={changing} onClick={() => setChanging(open => !open)}>{changing ? "Done" : "Change"}</button>}
      </div>
      <div hidden={!showPicker}><FirmwarePackageSource key={profileId} profileId={profileId} onChange={next => { setSource(next); if (next?.selected && next.selection_current) setChanging(false); }} /></div>
    </>}
    {profileId && servers.map(item => item.device_id
      ? <FirmwareOverview key={`${item.device_id}:${selected?.modified_ns}`} profileId={profileId} deviceId={item.device_id} deviceName={item.name} model={item.model}
          packageName={selected?.file_name} packageCurrent={source?.selection_current} />
      : <section className="fw-card fw-other" key={item.id} aria-label={item.name}><p><b>{item.name}</b> · {item.model}. Save it and set up its connection first. <Link to={`/setup/connect?device=${encodeURIComponent(item.id)}`}>Open connection settings</Link></p></section>)}
    {others.map(item => <section className="fw-card fw-other" key={item.id} aria-label={item.name}>
      <p><b>{item.name}</b> · {item.model}. Firmware check not available in the app yet.</p></section>)}
  </section></GuideActionProvider>;
}
