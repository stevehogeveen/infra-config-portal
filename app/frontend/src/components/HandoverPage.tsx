import { useEffect, useState } from "react";
import { Download, Printer } from "lucide-react";
import { jobsApi, type Handover } from "../api";
import { useStudio } from "./studio/StudioContext";
import { size } from "./bays";

const when = (value?: string | null) => value ? new Date(value).toLocaleString() : "—";
const dash = (value?: string | number | null) => value === null || value === undefined || value === "" ? "—" : String(value);

/** One printable page for the kit's next owner: addresses, versions, disks, cables and proof. No passwords. */
export function HandoverPage({ profileId: given }: { profileId?: string } = {}) {
  const studio = useStudio();
  const profileId = given ?? studio?.profileId;
  const [data, setData] = useState<Handover | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!profileId) return;
    jobsApi.handover(profileId).then(setData).catch(err => setError(err instanceof Error ? err.message : String(err)));
  }, [profileId]);
  async function downloadRecipe() {
    if (!profileId) return;
    const recipe = await jobsApi.recipe(profileId);
    const blob = new Blob([JSON.stringify(recipe, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${(data?.kit || "kit").replace(/[^A-Za-z0-9-]+/g, "-")}.labrecipe.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  }
  if (error) return <p role="alert">{error}</p>;
  if (!data) return <p role="status">Gathering the hand-over pack…</p>;
  return <article className="handover">
    <header className="handover-head">
      <div><h1>Hand-over pack</h1><p>{data.kit} · prepared {when(data.generated_at)}</p></div>
      <div className="handover-actions">
        <button type="button" className="secondary-action" onClick={() => void downloadRecipe()}><Download size={16} />Recipe to rebuild this kit</button>
        <button type="button" className="primary-action" onClick={() => window.print()}><Printer size={16} />Print</button>
      </div>
    </header>
    <p className="handover-note">From the app's records only. Passwords are not included; hand them over separately.</p>

    <section><h2>Network</h2>
      <dl className="ho-grid"><div><dt>Subnet</dt><dd>{dash(data.network.subnet)}</dd></div><div><dt>Gateway</dt><dd>{dash(data.network.gateway)}</dd></div>
        <div><dt>DNS</dt><dd>{(data.network.dns || []).join(", ") || "—"}</dd></div><div><dt>Domain</dt><dd>{dash(data.network.domain)}</dd></div></dl></section>

    {data.servers.map(server => <section key={server.name}><h2>{server.name} <small>{server.model}{server.observed_at ? ` · read ${when(server.observed_at)}` : " · saved plan"}</small></h2>
      <dl className="ho-grid">
        <div><dt>iLO</dt><dd>{dash(server.ilo.address)}</dd></div>
        <div><dt>iLO firmware</dt><dd>{dash(server.ilo.firmware)}</dd></div>
        <div><dt>System ROM</dt><dd>{dash(server.ilo.bios)}</dd></div>
        <div><dt>Last check</dt><dd>{when(server.ilo.checked_at)}</dd></div>
        <div><dt>Health</dt><dd>{server.health ? `${server.health.problems.length ? server.health.problems.join("; ") : `OK · fans ${server.health.fans_ok}/${server.health.fans} · power ${server.health.psu_ok}/${server.health.psus}`} (read ${when(server.health.checked_at)})` : "—"}</dd></div>
        <div><dt>Boot disks</dt><dd>{server.boot_disks ? `${server.boot_disks.bays.length} × · ${size(server.boot_disks.capacity_bytes)} · bays ${server.boot_disks.bays.join(", ")}` : "—"}</dd></div>
        <div><dt>VM storage</dt><dd>{server.data_disks ? `${dash(server.data_disks.raid)} · ${size(server.data_disks.capacity_bytes)} · bays ${server.data_disks.bays.join(", ")}` : "—"}</dd></div>
        <div><dt>ESXi</dt><dd>{dash(server.esxi.host_name)} · {dash(server.esxi.address)}{server.esxi.datastore?.name ? ` · datastore ${server.esxi.datastore.name}` : ""}</dd></div>
        <div><dt>ESXi verified</dt><dd>{server.esxi.state === "verified" ? when(server.esxi.verified_at) : dash(server.esxi.state)}</dd></div>
        <div><dt>Windows VM</dt><dd>{server.windows.state === "verified" ? `${dash(server.windows.vm)} · ${dash(server.windows.address)} · ${dash(server.windows.os)}` : dash(server.windows.state)}</dd></div>
        <div><dt>Windows verified</dt><dd>{when(server.windows.verified_at)}</dd></div>
        <div><dt>Acceptance test</dt><dd>{server.acceptance?.state === "verified" ? `Passed ${when(server.acceptance.finished_at)}` : server.acceptance?.state === "failed" ? "Failed" : server.acceptance?.state === "needs_attention" ? "Needs attention" : "Not run"}</dd></div>
      </dl></section>)}

    {data.switches.map(sw => <section key={sw.name}><h2>{sw.name} <small>{sw.model}</small></h2>
      <dl className="ho-grid">
        <div><dt>Management address</dt><dd>{dash(sw.address)}</dd></div>
        <div><dt>Admin user</dt><dd>{dash(sw.username)}</dd></div>
        <div><dt>Software</dt><dd>{dash(sw.software)}</dd></div>
        <div><dt>Serial</dt><dd>{dash(sw.serial)}</dd></div>
        <div><dt>Console</dt><dd>{dash(sw.console)}</dd></div>
        <div><dt>Last check</dt><dd>{sw.checked_at ? `${when(sw.checked_at)} · ${sw.check_status === "ok" ? "answered" : "did not answer"}` : "—"}</dd></div>
      </dl>
      {sw.config?.after && <details className="ho-config"><summary>Configuration as read after the first setup ({when(sw.config.at)}; secrets masked) · {sw.config.diff.filter(l => /^[+-][^+-]/.test(l)).length} lines changed</summary>
        {sw.config.diff.length > 2 && <pre className="ho-diff" aria-label="What the setup changed">{sw.config.diff.slice(2).join("\n")}</pre>}
        <pre className="ho-pre" aria-label="Running configuration">{sw.config.after}</pre></details>}
      </section>)}

    <section><h2>Cables</h2>
      {data.cables?.cables?.length ? <ul className="ho-list">{data.cables.cables.map(cable => <li key={cable.mac}>{cable.server} {cable.server_port} → {cable.switch} {cable.switch_port} · VLAN {cable.vlan}</li>)}</ul>
        : <p className="ho-muted">Not read yet (My Rack → Cables → Read cables).</p>}</section>

    <section><h2>Verified</h2>
      {data.verified.length ? <ul className="ho-list">{data.verified.map(row => <li key={row.id}><b>{row.area}</b> · {when(row.at)} · {row.message}</li>)}</ul>
        : <p className="ho-muted">Nothing verified yet.</p>}</section>
  </article>;
}
