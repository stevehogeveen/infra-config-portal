import { useState, type FormEvent } from "react";

import { api } from "../api";
import type { DeviceInventoryItem, DeviceInventoryWrite } from "../types";

export function DeviceInventoryForm({
  device,
  onClose,
  onReload,
  onSaved,
  submitLabel,
  iloOnboarding = false,
  initialIloAccessHost,
  defaultDeviceType,
  initialIloUsername,
  iloCredentialsConfigured = false
}: {
  device?: DeviceInventoryItem;
  onClose: () => void;
  onReload: () => Promise<void> | void;
  onSaved?: (device: DeviceInventoryItem) => void;
  submitLabel?: string;
  iloOnboarding?: boolean;
  initialIloAccessHost?: string | null;
  defaultDeviceType?: string;
  initialIloUsername?: string | null;
  iloCredentialsConfigured?: boolean;
}) {
  const [form, setForm] = useState<DeviceInventoryWrite>({
    device_type: device?.device_type ?? defaultDeviceType ?? "other",
    display_name: device?.display_name ?? "",
    host: device?.host ?? "",
    dhcp_enabled: device?.dhcp_enabled ?? false,
    notes: device?.notes ?? ""
  });
  const [createdDevice, setCreatedDevice] = useState<DeviceInventoryItem | null>(null);
  const [iloUsername, setIloUsername] = useState(device?.device_type === "ilo" ? initialIloUsername ?? "" : "");
  const [iloPassword, setIloPassword] = useState("");
  const [iloVerifyTls, setIloVerifyTls] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isIloFirstContact = iloOnboarding && form.device_type.trim().toLowerCase() === "ilo";
  const isActiveIloTarget = Boolean(
    device?.device_type === "ilo" &&
    device.host?.trim().toLowerCase() &&
    device.host.trim().toLowerCase() === initialIloAccessHost?.trim().toLowerCase()
  );
  const canReuseIloCredentials = isActiveIloTarget && iloCredentialsConfigured;

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const firstContactHost = form.host?.trim() ?? "";
      if (isIloFirstContact && !firstContactHost) {
        setError("Enter the current DHCP address shown for this iLO.");
        return;
      }
      if (isIloFirstContact && !canReuseIloCredentials && !iloUsername.trim()) {
        setError("Enter the iLO username or UID used for first contact.");
        return;
      }
      if (isIloFirstContact && !canReuseIloCredentials && !iloPassword.trim()) {
        setError("Enter the iLO password used for first contact.");
        return;
      }
      const targetDevice = device ?? createdDevice;
      const payload = isIloFirstContact
        ? targetDevice
          ? { ...form, dhcp_enabled: true, host: undefined }
          : { ...form, dhcp_enabled: true, host: firstContactHost }
        : form.dhcp_enabled
          ? { ...form, host: undefined }
          : form;
      const saved = targetDevice
        ? await api.updateDevice(targetDevice.id, payload)
        : await api.createDevice(payload);
      setCreatedDevice(saved);
      if (isIloFirstContact) {
        await api.saveIloAccessSettings({
          host: firstContactHost,
          username: iloUsername.trim() || null,
          password: iloPassword.trim() || null,
          verify_tls: iloVerifyTls
        });
      }
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
          {isIloFirstContact && <div className="ilo-add-flow" aria-label="iLO onboarding steps">
            <div><span className="is-active">1</span><strong>Locate iLO</strong></div>
            <i />
            <div><span>2</span><strong>Sign in</strong></div>
            <i />
            <div><span>3</span><strong>Verify</strong></div>
            <p>Enter the DHCP address shown on the server or in the DHCP lease table, then save the sign-in used for first contact. Lab Builder will not connect until you explicitly run Verify.</p>
          </div>}
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
          {!isIloFirstContact && <label>
            <span>Addressing</span>
            <select aria-label="Device addressing mode" onChange={(event) => setForm({ ...form, dhcp_enabled: event.target.value === "dhcp" })} value={form.dhcp_enabled ? "dhcp" : "static"}>
              <option value="static">Static</option>
              <option value="dhcp">DHCP</option>
            </select>
          </label>}
          <label>
            <span>{isIloFirstContact ? "Current iLO DHCP address" : form.dhcp_enabled ? "Observed address" : "Host or management IP (optional)"}</span>
            <input
              aria-label={isIloFirstContact ? "Current iLO DHCP address" : "Device host"}
              disabled={!isIloFirstContact && form.dhcp_enabled}
              onChange={(event) => setForm({ ...form, host: event.target.value })}
              placeholder={isIloFirstContact ? "For example: 192.168.1.11" : form.dhcp_enabled ? "No address observed yet" : "IP address or hostname"}
              required={isIloFirstContact}
              value={form.host ?? ""}
            />
            {isIloFirstContact
              ? <small className="from-device-hint">The address is saved locally as the active first-contact target. No connection is attempted yet.</small>
              : form.dhcp_enabled && <small className="from-device-hint">Assigned by the network, not editable.</small>}
          </label>
          {isIloFirstContact && <>
            <div className="ilo-add-credentials-title"><span>Step 2</span><strong>Sign in to this iLO</strong></div>
            <label>
              <span>iLO username / UID</span>
              <input aria-label="iLO username or UID" autoComplete="username" onChange={(event) => setIloUsername(event.target.value)} placeholder={canReuseIloCredentials ? "Saved username" : "Administrator"} required={!canReuseIloCredentials} value={iloUsername} />
            </label>
            <label>
              <span>iLO password</span>
              <input aria-label="iLO password" autoComplete="current-password" onChange={(event) => setIloPassword(event.target.value)} placeholder={canReuseIloCredentials ? "Saved - type to replace" : "Password"} required={!canReuseIloCredentials} type="password" value={iloPassword} />
            </label>
            <label className="ilo-add-tls">
              <input checked={iloVerifyTls} onChange={(event) => setIloVerifyTls(event.target.checked)} type="checkbox" />
              <span>Verify iLO TLS certificate</span>
            </label>
          </>}
          <label>
            <span>Rack notes (optional)</span>
            <textarea aria-label="Device notes" onChange={(event) => setForm({ ...form, notes: event.target.value })} value={form.notes ?? ""} />
          </label>
          {error && <div className="operator-feedback error">{error}</div>}
          <p className="muted">{isIloFirstContact ? "Address and credentials are saved locally. Next, run an explicit read-only access check; no connection is attempted by this save." : "Inventory only. Saving places this device in the rack; it does not contact or change hardware."}</p>
          <button className="operator-primary-button" disabled={busy} type="submit">{busy ? "Saving" : isIloFirstContact ? device ? "Save iLO access" : "Save iLO and continue" : submitLabel ?? "Save device"}</button>
        </form>
      </aside>
    </div>
  );
}

function deviceInventoryError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
