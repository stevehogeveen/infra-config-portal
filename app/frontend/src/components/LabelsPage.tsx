import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { Printer, ScanLine } from "lucide-react";
import { jobsApi, switchApi } from "../api";
import { useStudio } from "./studio/StudioContext";

type Label = { id: string; name: string; kind: string; model: string; address: string | null; addressLabel: string; serial: string | null; serialReadAt: string | null };

/** One printable label per device: name, model, management address, serial and a QR code with the same. */
export function LabelsPage() {
  const studio = useStudio();
  const [labels, setLabels] = useState<Label[]>([]);
  const [codes, setCodes] = useState<Record<string, string>>({});
  const [reading, setReading] = useState(false);
  const [note, setNote] = useState("");
  useEffect(() => {
    let active = true;
    const devices = (studio?.devices ?? []).filter(item => item.deviceId && (item.kind === "server" || item.kind === "switch" || item.kind === "storage"));
    Promise.all(devices.map(async item => {
      let address = item.access?.host ?? null;
      if (item.kind === "switch") { try { address = (await switchApi.read(item.deviceId!)).host; } catch { address = null; } }
      return { id: item.deviceId!, name: item.name, kind: item.kind, model: item.model || (item.kind === "switch" ? "Cisco switch" : "Server"),
        address, addressLabel: item.kind === "server" ? "iLO" : "Mgmt", serial: null, serialReadAt: null } as Label;
    })).then(next => { if (active) setLabels(current => next.map(label => { const old = current.find(item => item.id === label.id); return { ...label, serial: old?.serial ?? null, serialReadAt: old?.serialReadAt ?? null }; })); });
    return () => { active = false; };
  }, [studio?.devices]);
  useEffect(() => {
    let active = true;
    Promise.all(labels.map(async label => [label.id, await QRCode.toDataURL(qrText(label, studio?.profileName ?? ""), { margin: 1, width: 220 })] as const))
      .then(rows => { if (active) setCodes(Object.fromEntries(rows)); });
    return () => { active = false; };
  }, [labels, studio?.profileName]);
  async function readSerials() {
    setReading(true); setNote("");
    const servers = labels.filter(label => label.kind === "server");
    const results = await Promise.all(servers.map(async label => {
      try { return [label.id, (await jobsApi.identity(label.id)).serial] as const; } catch { return [label.id, null] as const; }
    }));
    // A failed read clears the serial: a label never prints a number this read did not see.
    const readAt = new Date().toISOString();
    setLabels(current => current.map(label => {
      const result = results.find(([id]) => id === label.id);
      return result ? { ...label, serial: result[1], serialReadAt: result[1] ? readAt : null } : label;
    }));
    const missing = results.filter(([, serial]) => !serial).length;
    setNote(missing ? `${missing} server${missing === 1 ? "" : "s"} did not answer; their labels have no serial.` : "Serial numbers read from the iLO.");
    setReading(false);
  }
  return <section className="labels-page">
    <header className="labels-head">
      <div><h1>Equipment labels</h1><p>{studio?.profileName}</p></div>
      <div className="labels-actions">
        <button type="button" className="secondary-action" disabled={reading || !labels.some(label => label.kind === "server")} onClick={() => void readSerials()}><ScanLine size={16} />{reading ? "Reading…" : "Read serial numbers"}</button>
        <button type="button" className="primary-action" onClick={() => window.print()}><Printer size={16} />Print labels</button>
      </div>
    </header>
    {note && <p role="status" className="labels-note">{note}</p>}
    {!labels.length ? <p>No saved servers or switches in this kit yet.</p>
      : <div className="label-sheet">{labels.map(label => <article key={label.id} className="equip-label" aria-label={`Label for ${label.name}`}>
        {codes[label.id] && <img src={codes[label.id]} alt="" />}
        <div>
          <strong>{label.name}</strong>
          <span>{label.model}</span>
          <span>{label.addressLabel} {label.address ?? "—"} <em>(saved)</em></span>
          <span>S/N {label.serial ?? "—"}{label.serialReadAt ? <em> (read {new Date(label.serialReadAt).toLocaleDateString()})</em> : null}</span>
          <small>{studio?.profileName}</small>
        </div>
      </article>)}</div>}
  </section>;
}

function qrText(label: Label, kit: string) {
  return [`Lab Builder: ${label.name}`, label.model, `${label.addressLabel} ${label.address ?? "-"} (saved)`,
    `S/N ${label.serial ?? "-"}${label.serialReadAt ? ` (read from iLO ${label.serialReadAt.slice(0, 10)})` : ""}`, kit && `Kit ${kit}`].filter(Boolean).join("\n");
}
