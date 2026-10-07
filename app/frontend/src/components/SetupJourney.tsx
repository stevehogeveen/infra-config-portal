import { useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowLeft, ArrowRight, Circle, ShieldCheck, SlidersHorizontal } from "lucide-react";
import "../setupJourney.css";
import { StudioFrame } from "./studio/StudioFrame";
import { GuideBanner } from "./studio/Guide";
import { computeSteps, studioSteps } from "./studio/StudioRail";
import { useStudio } from "./studio/StudioContext";

export const setupSteps = studioSteps;

/*
 * Journey step numbers: 0 equipment, 1 connect, 2 firmware, 3 disks & RAID, 4 ESXi, 5 Windows.
 * Network settings ("defaults") sits at rail index 1, so numbered steps above 0 shift by one.
 */
type JourneyStep = number | "defaults" | "history";

function viewingIndex(step: JourneyStep) {
  return step === "history" ? -1 : step === "defaults" ? 1 : step === 0 ? 0 : step + 1;
}

export function stepEyebrow(index: number, extra?: ReactNode) {
  return <>Your guide · <b>Step {index + 1} of {setupSteps.length}</b> · {setupSteps[index].name}{extra}</>;
}

function nextPrimary(activeStep: number, query: string, done: boolean): ReactNode {
  if (!done) return undefined;
  if (activeStep >= setupSteps.length - 1) return <Link className="sd-primary" to="/simple?report=1">Review build report<ArrowRight size={17} /></Link>;
  const next = setupSteps[activeStep + 1];
  const label: Record<string, string> = { "/setup/disks": "Continue to disks & RAID", "/setup/prepare-esxi": "Continue to ESXi", "/setup/install-windows": "Continue to Windows" };
  return <Link className="sd-primary" to={next.path + query}>{label[next.path] ?? `Continue to ${next.name.toLowerCase()}`}<ArrowRight size={17} /></Link>;
}

function defaultGuide(activeStep: number, query: string, done = false): ReactNode {
  if (activeStep < 0) return <GuideBanner eyebrow={<>Your guide · <b>Run history</b></>}
    say="Run history lists every read and every confirmed write for this kit, newest first."
    reassure="Looking at history reads records only. Nothing is sent to hardware." />;
  switch (activeStep) {
    case 1: return <GuideBanner eyebrow={stepEyebrow(1)}
      say={<>Check the shared network settings, save them in your plan, then carry on to connecting the equipment.</>}
      reassure="Saving writes your plan only. Nothing on the network is changed."
      primary={<Link className="sd-primary" to={"/setup/connect" + query}>Continue to connections<ArrowRight size={17} /></Link>} />;
    case 3: return <GuideBanner eyebrow={stepEyebrow(3)}
      say={done ? <>Every server's firmware update is verified. Carry on to the disks and RAID.</> : <>Compare each server with the selected HPE firmware package, then update it with one button.</>}
      reassure="Checking only reads. Updating asks for one confirmation, then installs and reads every part back."
      primary={nextPrimary(3, query, done)} aside={done ? undefined : "Choose the package and run the comparison below."} />;
    case 4: return <GuideBanner eyebrow={stepEyebrow(4)}
      say={done ? <>The RAID is built as planned on every server. Carry on to installing ESXi.</> : <>Look at each server's drive bays: what's in them now and what your plan will make them. Follow the one button on each server.</>}
      reassure="Reading disks changes nothing. Erasing and building RAID each show what happens and need your click."
      primary={nextPrimary(4, query, done)} aside={done ? undefined : "Erased disks? The re-enable guide walks you through it."} />;
    case 5: return <GuideBanner eyebrow={stepEyebrow(5)}
      say={done ? <>ESXi is installed and verified. Carry on to deploying Windows.</> : <>Install ESXi in three steps: choose the installer ISO, set the host name and address, then install. The app does the rest and watches until ESXi answers.</>}
      reassure="Steps 1 and 2 only save your plan. Installing asks for one confirmation, then attaches, boots and checks by itself."
      primary={nextPrimary(5, query, done)} aside={done ? undefined : "ESXi installs onto the RAID 1 boot mirror."} />;
    case 6: return <GuideBanner eyebrow={stepEyebrow(6)}
      say={done ? <>Windows is running. Your kit is built; the build report lists every verified step.</> : <>Deploy Windows in three steps: choose the OVA or OVF, name the VM, then deploy. The app imports it onto ESXi, starts it and waits until Windows reports its address.</>}
      reassure="Steps 1 and 2 only save your plan. Deploying asks for one confirmation; nothing else on the server changes."
      primary={nextPrimary(6, query, done)} aside={done ? undefined : "Needs ESXi installed and verified (Prepare ESXi) and VMware Tools in the image."} />;
    default: return <GuideBanner eyebrow={stepEyebrow(Math.max(0, activeStep))} say={setupSteps[Math.max(0, activeStep)].detail + "."} />;
  }
}

export function SetupJourney({ step, children }: { step: JourneyStep; children: ReactNode }) {
  const location = useLocation();
  const device = new URLSearchParams(location.search).get("device");
  const query = device ? `?device=${encodeURIComponent(device)}` : "";
  const activeStep = viewingIndex(step);
  const studio = useStudio();
  const done = activeStep >= 0 && computeSteps(studio)[activeStep]?.state === "done";
  const next = activeStep >= 0 && activeStep < setupSteps.length - 1 ? setupSteps[activeStep + 1] : null;
  return <StudioFrame viewing={activeStep >= 0 ? activeStep : null} defaultGuide={defaultGuide(activeStep, query, done)}>
    <div className="setup-body sd-setup-body">{children}
      <footer className="setup-footer">{activeStep > 0 ? <Link to={setupSteps[activeStep - 1].path + query}><ArrowLeft size={16} />{setupSteps[activeStep - 1].name}</Link> : <Link to="/simple"><ArrowLeft size={16} />My Rack</Link>}
        <span>Hardware changes require review and approval</span>
        {next && <Link className="setup-footer-next" to={next.path + query}>Next: {next.name}<ArrowRight size={16} /></Link>}</footer>
    </div>
  </StudioFrame>;
}

/** My Rack sits in the same frame: rail, guide slot and evidence drawer. */
export function RackHomeFrame({ children }: { children: ReactNode }) {
  return <StudioFrame viewing={null}>{children}</StudioFrame>;
}

const reviews: Record<number, { title: string; subtitle: string; prerequisites: string; rows: string[]; tools: string; next: string }> = {
  2: { title: "Check firmware", subtitle: "Review the whole kit before installing anything.", prerequisites: "Start with working equipment connections. Inventory alone does not confirm firmware compatibility.", rows: ["iLO and server firmware", "Switch firmware", "ESXi version and hardware compatibility"], tools: "Firmware review tools", next: "Continue to disks & RAID" },
  4: { title: "Prepare ESXi", subtitle: "Get the server ready to receive your Windows virtual machine.", prerequisites: "Firmware approval and network readiness must be verified before installation. Reserve exactly two drives for the ESXi boot mirror.", rows: ["Switch, DNS, NTP and management network", "Two-drive boot mirror", "ESXi installation and management access", "VM datastore and port group"], tools: "Server preparation tools", next: "Preview Windows setup" },
  5: { title: "Install Windows", subtitle: "Deploy your Windows OVF or OVA onto the prepared server.", prerequisites: "Verify ESXi, available datastore space and the VM network before deployment. vCenter is optional for this kit.", rows: ["Windows OVF or OVA package", "Target ESXi server and datastore", "VM network and deployment settings", "Power-on and Windows verification"], tools: "Windows deployment tools", next: "View activity" },
};

export function SetupReview({ step, children }: { step: 2 | 4 | 5; children: ReactNode }) {
  const [toolsOpen, setToolsOpen] = useState(step === 5);
  const data = reviews[step];
  const location = useLocation();
  // Forward links stay available but quiet: the guide banner carries the one primary.
  if (step === 2) return <SetupJourney step={step}>{children}</SetupJourney>;
  if (step === 4) return <SetupJourney step={step}><header className="journey-heading"><h1>Prepare ESXi</h1><p>Configure the host network and prepare the ESXi installer.</p></header>{children}</SetupJourney>;
  return <SetupJourney step={step}><header className="journey-heading"><h1>{data.title}</h1><p>{data.subtitle}</p></header>
    <div className="journey-warning"><ShieldCheck size={23} /><div><strong>Readiness not yet confirmed</strong><p>{data.prerequisites}</p></div></div>
    <details className="journey-prerequisites"><summary>Prerequisites <span>{data.rows.length} unverified</span></summary>
      <div className="journey-checks">{data.rows.map((row, index) => <div key={row}><span className="review-number">{index + 1}</span><strong>{row}</strong><span><Circle size={13} />Needs verification</span></div>)}</div>
      <p className="journey-evidence-note">Completion has not been verified for this kit.</p>
    </details>
    <details className="journey-tools" open={toolsOpen} onToggle={event => setToolsOpen(event.currentTarget.open)}><summary><SlidersHorizontal size={18} />{data.tools}</summary>{toolsOpen && <div>{children}</div>}</details>
    <div className="journey-next journey-preview"><Link to="/simple?report=1">Review build report<ArrowRight size={17} /></Link></div>
  </SetupJourney>;
}
