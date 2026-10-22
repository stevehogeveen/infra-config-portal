import { useEffect, useId, useState } from "react";
import { Cable, PlugZap, RefreshCw, Terminal } from "lucide-react";
import { GuidePrimary } from "./studio/Guide";
import { shortTime } from "./studio/ProvenanceChip";
import { requestStudioRefresh } from "./studio/StudioContext";
import { SwitchFirstSetup } from "./SwitchSetup";
import { switchApi, type SwitchAccess, type SwitchCheck, type SwitchConsolePorts, type SwitchConsoleRead } from "../api";

/** A switch on the Connect step. A new switch has no address yet, so the console cable comes
 * first: pick this PC's COM port and read the switch through it. The address and SSH sign-in
 * follow once the switch has been set up. */
export function RackSwitchAccess({ profileId, deviceName, deviceId, plannedPorts, onChecked, onConsole, onBusyChange, hoistSubmit = false }: { profileId: string; deviceName: string; deviceId: string; plannedPorts?: number; onChecked?: (check: SwitchCheck | null) => void; onConsole?: (read: SwitchConsoleRead | null) => void; onBusyChange?: (busy: boolean) => void; hoistSubmit?: boolean }) {
  const [consoleRead, setConsoleRead] = useState<SwitchConsoleRead | null>(null);
  const [consoleBusy, setConsoleBusy] = useState(false);
  const [signInBusy, setSignInBusy] = useState(false);
  const [signInRevision, setSignInRevision] = useState(0);
  useEffect(() => { onBusyChange?.(consoleBusy || signInBusy); }, [consoleBusy, signInBusy, onBusyChange]);
  const answered = !!consoleRead?.answered;
  return <div className="sw-steps">
    <section className="sw-step" aria-label="Console cable">
      <header><span className="sw-num">1</span><div><h3>Console cable</h3><p>A new switch is set up through its console cable. Pick the COM port the cable is plugged into.</p></div></header>
      <SwitchConsole deviceId={deviceId} hoist={hoistSubmit && !answered} onBusyChange={setConsoleBusy} onRead={read => { setConsoleRead(read); onConsole?.(read); }} />
    </section>
    <section className="sw-step" aria-label="First setup">
      <header><span className="sw-num">2</span><div><h3>First setup</h3><p>Name, admin sign-in, management address and SSH, sent over the console cable.</p></div></header>
      <SwitchFirstSetup profileId={profileId} deviceId={deviceId} deviceName={deviceName} consoleRead={consoleRead} hoist={hoistSubmit && answered} onVerified={() => { setSignInRevision(value => value + 1); requestStudioRefresh(); }} />
    </section>
    <section className="sw-step" aria-label="Management address">
      <header><span className="sw-num">3</span><div><h3>Check over the network</h3><p>Signs in over SSH at the management address. Already-set-up switches can start here.</p></div></header>
      <SwitchSignIn key={signInRevision} deviceId={deviceId} plannedPorts={plannedPorts} onChecked={onChecked} onBusyChange={setSignInBusy} />
    </section>
  </div>;
}

function SwitchConsole({ deviceId, hoist, onBusyChange, onRead }: { deviceId: string; hoist: boolean; onBusyChange: (busy: boolean) => void; onRead: (read: SwitchConsoleRead | null) => void }) {
  const [ports, setPorts] = useState<SwitchConsolePorts | null>(null);
  const [port, setPort] = useState("");
  const [baud, setBaud] = useState(9600);
  const [read, setRead] = useState<SwitchConsoleRead | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => onBusyChange(busy), [busy]);
  async function load() {
    setError("");
    try {
      const [listed, access] = await Promise.all([switchApi.consolePorts(deviceId), switchApi.read(deviceId)]);
      setPorts(listed);
      const last = access.console?.last ?? null;
      setRead(last); onRead(last);
      const preferred = listed.ports.find(item => item.port === (listed.saved_port || last?.port)) ?? listed.ports.find(item => item.recommended) ?? (listed.ports.length === 1 ? listed.ports[0] : undefined);
      setPort(current => current && listed.ports.some(item => item.port === current) ? current : preferred?.port ?? "");
      if (listed.saved_baud) setBaud(listed.saved_baud);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }
  useEffect(() => { setPorts(null); void load(); }, [deviceId]);
  const chosen = ports?.ports.find(item => item.port === port);
  const button = <button type="button" className="rack-plan-save" disabled={busy || !chosen} onClick={async () => {
    if (!chosen) return;
    setBusy(true); setError("");
    try { const next = await switchApi.identify(deviceId, { port: chosen.port, baud, candidate_fingerprint: chosen.candidate_fingerprint }); setRead(next); onRead(next); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }}><Terminal size={16} />{busy ? "Reading the switch…" : read?.answered && read.port === port ? "Read the switch again" : "Read the switch"}</button>;
  if (!ports) return <p role="status">{error || "Looking for COM ports on this PC…"}</p>;
  return <div className="workbench-access sw-console">
    {ports.problem && <p className="sd-proof-note" role="note">{ports.problem}</p>}
    {ports.ports.length > 0 && <div className="ex-ports">
      <small>COM ports on this PC</small>
      <div role="radiogroup" aria-label="COM port">
        {ports.ports.map(item => <button key={item.port} type="button" role="radio" aria-checked={item.port === port} disabled={busy}
          className={item.usb ? "linked" : ""} aria-label={`${item.port}, ${item.description}${item.recommended ? ", likely the console cable" : ""}`} onClick={() => setPort(item.port)}>
          {item.usb ? <Cable size={16} aria-hidden="true" /> : <Terminal size={16} aria-hidden="true" />}
          <b>{item.port}</b>
          <span>{item.recommended ? "Likely the console cable" : item.hint}</span>
          <em>{item.description}</em>
        </button>)}
      </div>
    </div>}
    <div className="sw-console-row">
      <label><span className="input-label">Speed <small>Cisco default 9600</small></span><select aria-label="Console speed" value={baud} disabled={busy} onChange={e => setBaud(Number(e.target.value))}>{(ports.bauds ?? [9600, 115200]).map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      <button type="button" className="connection-secondary" disabled={busy} onClick={() => void load()}><RefreshCw size={15} />Refresh ports</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {button}
    <p>Read-only: sends one Enter to wake the prompt, then reads the model and software. It never answers setup questions or changes settings.</p>
    {read && <section aria-label="Console result" aria-live="polite">
      <h3>{read.identity_verified ? "The switch answered" : read.answered ? "A switch is on this cable" : "No answer"}</h3>
      {read.state_text && <p>{read.state_text}</p>}
      {!read.answered && <p role="alert">{read.message}</p>}
      <p>{read.port} at {read.baud} · {new Date(read.checked_at).toLocaleString()}</p>
      {read.identity_verified && <dl>{read.model && <div><dt>Model</dt><dd>{read.model}</dd></div>}{read.version && <div><dt>Software</dt><dd>{read.version}</dd></div>}</dl>}
    </section>}
  </div>;
}

function SwitchSignIn({ deviceId, plannedPorts, onChecked, onBusyChange, hoistSubmit = false }: { deviceId: string; plannedPorts?: number; onChecked?: (check: SwitchCheck | null) => void; onBusyChange?: (busy: boolean) => void; hoistSubmit?: boolean }) {
  const formId = useId();
  const [access, setAccess] = useState<SwitchAccess | null>(null);
  const [host, setHost] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [enablePassword, setEnablePassword] = useState("");
  const [replacePassword, setReplacePassword] = useState(false);
  const [check, setCheck] = useState<SwitchCheck | null>(null);
  const [reading, setReading] = useState(false);
  const [found, setFound] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { onBusyChange?.(busy); return () => onBusyChange?.(false); }, [busy, onBusyChange]);
  useEffect(() => {
    let cancelled = false;
    switchApi.read(deviceId).then(value => {
      if (cancelled) return;
      setAccess(value); setHost(value.host || ""); setUsername(value.username || ""); setCheck(value.last_check); onChecked?.(value.last_check);
    }).catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : String(err)); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [deviceId]);
  const saved = !!access?.username_configured && !!access.password_configured;
  const edited = !!access && (host.trim() !== (access.host || "") || username.trim() !== (access.username || "") || !!password || !!enablePassword);
  const submit = <button className="rack-plan-save" type="submit" form={formId} disabled={busy || !access}><PlugZap size={16} />{busy ? "Working..." : saved && !edited ? (access?.host ? "Check connection" : "Saved") : access?.host || host.trim() ? "Save and check connection" : "Save sign-in"}</button>;
  return <form id={formId} className="workbench-access" onSubmit={async event => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      let current = access;
      if (edited || !saved) {
        // With DHCP there is no address to type: the sign-in is saved on its own, and the address arrives from the first setup.
        const next = await switchApi.save(deviceId, { ...(host.trim() ? { host: host.trim() } : {}), ...(username.trim() ? { username: username.trim() } : {}), ...(password ? { password } : {}), ...(enablePassword ? { enable_password: enablePassword } : {}) });
        setAccess(next); setHost(next.host || ""); setUsername(next.username || ""); setPassword(""); setEnablePassword(""); setReplacePassword(false);
        current = next;
      }
      if (!current?.host) { setFound("Sign-in saved. The switch has no address yet: with DHCP it gets one during the first setup (step 2), which reads it over the console; or press Find switch address."); return; }
      setCheck(null); onChecked?.(null);
      const result = await switchApi.check(deviceId);
      requestStudioRefresh();
      setCheck(result); onChecked?.(result);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }}>
    {edited && check && <p className="sd-proof-note" role="note">The last answer ({shortTime(check.checked_at)}) was for the saved details. It does not prove these edited details; save and check again.</p>}
    <p>The address the switch answers SSH on, usually its management VLAN address. With DHCP, use Find switch address instead of typing it.</p>
    <div className="sw-console-row">
      <button type="button" className="connection-secondary" disabled={busy || !access || reading} onClick={async () => {
        setReading(true); setError(""); setFound(null);
        try {
          const result = await switchApi.address(deviceId);
          setFound(result.message);
          if (result.address) { setHost(result.address); setAccess(current => current ? { ...current, host: result.address } : current); }
        } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
        finally { setReading(false); }
      }}><Terminal size={15} />{reading ? "Reading over the console…" : "Find switch address"}</button>
    </div>
    {found && <p role="status">{found}</p>}
    <label><span className="input-label">Switch address <small>{access?.host ? "From the first setup; change if needed" : "Not yet: DHCP gives it during the first setup"}</small></span><input aria-label="Switch address" disabled={busy || !access} value={host} onChange={e => setHost(e.target.value)} placeholder="Leave empty with DHCP" /></label>
    <label><span className="input-label">Username <small>{access?.username_configured ? "Saved; change if needed" : "Required"}</small></span><input aria-label="Switch username" required={!access?.username_configured} disabled={busy || !access} value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" /></label>
    {access?.password_configured && !replacePassword
      ? <div><p>Passwords saved securely{access.enable_password_configured ? " (sign-in and enable)" : ""}</p><button type="button" className="connection-secondary" disabled={busy} onClick={() => setReplacePassword(true)}>Change passwords</button></div>
      : <>
        <label><span className="input-label">Password <small>{access?.password_configured ? "Replacement" : "Required"}</small></span><input aria-label="Switch password" type="password" required={!access?.password_configured} disabled={busy || !access} value={password} onChange={e => setPassword(e.target.value)} placeholder={access?.password_configured ? "Leave blank to keep saved password" : "Password"} autoComplete="new-password" /></label>
        <label><span className="input-label">Enable password <small>Optional</small></span><input aria-label="Enable password" type="password" disabled={busy || !access} value={enablePassword} onChange={e => setEnablePassword(e.target.value)} placeholder={access?.enable_password_configured ? "Leave blank to keep saved password" : "Only if the switch asks for one"} autoComplete="new-password" /></label>
      </>}
    {error && <p role="alert">{error}</p>}
    {hoistSubmit ? <GuidePrimary>{submit}</GuidePrimary> : submit}
    <p>Read-only: signs in over SSH and reads the switch's model, software and ports. Nothing on the switch changes.</p>
    {check && <SwitchResult check={check} plannedPorts={plannedPorts} />}
  </form>;
}

function SwitchResult({ check, plannedPorts }: { check: SwitchCheck; plannedPorts?: number }) {
  const ok = check.status === "ok";
  const rows: [string, string | number | null][] = [["Name", check.hostname], ["Model", check.model], ["Software", check.version], ["Serial number", check.serial], ["Ports", check.port_count], ["Up for", check.uptime]];
  return <section aria-label="Connection check result" aria-live="polite">
    <h3>{ok ? "The switch answered" : check.status === "sign_in_failed" ? "Sign-in refused" : check.status === "unreachable" ? "No answer" : "Check stopped"}</h3>
    <p role={ok ? undefined : "alert"}>{check.message}</p>
    {check.checked_at && <p>{new Date(check.checked_at).toLocaleString()}</p>}
    {ok && <dl>{rows.filter(([, value]) => value !== null && value !== undefined).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>}
    {ok && plannedPorts && check.port_count && check.port_count < plannedPorts ? <p role="note">The rack plan has {plannedPorts} ports, but the switch reported {check.port_count}.</p> : null}
  </section>;
}
