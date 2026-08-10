import { useState, type FormEvent } from "react";

import { api } from "../api";
import type { DeviceInventoryItem, DeviceInventoryWrite } from "../types";

export function DeviceInventoryForm({
  device,
  onClose,
  onReload,
  onSaved,
  submitLabel
}: {
  device?: DeviceInventoryItem;
  onClose: () => void;
  onReload: () => Promise<void> | void;
  onSaved?: (device: DeviceInventoryItem) => void;
  submitLabel?: string;
}) {
  const [form, setForm] = useState<DeviceInventoryWrite>({
    device_type: device?.device_type ?? "other",
    display_name: device?.display_name ?? "",
    host: device?.host ?? "",
    dhcp_enabled: device?.dhcp_enabled ?? false,
    notes: device?.notes ?? ""
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = form.dhcp_enabled ? { ...form, host: undefined } : form;
      const saved = device
        ? await api.updateDevice(device.id, payload)
        : await api.createDevice(payload);
      await onReload();
      onSaved?.(saved);
      onClose();
    } catch (err) {
      setError(deviceInventoryError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="topology-workspace-overlay" aria-label={device ? "Edit device" : "Add device"}>
      <div className="topology-workspace-backdrop" onClick={onClose} />
      <aside className="topology-workspace-drawer">
        <div className="topology-workspace-drawer-head">
          <span>{device ? "Edit rack device" : "Add device to rack"}</span>
          <button onClick={onClose} type="button">Close</button>
        </div>
        <form className="map-editor-form" onSubmit={save}>
          <label>
            <span>Equipment type</span>
            <input aria-label="Device type" list="device-inventory-types" onChange={(event) => setForm({ ...form, device_type: event.target.value })} required value={form.device_type} />
          </label>
          <datalist id="device-inventory-types">
            <option value="ilo" />
            <option value="cisco_switch" />
            <option value="esxi_host" />
            <option value="netapp" />
            <option value="vcenter" />
            <option value="server" />
            <option value="other" />
          </datalist>
          <label>
            <span>Display name</span>
            <input aria-label="Device name" onChange={(event) => setForm({ ...form, display_name: event.target.value })} required value={form.display_name} />
          </label>
          <label>
            <span>Addressing</span>
            <select aria-label="Device addressing mode" onChange={(event) => setForm({ ...form, dhcp_enabled: event.target.value === "dhcp" })} value={form.dhcp_enabled ? "dhcp" : "static"}>
              <option value="static">Static</option>
              <option value="dhcp">DHCP</option>
            </select>
          </label>
          <label>
            <span>{form.dhcp_enabled ? "Observed address" : "Host or management IP (optional)"}</span>
            <input
              aria-label="Device host"
              disabled={form.dhcp_enabled}
              onChange={(event) => setForm({ ...form, host: event.target.value })}
              placeholder={form.dhcp_enabled ? "No address observed yet" : "IP address or hostname"}
              value={form.host ?? ""}
            />
            {form.dhcp_enabled && <small className="from-device-hint">Assigned by the network, not editable.</small>}
          </label>
          <label>
            <span>Rack notes (optional)</span>
            <textarea aria-label="Device notes" onChange={(event) => setForm({ ...form, notes: event.target.value })} value={form.notes ?? ""} />
          </label>
          {error && <div className="operator-feedback error">{error}</div>}
          <p className="muted">Inventory only. Saving places this device in the rack; it does not contact or change hardware.</p>
          <button className="operator-primary-button" disabled={busy} type="submit">{busy ? "Saving" : submitLabel ?? "Save device"}</button>
        </form>
      </aside>
    </div>
  );
}

function deviceInventoryError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
