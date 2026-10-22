import { api, writeScopeApi } from "../api";
import { WRITE_SCOPE_CHANGED } from "./studio/WriteScope";

/*
 * Shared steps for the storage installers (Build RAID, Wipe disks). Each one sends one request per
 * call and never retries a hardware write by itself; waiting is done with read-only checks.
 */

const pause = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

/** Disks-and-RAID-only permission: nothing else on the server can be changed meanwhile. */
export async function allowStorageChanges() {
  await allowOnly("storage_only");
}

/** Narrow the server's permission to exactly one kind of change for the duration of an installer. */
export async function allowOnly(target: "storage_only" | "esxi_install_only" | "firmware_only" | "vm_deploy_only" | "switch_setup_only") {
  const scope = await writeScopeApi.get();
  if (scope.scope === target) return;
  const narrow = await writeScopeApi.preview(target);
  if (narrow.blockers?.length) throw new Error(narrow.blockers.join(" "));
  await writeScopeApi.apply({ review_token: narrow.review_token, confirmation_phrase: narrow.confirmation_phrase ?? "" });
  window.dispatchEvent(new Event(WRITE_SCOPE_CHANGED));
}

/** A locked-down permission whose phrase the operator types (the preview never hands it out). */
export async function allowTyped(target: "switch_reset_only", typed: string) {
  const scope = await writeScopeApi.get();
  if (scope.scope === target) return;
  const narrow = await writeScopeApi.preview(target);
  if (narrow.blockers?.length) throw new Error(narrow.blockers.join(" "));
  await writeScopeApi.apply({ review_token: narrow.review_token, confirmation_phrase: typed });
  window.dispatchEvent(new Event(WRITE_SCOPE_CHANGED));
}

/** Back to read-only once the installer is done. */
export async function lockReadOnly() {
  const scope = await writeScopeApi.get();
  if (scope.scope === "read_only") return;
  const lock = await writeScopeApi.preview("read_only");
  await writeScopeApi.apply({ review_token: lock.review_token, confirmation_phrase: lock.confirmation_phrase ?? "" });
  window.dispatchEvent(new Event(WRITE_SCOPE_CHANGED));
}

/** Power the server off: a normal power-button press first, forced off after two minutes if needed. */
export async function powerOffServer(profileId: string, deviceId: string, say: (text: string) => void, stopIf: () => void = () => undefined) {
  const on = async () => { stopIf(); return (await api.resetPowerState(profileId, deviceId)).power !== "Off"; };
  if (!(await on())) return;
  say("Turning the server off…");
  const soft = await api.previewResetShutdown(profileId, deviceId, false);
  if (!soft.apply_enabled) throw new Error(soft.blockers[0] ?? "The server can't be turned off yet.");
  stopIf();
  await api.applyResetShutdown(profileId, deviceId, soft.preview_id, soft.confirmation);
  for (let i = 0; i < 13; i++) { await pause(10000); if (!(await on())) return; }
  stopIf();  // the forced power-off is a separate decision point: a paused install never reaches it
  say("The server didn't turn off by itself, so it's being powered off…");
  const hard = await api.previewResetShutdown(profileId, deviceId, true);
  if (!hard.apply_enabled) throw new Error(hard.blockers[0] ?? "The server can't be powered off yet.");
  stopIf();
  await api.applyResetShutdown(profileId, deviceId, hard.preview_id, hard.confirmation);
  for (let i = 0; i < 12; i++) { await pause(10000); if (!(await on())) return; }
  throw new Error("The server is still reporting power on. Nothing else was sent. Check its power in the iLO and try again.");
}

/** Start the server so the controller applies what was saved on it. */
export async function startToApply(profileId: string, deviceId: string, stopIf: () => void = () => undefined) {
  const boot = await api.previewRaidBoot(profileId, deviceId);
  if (boot.blockers.length || !boot.apply_enabled) throw new Error(boot.blockers[0] ?? "The server start can't be requested yet.");
  stopIf();
  await api.startRaidBoot(profileId, deviceId, { preview_id: boot.preview_id, confirmation: boot.confirmation,
    pending_changes_reviewed: true, data_loss_confirmed: true, maintenance_confirmed: true });
}

export { pause };
