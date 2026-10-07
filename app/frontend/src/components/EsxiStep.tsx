import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AlertTriangle, Cable, Check, Disc3, ExternalLink, HardDrive, KeyRound, Network, Rocket, Server, Unplug } from "lucide-react";
import { api, type EsxiInstallerBuild, type EsxiInstallStatus, type EsxiMedia, type EsxiNetworkPort, type EsxiNetworkPorts, type EsxiSettings } from "../api";
import type { LabProfile, LabProfileList as LabProfileState } from "../types";
import type { RackPlan } from "./RackPlanner";
import { MediaDropZone } from "./MediaDropZone";
import { EsxiInstaller } from "./EsxiInstaller";
import { size } from "./bays";
import { saveEsxiManagementAddress } from "../operatorPages";

/*
 * Prepare ESXi: three steps per server, in order. 1 choose the installer ISO (or add one),
 * 2 save the host settings (name, address, VLAN, root password), 3 install. Steps 1 and 2 save
 * the plan only; step 3 opens the installer, which is the only thing that touches the server.
 */

type ServerRow = { name: string; model: string; deviceId: string };

function activeProfile(state: LabProfileState | null | undefined): LabProfile | null {
  return state?.active_profile ?? null;
}

function Step({ n, title, done, icon, children, summary, keepOpen = false }: { n: number; title: string; done: boolean; icon: ReactNode; children: ReactNode; summary?: ReactNode; keepOpen?: boolean }) {
  const [open, setOpen] = useState(!done || keepOpen);
  useEffect(() => { if (!done || keepOpen) setOpen(true); }, [done, keepOpen]);
  const folded = done && !keepOpen && !open;
  return <section className={`ex-step ${done ? "is-done" : ""} ${folded ? "is-folded" : ""}`} aria-label={title}>
    <header><span className="ex-num">{done ? <Check size={15} aria-hidden="true" /> : n}</span><span className="ex-icon" aria-hidden="true">{icon}</span>
      <div><h2>{title}</h2>{summary && <p>{summary}</p>}</div>
      {done && !keepOpen && <button type="button" className="ex-change" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? "Done" : "Change"}</button>}</header>
    {!folded && <div className="ex-body">{children}</div>}
  </section>;
}

function MediaStep({ profileId, deviceId, media, onChanged }: { profileId: string; deviceId: string; media: EsxiMedia | null; onChanged: (next: EsxiMedia) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const choose = async (path: string) => {
    setBusy(true); setError("");
    try { onChanged(await api.chooseEsxiMedia(profileId, deviceId, path)); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  };
  const selected = media?.selected;
  return <>
    {media && !media.isos.length && <p className="ex-hint">No ESXi installer ISO is in the media folder yet. Add one below; HPE's custom ESXi image is recommended for ProLiant servers.</p>}
    {!!media?.isos.length && <div className="ex-isos" role="radiogroup" aria-label="ESXi installer ISO">
      {media.isos.map(iso => {
        const active = selected?.path === iso.path;
        return <button key={iso.path} type="button" role="radio" aria-checked={active} className={`ex-iso ${active ? "is-on" : ""}`} disabled={busy || uploading} onClick={() => void choose(iso.path)}>
          <Disc3 size={22} aria-hidden="true" />
          <span><strong>{iso.version ? `ESXi ${iso.version}` : iso.name}</strong><small>{iso.name}</small></span>
          <span className="ex-iso-meta">{size(iso.size_bytes)}{iso.hpe_image && <b>HPE image</b>}</span>
          {active && <Check className="ex-iso-check" size={18} aria-hidden="true" />}
        </button>;
      })}
    </div>}
    {selected && !selected.present && <p className="fw-stop" role="alert">The chosen ISO ({selected.name}) is no longer in the media folder. Choose another or add it again.</p>}
    <details className="ex-add" open={!!media && !media.isos.length}>
      <summary>Add an ESXi ISO</summary>
      <MediaDropZone profileId={profileId} folder="" disabled={busy} onUploading={setUploading}
        onUploaded={async () => { onChanged(await api.esxiMedia(profileId, deviceId)); }} />
    </details>
    {error && <p className="fw-stop" role="alert">{error}</p>}
  </>;
}

// "Embedded LOM" -> "Built-in", "NIC.Slot.3.1" -> "Slot 3": what the back of the server says.
function portPlace(port: EsxiNetworkPort) {
  const slot = /Slot\.?\s*(\d+)/i.exec(port.location);
  if (slot) return `Slot ${slot[1]}`;
  if (/lom|embedded/i.test(port.location)) return "Built-in";
  if (/ocp|flexlom|flr/i.test(port.location)) return "FlexibleLOM";
  return port.location || "Adapter";
}
function speed(mbps: number | null) { return !mbps ? "" : mbps >= 1000 ? ` · ${mbps / 1000} Gb` : ` · ${mbps} Mb`; }
const matches = (port: EsxiNetworkPort, nic: string) => port.mac === nic.toLowerCase() || port.vmnic === nic;

function PortPicker({ ports, value, busy, onChange }: { ports: EsxiNetworkPorts | null; value: string; busy: boolean; onChange: (next: string) => void }) {
  if (!ports) return <p className="ex-hint" role="status">Reading the server's network ports from the iLO…</p>;
  if (!ports.available || !ports.ports.length) return <>
    <p className="ex-hint">{ports.message || "The iLO listed no network ports."} Type the ESXi name of the port instead.</p>
    <input aria-label="Management network card" className="ex-nic" value={value} disabled={busy} onChange={e => onChange(e.target.value)} />
  </>;
  const groups = new Map<string, EsxiNetworkPort[]>();
  for (const port of ports.ports) groups.set(`${portPlace(port)} · ${port.adapter}`, [...(groups.get(`${portPlace(port)} · ${port.adapter}`) ?? []), port]);
  const chosen = ports.ports.find(port => matches(port, value));
  return <>
    {[...groups].sort(([a], [b]) => Number(b.startsWith("Built-in")) - Number(a.startsWith("Built-in"))).map(([group, list]) => <div key={group} className="ex-ports">
      <small>{group}</small>
      <div role="radiogroup" aria-label={`Ports on ${group}`}>
        {list.map(port => <button key={port.mac} type="button" role="radio" aria-checked={chosen?.mac === port.mac} disabled={busy}
          className={port.link ? "linked" : ""} aria-label={`${portPlace(port)} port ${port.port}, ${port.link ? "cable connected" : "no cable"}${port.vmnic ? `, ${port.vmnic}` : ""}`}
          onClick={() => onChange(port.mac)}>
          {port.link ? <Cable size={16} aria-hidden="true" /> : <Unplug size={16} aria-hidden="true" />}
          <b>Port {port.port}</b>
          <span>{port.link ? `Cable${speed(port.speed_mbps)}` : "No cable"}</span>
          <em>{port.vmnic ?? port.mac}</em>
        </button>)}
      </div>
    </div>)}
    {!chosen && <p className="fw-stop" role="alert">Saved as {value}, which the iLO doesn't list. Choose the port with a cable.</p>}
    {chosen && !chosen.link && <p className="fw-stop" role="alert"><AlertTriangle size={15} aria-hidden="true" /> {portPlace(chosen)} port {chosen.port} has no cable, so ESXi won't be reachable on it{ports.ports.some(port => port.link) ? " — choose a port marked Cable." : ". The iLO shows link only while the server is on."}</p>}
    {ports.message && <small>{ports.message}</small>}
  </>;
}

function SettingsStep({ profile, profileId, deviceId, settings, onSaved }: { profile: LabProfile; profileId: string; deviceId: string; settings: EsxiSettings; onSaved: (next: EsxiSettings) => Promise<void> }) {
  const domain = settings.kit.domain_name;
  const initialHost = settings.hostname ? (domain && settings.hostname.endsWith("." + domain) ? settings.hostname.slice(0, -(domain.length + 1)) : settings.hostname) : "";
  const [host, setHost] = useState(initialHost);
  const [dhcp, setDhcp] = useState(settings.addressing === "dhcp");
  const [ip, setIp] = useState(settings.management_ip || settings.kit.esxi_management || "");
  const [tagged, setTagged] = useState(settings.vlan_id > 0);
  const [vlan, setVlan] = useState(settings.vlan_id > 0 ? String(settings.vlan_id) : "");
  const [nic, setNic] = useState(settings.management_nic || "");
  const [ports, setPorts] = useState<EsxiNetworkPorts | null>(null);
  useEffect(() => {
    let live = true;
    api.esxiNetworkPorts(profileId, deviceId)
      .then(next => {
        if (!live) return;
        setPorts(next);
        // Nothing saved yet, or a saved name the iLO cannot place: start on the cabled port.
        setNic(current => current && next.ports.some(port => matches(port, current)) ? current : next.suggested ?? (current || "vmnic0"));
      })
      .catch(() => { if (live) { setPorts({ available: false, ports: [], suggested: null, message: "The iLO could not be read." }); setNic(current => current || "vmnic0"); } });
    return () => { live = false; };
  }, [profileId, deviceId]);
  const [datastore, setDatastore] = useState(settings.datastore_name || "VMdata");
  // The app also needs the password itself to sign in after install; ask again if it only has the hash.
  const [changePassword, setChangePassword] = useState(!settings.password_set || !settings.signin_ready);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const fqdn = domain ? `${host.trim().replace(/\.$/, "")}.${domain}` : host.trim();
  const vlanId = tagged ? Number(vlan) : 0;
  const problem = !host.trim() ? "Enter a host name."
    : !domain && host.split(".").length < 2 ? "Enter the full host name, for example esxi01.lab.example."
    : !dhcp && !/^\d{1,3}(\.\d{1,3}){3}$/.test(ip.trim()) ? "Enter the management IP address."
    : tagged && !(Number.isInteger(vlanId) && vlanId >= 1 && vlanId <= 4094) ? "VLAN must be 1-4094."
    : !nic.trim() ? "Choose the network port ESXi is managed through."
    : !/^[A-Za-z0-9][A-Za-z0-9 _.-]{0,41}$/.test(datastore.trim()) ? "Name the datastore with letters, digits, spaces, dots, dashes or underscores (up to 42)."
    : changePassword && password.length < 8 ? "Enter a root password (at least 8 characters)."
    : changePassword && password !== confirm ? "The two passwords don't match."
    : "";
  async function save(event: FormEvent) {
    event.preventDefault();
    if (problem) { setError(problem); return; }
    setBusy(true); setError(""); setSaved("");
    try {
      // The kit keeps the planned address; with DHCP it is cleared so nothing claims a fixed IP.
      const kitAddress = dhcp ? "" : ip.trim();
      if ((settings.kit.esxi_management || "") !== kitAddress) await saveEsxiManagementAddress(profile, kitAddress);
      const next = await api.saveEsxiSettings(profileId, deviceId, { hostname: fqdn, addressing: dhcp ? "dhcp" : "static", management_ip: dhcp ? null : ip.trim(),
        vlan_id: vlanId, management_nic: nic.trim(), datastore_name: datastore.trim(), root_password: changePassword ? password : null });
      setPassword(""); setConfirm(""); setChangePassword(false);
      await onSaved(next);
      setSaved("Saved. Nothing was sent to the server.");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  const kit = settings.kit;
  const data = settings.data_volume;
  return <form className="ex-form" onSubmit={event => void save(event)}>
    <div className="ex-grid">
      <label className="ex-field">Host name
        <span className="ex-joined"><input aria-label="ESXi host name" value={host} disabled={busy} onChange={e => setHost(e.target.value)} placeholder={domain ? "esxi01" : "esxi01.lab.example"} autoComplete="off" />{domain && <span>.{domain}</span>}</span>
      </label>
      <div className="ex-field">Management address
        <div className="ex-seg" role="radiogroup" aria-label="Management addressing">
          <button type="button" role="radio" aria-checked={!dhcp} disabled={busy} onClick={() => setDhcp(false)}>Static IP</button>
          <button type="button" role="radio" aria-checked={dhcp} disabled={busy} onClick={() => setDhcp(true)}>DHCP</button>
        </div>
        {dhcp ? <small>ESXi takes its address from your DHCP server. After install the app finds it through the iLO, or you can type the address the server's screen shows.</small>
          : <><input aria-label="ESXi management IP" value={ip} disabled={busy} onChange={e => setIp(e.target.value)} placeholder={kit.subnet ? `In ${kit.subnet}` : "IPv4 address"} inputMode="decimal" autoComplete="off" />
            <small>Subnet {kit.subnet || "not set"} · gateway {kit.gateway || "not set"}</small></>}
      </div>
      <div className="ex-field">VLAN
        <label className="ex-check"><input type="checkbox" checked={tagged} disabled={busy} onChange={e => setTagged(e.target.checked)} />Tag management traffic with a VLAN</label>
        {tagged ? <input aria-label="Management VLAN ID" value={vlan} disabled={busy} onChange={e => setVlan(e.target.value)} placeholder="1-4094" inputMode="numeric" />
          : <small>Untagged: use this when the switch port is an access port.</small>}
      </div>
      <div className="ex-field">Root password
        {changePassword ? <>
          <input aria-label="ESXi root password" type="password" value={password} disabled={busy} onChange={e => setPassword(e.target.value)} autoComplete="new-password" />
          <input aria-label="Confirm ESXi root password" type="password" value={confirm} disabled={busy} onChange={e => setConfirm(e.target.value)} placeholder="Type it again" autoComplete="new-password" />
          <small>{settings.password_set && !settings.signin_ready ? "Enter it once more so the app can sign in to check the install. " : ""}8+ characters, three of: lowercase, uppercase, digits, symbols. Kept only on this computer (owner-only) to sign in after install; never shown again.</small>
        </> : <span className="ex-saved"><KeyRound size={15} aria-hidden="true" />Saved<button type="button" className="fw-link" onClick={() => setChangePassword(true)}>Change</button></span>}
      </div>
    </div>
    <div className="ex-field ex-portfield">Management network port
      <PortPicker ports={ports} value={nic} busy={busy} onChange={setNic} />
    </div>
    <div className="ex-field ex-ds">VM datastore
      <span className="ex-ds-row"><input aria-label="VM datastore name" value={datastore} disabled={busy} onChange={e => setDatastore(e.target.value)} />
        <small>{data ? <>Created on <b>{data.name}</b> ({data.raid.replace(/^RAID/, "RAID ")}, {size(data.capacity_bytes)}) once ESXi is verified.</> : "No datastore volume is in your RAID plan, so none will be created."}</small></span>
    </div>
    <dl className="ex-facts">
      <div><dt>DNS</dt><dd>{dhcp ? "From DHCP" : kit.dns.join(", ") || "None set"}</dd></div>
      <div><dt>NTP</dt><dd>{kit.ntp_enabled ? kit.ntp.join(", ") || "None set" : "Off"}</dd></div>
      <div><dt>Shared settings</dt><dd><Link to="/setup/defaults">Edit in Network settings</Link></dd></div>
    </dl>
    <div className="ex-actions">
      <button type="submit" className="primary-action" disabled={busy}>{busy ? "Saving…" : "Save host settings"}</button>
      {saved && <span className="inst-ok" role="status"><Check size={15} />{saved}</span>}
    </div>
    {error && <p className="fw-stop" role="alert">{error}</p>}
  </form>;
}

function InstallStep({ settings, build, status, onOpen }: { settings: EsxiSettings; build: EsxiInstallerBuild | null; status: EsxiInstallStatus | null; onOpen: () => void }) {
  const volume = settings.boot_volume;
  if (status?.state === "reachable") return <div className="ex-hint">
    <strong>ESXi answers; verification pending</strong><p>{status.message}</p>
    <button type="button" className="secondary-action" onClick={onOpen}>Review result</button>
    <a className="secondary-action" href={`https://${status.management_ip}/ui/`} target="_blank" rel="noreferrer"><ExternalLink size={15} />Open ESXi</a>
  </div>;
  if (status?.state === "verified") return <div className="ex-done">
    <Check size={22} aria-hidden="true" />
    <div><strong>ESXi is installed and verified</strong><p>Signed in as root: {status.hostname} at {status.management_ip}{status.datastore ? ` · datastore ${status.datastore.name}` : ""}{status.ejected === false ? " · eject the installer in the iLO" : ""}</p></div>
    <a className="secondary-action" href={`https://${status.management_ip}/ui/`} target="_blank" rel="noreferrer"><ExternalLink size={15} />Open ESXi</a>
  </div>;
  const blockers = build?.status === "blocked" ? build.blockers : [];
  return <>
    {volume && <p className="ex-target"><HardDrive size={18} aria-hidden="true" />Installs to <b>{volume.name}</b> (RAID 1, {size(volume.capacity_bytes)}, bays {volume.bays.map(bay => bay.split(":").pop()).join(" & ")}). Anything on it is replaced.</p>}
    {settings.data_volume && <p className="ex-target"><HardDrive size={18} aria-hidden="true" />Then formats <b>{settings.data_volume.name}</b> ({settings.data_volume.raid.replace(/^RAID/, "RAID ")}, {size(settings.data_volume.capacity_bytes)}) as datastore <b>{settings.datastore_name}</b>, after ESXi is verified.</p>}
    {!!blockers.length && <ul className="ex-todo" aria-label="Still to do">{blockers.map(item => <li key={item}>{item}</li>)}</ul>}
    {status?.active && <p className="ex-hint" role="status">{status.message}</p>}
    <div className="ex-actions">
      <button type="button" className="primary-action ex-go" disabled={!!blockers.length} onClick={onOpen}><Rocket size={17} aria-hidden="true" />{status?.active ? "See progress" : "Install ESXi"}</button>
      {!blockers.length && !status?.active && <span className="ex-hint">You'll confirm once; the app then installs, signs in to check the host, and creates the datastore.</span>}
    </div>
  </>;
}

export function EsxiStep({ labProfileState, onReloadLabProfile }: { labProfileState?: LabProfileState | null; onReloadLabProfile?: () => Promise<void> }) {
  const profile = activeProfile(labProfileState);
  const profileId = profile?.id;
  const location = useLocation();
  const navigate = useNavigate();
  const [servers, setServers] = useState<ServerRow[] | null>(null);
  const [media, setMedia] = useState<EsxiMedia | null>(null);
  const [settings, setSettings] = useState<EsxiSettings | null>(null);
  const [build, setBuild] = useState<EsxiInstallerBuild | null>(null);
  const [status, setStatus] = useState<EsxiInstallStatus | null>(null);
  const [error, setError] = useState("");
  const [installer, setInstaller] = useState(false);
  useEffect(() => {
    let active = true;
    setServers(null); setError("");
    if (!profileId) return;
    api.rackPlan(profileId).then((plan: RackPlan) => { if (active) setServers(plan.equipment.filter(item => item.kind === "server" && item.device_id).map(item => ({ name: item.name, model: item.model, deviceId: item.device_id! }))); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : String(err)); });
    return () => { active = false; };
  }, [profileId]);
  const requested = new URLSearchParams(location.search).get("device");
  const server = servers ? (servers.find(item => item.deviceId === requested) ?? servers[0]) : undefined;
  async function load() {
    if (!profileId || !server) return;
    try {
      const [nextMedia, nextSettings, nextBuild, nextStatus] = await Promise.all([api.esxiMedia(profileId, server.deviceId), api.esxiSettings(profileId, server.deviceId), api.esxiInstaller(profileId, server.deviceId), api.esxiInstall(profileId, server.deviceId)]);
      setMedia(nextMedia); setSettings(nextSettings); setBuild(nextBuild); setStatus(nextStatus);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }
  useEffect(() => { setMedia(null); setSettings(null); setBuild(null); setStatus(null); void load(); }, [profileId, server?.deviceId]);

  if (!profileId) return <p>Select a kit first.</p>;
  const mediaDone = !!media?.selected?.present;
  const settingsDone = !!settings?.saved_at && !!settings.password_set && !!settings.signin_ready
    && (settings.addressing === "dhcp" ? !settings.kit.esxi_management : settings.kit.esxi_management === settings.management_ip);
  return <section className="ex-page" aria-label="Prepare ESXi">
    <header className="journey-heading"><h1>Prepare ESXi</h1><p>Choose the installer, set the host's name and address, then install. Steps 1 and 2 only save your plan.</p></header>
    {error && <p className="fw-stop" role="alert">{error}</p>}
    {!servers && !error && <p role="status">Loading servers…</p>}
    {servers && !servers.length && <p>No connected servers in this kit. <Link to="/setup/guide">Add equipment</Link></p>}
    {servers && servers.length > 1 && <label className="ex-server-pick">Server<select aria-label="Server for ESXi" value={server?.deviceId} onChange={e => navigate("/setup/prepare-esxi?device=" + encodeURIComponent(e.target.value))}>{servers.map(item => <option key={item.deviceId} value={item.deviceId}>{item.name}</option>)}</select></label>}
    {server && <article className="ex-card" aria-label={server.name}>
      <header className="ex-card-head"><Server size={20} aria-hidden="true" /><div><strong>{server.name}</strong><small>{server.model}</small></div>
        {status?.state === "verified" && <span className="fw-pill fw-pill-ok">ESXi running</span>}
        {status?.active && <span className="fw-pill fw-pill-up">Installing</span>}</header>
      {!settings ? <p className="dr-loading" role="status">Loading…</p> : <div className="ex-steps">
        <Step n={1} title="Installer media" icon={<Disc3 size={18} />} done={mediaDone}
          summary={media?.selected?.present ? <>Using <b>{media.selected.name}</b></> : "Choose the ESXi ISO to install."}>
          <MediaStep profileId={profileId} deviceId={server.deviceId} media={media} onChanged={next => { setMedia(next); void api.esxiInstaller(profileId, server.deviceId).then(setBuild); }} />
        </Step>
        <Step n={2} title="Host settings" icon={<Network size={18} />} done={settingsDone}
          summary={settingsDone ? <>{settings.hostname} · {settings.addressing === "dhcp" ? "DHCP" : settings.management_ip}{settings.vlan_id ? ` · VLAN ${settings.vlan_id}` : " · untagged"}</> : "Name, management address and root password."}>
          {profile && <SettingsStep key={settings.saved_at ?? "new"} profile={profile} profileId={profileId} deviceId={server.deviceId} settings={settings}
            onSaved={async next => { setSettings(next); await onReloadLabProfile?.(); await load(); }} />}
        </Step>
        <Step n={3} title="Install ESXi" icon={<Rocket size={18} />} done={status?.state === "verified"} keepOpen
          summary={status?.state === "verified" ? "Installed and answering." : "Unattended install onto the boot mirror."}>
          <InstallStep settings={settings} build={build} status={status} onOpen={() => setInstaller(true)} />
        </Step>
      </div>}
    </article>}
    {installer && server && <EsxiInstaller profileId={profileId} deviceId={server.deviceId} deviceName={server.name} settings={settings!}
      onClose={() => { setInstaller(false); void load(); }} />}
  </section>;
}
