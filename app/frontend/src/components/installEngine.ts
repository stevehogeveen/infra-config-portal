/*
 * The "Build my kit" installer engine: runs every build step in order with the same API calls the
 * step installers use, after one up-front approval. Each step first reads what the app recorded:
 * a verified step is skipped, a step already underway is watched (never started again), and only a
 * step that has not been done is started. Each change is sent once by the server-side run; this
 * engine only starts runs and reads their status.
 *
 * Safety:
 *  - ctx.stopIf() is called before every request that can change equipment and after every wait;
 *    a paused install (page left, Pause) throws there, so nothing new is sent after a pause.
 *  - a step that needs a write permission takes exactly that one (also when resuming a run already
 *    underway), and permission returns to read-only at the end of every step and on any stop.
 *  - anything the engine cannot decide for the operator (a blocker, a step needing attention, an
 *    unclear firmware result) stops the install with NeedsYou saying what to do and where.
 */
import { api, partsUpdateApi, sppUpdateApi, switchSetupApi, windowsApi } from "../api";
import { allowOnly, allowStorageChanges, lockReadOnly, powerOffServer, startToApply } from "./storageInstall";

export class NeedsYou extends Error {
  constructor(message: string, public where: string, public whereLabel: string) { super(message); }
}
export class Paused extends Error { constructor() { super("paused"); } }

export type Ctx = {
  profileId: string;
  servers: Array<{ deviceId: string; name: string }>;
  switches: Array<{ deviceId: string; name: string }>;
  say: (text: string) => void;
  /** Reports that write permission could not be returned to read-only. */
  warn: (text: string) => void;
  /** Throws Paused when the install has been paused. */
  stopIf: () => void;
  /** Resolves after ms; throws Paused if paused before or during the wait. */
  sleep: (ms: number) => Promise<void>;
};
export type StageResult = "done" | "skipped";
export type Stage = { id: string; title: string; changes: string; run: (ctx: Ctx) => Promise<StageResult> };

const RAID_HANDLED = /live-operation scope|Shut down the server cleanly first/i;
const TRANSIENT = /timed out|Network error|Bad Gateway|Service Unavailable|Gateway Timeout|\b50[234]\b|ECONNREFUSED|restarting/i;
const OUTAGE_LIMIT = 60;  // consecutive unreadable polls (equipment restarting) before the install stops

const message = (err: unknown) => err instanceof Error ? err.message : String(err);

async function poll<T>(ctx: Ctx, every: number, read: () => Promise<T>, done: (value: T) => boolean, stuck: (value: T) => string | null): Promise<T> {
  let failures = 0;
  for (;;) {
    ctx.stopIf();
    let value: T | null = null;
    try { value = await read(); failures = 0; }
    catch (err) {
      // Equipment restarting is expected; anything else (refused, invalid, conflict) stops at once.
      if (!TRANSIENT.test(message(err)) || ++failures >= OUTAGE_LIMIT) throw err;
    }
    if (value !== null) {
      if (done(value)) return value;
      const problem = stuck(value);
      if (problem) throw new Error(problem);
    }
    await ctx.sleep(every);
  }
}

const connect: Stage = { id: "connect", title: "Connect the servers", changes: "Read-only: signs in to each iLO and reads the server.", run: async ctx => {
  for (const server of ctx.servers) {
    ctx.stopIf();
    ctx.say(`Reading ${server.name} through its iLO…`);
    const probe = await api.probeProvider("ilo-redfish", server.deviceId);
    if (probe.status !== "ok") throw new NeedsYou(`${server.name}: ${probe.message || "the iLO did not answer."}`, "/setup/connect", "Open Connect");
  }
  return "done";
} };

const switchSetup: Stage = { id: "switch", title: "Set up the switch", changes: "Sends the reviewed first setup over the console cable (name, admin user, management address, SSH), then checks SSH.", run: async ctx => {
  let did = false;
  for (const sw of ctx.switches) {
    let status = await switchSetupApi.status(ctx.profileId, sw.deviceId);
    if (status.state === "verified") continue;
    if (status.state === "needs_attention") throw new NeedsYou(`${sw.name}: ${status.message}`, "/setup/connect", "Open Set up the switch");
    if (!status.active) {
      const review = await switchSetupApi.review(ctx.profileId, sw.deviceId);
      if (review.blockers.length) throw new NeedsYou(`${sw.name}: ${review.blockers[0]}`, "/setup/connect", "Open Set up the switch");
      if (review.replace_needed) throw new NeedsYou(`${sw.name} already has settings. Confirm replacing them on Set up the switch.`, "/setup/connect", "Open Set up the switch");
      ctx.stopIf();
      await allowOnly("switch_setup_only");
      ctx.stopIf();
      ctx.say(`Setting up ${sw.name} over the console…`);
      status = await switchSetupApi.start(ctx.profileId, sw.deviceId, false);
    } else {
      await allowOnly("switch_setup_only");  // the run's own permission, also when resuming it
    }
    await poll(ctx, 5000, () => switchSetupApi.advance(ctx.profileId, sw.deviceId), s => s.state === "verified",
      s => { ctx.say(s.step ? `${sw.name}: ${s.step}…` : s.message); return s.state === "needs_attention" || s.state === "failed" ? s.message : null; });
    did = true;
  }
  return did ? "done" : "skipped";
} };

const firmware: Stage = { id: "firmware", title: "Update firmware", changes: "Installs the firmware the package says is out of date, through the iLO and, if needed, HPE's boot disc. The server restarts, possibly several times.", run: async ctx => {
  let did = false;
  for (const server of ctx.servers) {
    const where = ["/setup/check-firmware", "Open Check firmware"] as const;
    const parts = await partsUpdateApi.status(ctx.profileId, server.deviceId);
    const spp = await sppUpdateApi.status(ctx.profileId, server.deviceId);
    if (parts.state === "needs_attention") throw new NeedsYou(`${server.name}: ${parts.message}`, ...where);
    if (spp.status === "uncertain") throw new NeedsYou(`${server.name}: ${spp.message}`, ...where);
    let partsActive = parts.active;
    if (!partsActive && !spp.active) {
      ctx.say(`Comparing ${server.name}'s firmware with the package…`);
      const plan = await partsUpdateApi.review(ctx.profileId, server.deviceId);
      if (plan.blockers.length) throw new NeedsYou(`${server.name}: ${plan.blockers[0]}`, ...where);
      if (plan.parts.length) {
        ctx.stopIf();
        await allowOnly("firmware_only");
        ctx.stopIf();
        await partsUpdateApi.start(ctx.profileId, server.deviceId, plan.review_id);
        partsActive = true;
      }
    } else if (partsActive) {
      await allowOnly("firmware_only");
    }
    if (partsActive) {
      did = true;
      await poll(ctx, 10000, () => partsUpdateApi.advance(ctx.profileId, server.deviceId), s => !s.active && s.state === "verified",
        s => { ctx.say(`${server.name}: ${s.message}`); return s.state === "needs_attention" || (!s.active && s.state !== "verified") ? s.message : null; });
    }
    let discRunning = spp.active;
    if (!discRunning) {
      // What only HPE's boot disc can still install. Anything unclear stops; nothing is skipped silently.
      const plan = await sppUpdateApi.plan(ctx.profileId, server.deviceId);
      if (plan.updates.length && !(plan.can_apply && plan.review_token && plan.confirmation_phrase)) {
        throw new NeedsYou(`${server.name}: ${plan.blockers[0] ?? "some firmware can only be installed from HPE's boot disc, and it can't start yet."}`, ...where);
      }
      if (plan.updates.length) {
        ctx.stopIf();
        await allowOnly("firmware_only");
        ctx.stopIf();
        ctx.say(`${server.name}: installing the rest from HPE's boot disc…`);
        await sppUpdateApi.apply(ctx.profileId, server.deviceId, { review_token: plan.review_token!, confirmation_phrase: plan.confirmation_phrase!, idempotency_key: crypto.randomUUID() });
        discRunning = true;
      }
    } else {
      await allowOnly("firmware_only");
    }
    if (discRunning) {
      did = true;
      await poll(ctx, 15000, () => sppUpdateApi.status(ctx.profileId, server.deviceId), s => !s.active && s.status === "verified",
        s => { ctx.say(`${server.name}: ${s.message}`); return s.status === "uncertain" || (!s.active && s.status !== "verified") ? s.message : null; });
    }
  }
  return did ? "done" : "skipped";
} };

const raid: Stage = { id: "raid", title: "Build RAID", changes: "Turns the server off (forced off if it has not shut down after two minutes), saves the planned RAID layout on the controller and starts the server so it builds it. Any data on the planned disks is lost. Disks that already have volumes are never touched: the install stops instead.", run: async ctx => {
  let did = false;
  for (const server of ctx.servers) {
    const where = ["/setup/disks", "Open Disks & RAID"] as const;
    const status = await api.raidOperationStatus(ctx.profileId, server.deviceId);
    if (status.operation === "create" && status.status === "verified") continue;
    if (["uncertain", "needs_attention", "failed"].includes(status.status) && status.operation === "create") throw new NeedsYou(`${server.name}: the last RAID build needs attention.`, ...where);
    const underway = status.operation === "create" && (status.status === "waiting" || status.status === "staged");
    if (!underway) {
      ctx.say(`Reading ${server.name}'s disks…`);
      const probe = await api.probeProvider("ilo-redfish", server.deviceId);
      if (probe.status !== "ok") throw new NeedsYou(`${server.name}: ${probe.message || "the iLO did not answer."}`, "/setup/connect", "Open Connect");
      const view = await api.diskPreparation(ctx.profileId, server.deviceId);
      if (view.blockers.length) throw new NeedsYou(`${server.name}: ${view.blockers[0]}`, ...where);
      if (view.volumes.length) throw new NeedsYou(`${server.name} already has RAID volumes. Keep them or wipe them on Disks & RAID; the installer never deletes volumes.`, ...where);
      const review = await api.previewRaidRebuild(ctx.profileId, server.deviceId, "create");
      const left = review.blockers.filter(item => !RAID_HANDLED.test(item));
      if (left.length) throw new NeedsYou(`${server.name}: ${left[0]}`, ...where);
      ctx.stopIf();
      await allowStorageChanges();
      await powerOffServer(ctx.profileId, server.deviceId, ctx.say, ctx.stopIf);
      ctx.say(`Saving the RAID layout on ${server.name}'s controller…`);
      const fresh = await api.previewRaidRebuild(ctx.profileId, server.deviceId, "create");
      if (!fresh.apply_enabled || fresh.blockers.length) throw new NeedsYou(`${server.name}: ${fresh.blockers[0] ?? "the RAID plan can't be applied yet."}`, ...where);
      ctx.stopIf();
      await api.applyRaidRebuild(ctx.profileId, server.deviceId, { preview_id: fresh.preview_id, confirmation: fresh.confirmation, data_loss_confirmed: true,
        backups_confirmed: true, health_reviewed: true, firmware_reviewed: true, empty_bays_confirmed: fresh.empty_bays });
      ctx.stopIf();
      ctx.say(`Starting ${server.name} so the controller builds the RAID…`);
      await startToApply(ctx.profileId, server.deviceId, ctx.stopIf);
    } else {
      await allowStorageChanges();
      if (status.status === "staged") await startToApply(ctx.profileId, server.deviceId, ctx.stopIf);
    }
    did = true;
    ctx.say(`${server.name} is building its RAID (it restarts)…`);
    await poll(ctx, 15000, () => api.verifyRaidRebuild(ctx.profileId, server.deviceId), r => r.verified, r => r.status === "failed" ? r.message : null);
  }
  return did ? "done" : "skipped";
} };

const esxi: Stage = { id: "esxi", title: "Install ESXi", changes: "Attaches the ESXi installer built from your ISO, boots it once and installs ESXi on the boot disks, then creates the VM datastore.", run: async ctx => {
  let did = false;
  for (const server of ctx.servers) {
    const where = ["/setup/prepare-esxi", "Open Prepare ESXi"] as const;
    const status = await api.esxiInstall(ctx.profileId, server.deviceId);
    if (status.state === "verified") continue;
    if (status.state === "needs_attention" || status.state === "closed") throw new NeedsYou(`${server.name}: ${status.message}`, ...where);
    if (status.state === "reachable") throw new NeedsYou(`${server.name}: ESXi answers but has not been verified yet. Finish the check on Prepare ESXi.`, ...where);
    if (!status.active) {
      let build = await api.esxiInstaller(ctx.profileId, server.deviceId);
      if (build.status === "not_built" || build.status === "stale") {
        ctx.say(`Building ${server.name}'s ESXi installer (about a minute; nothing touches the server)…`);
        build = await api.buildEsxiInstaller(ctx.profileId, server.deviceId);
      }
      if (build.status !== "ready") throw new NeedsYou(`${server.name}: ${build.blockers[0] ?? "the ESXi installer is not ready."}`, ...where);
      ctx.stopIf();
      await allowOnly("esxi_install_only");
      ctx.stopIf();
      ctx.say(`Installing ESXi on ${server.name} (about 20 minutes)…`);
      await api.startEsxiInstall(ctx.profileId, server.deviceId);
    } else {
      await allowOnly("esxi_install_only");  // finishing the run (eject, datastore) needs its permission
    }
    did = true;
    await poll(ctx, 30000, () => api.checkEsxiInstall(ctx.profileId, server.deviceId), s => s.state === "verified",
      s => { ctx.say(`${server.name}: ${s.message}`); return s.state === "needs_attention" || s.state === "closed" ? s.message
        : s.state === "reachable" && !s.active ? "ESXi answers but could not be verified. Finish the check on Prepare ESXi." : null; });
  }
  return did ? "done" : "skipped";
} };

const windows: Stage = { id: "windows", title: "Deploy Windows", changes: "Imports the chosen Windows image onto the VM datastore as a new VM and powers it on.", run: async ctx => {
  let did = false;
  for (const server of ctx.servers) {
    const status = await windowsApi.status(ctx.profileId, server.deviceId);
    if (status.state === "verified") continue;
    if (status.state === "needs_attention") throw new NeedsYou(`${server.name}: ${status.message}`, "/setup/install-windows", "Open Install Windows");
    if (!status.active) {
      const review = await windowsApi.review(ctx.profileId, server.deviceId);
      if (!review.ready) throw new NeedsYou(`${server.name}: ${review.blockers[0] ?? "Windows is not ready to deploy."}`, "/setup/install-windows", "Open Install Windows");
      ctx.stopIf();
      await allowOnly("vm_deploy_only");
      ctx.stopIf();
      ctx.say(`Importing Windows onto ${server.name} (large images take a while)…`);
      await windowsApi.start(ctx.profileId, server.deviceId);
    } else {
      await allowOnly("vm_deploy_only");
    }
    did = true;
    await poll(ctx, 15000, () => windowsApi.advance(ctx.profileId, server.deviceId), s => s.state === "verified",
      s => { ctx.say(`${server.name}: ${s.message}`); return s.state === "needs_attention" || s.state === "failed" ? s.message : null; });
  }
  return did ? "done" : "skipped";
} };

const acceptance: Stage = { id: "accept", title: "Prove it works", changes: "Checks Windows from outside and inside, restarts it once, and checks it is back.", run: async ctx => {
  let did = false;
  for (const server of ctx.servers) {
    const status = await windowsApi.test(ctx.profileId, server.deviceId);
    if (status.state === "verified") continue;
    if (status.state === "needs_attention") throw new NeedsYou(`${server.name}: ${status.message}`, "/setup/install-windows", "Open Install Windows");
    if (!status.active) {
      if (!status.signin.password_saved) throw new NeedsYou(`Save ${server.name}'s Windows administrator sign-in (Install Windows, step 4).`, "/setup/install-windows", "Open Install Windows");
      ctx.stopIf();
      await allowOnly("vm_deploy_only");
      ctx.stopIf();
      ctx.say(`Testing Windows on ${server.name}…`);
      await windowsApi.testStart(ctx.profileId, server.deviceId, status.lookup || status.default_lookup || "");
    } else {
      await allowOnly("vm_deploy_only");
    }
    did = true;
    await poll(ctx, 10000, () => windowsApi.testAdvance(ctx.profileId, server.deviceId), s => s.state === "verified",
      s => { const now = s.phases.find(p => p.state === "running"); if (now) ctx.say(`${server.name}: ${now.label}…`); return s.state === "needs_attention" || s.state === "failed" ? s.message : null; });
  }
  return did ? "done" : "skipped";
} };

export const STAGES: Stage[] = [connect, switchSetup, firmware, raid, esxi, windows, acceptance];

/** Return permission to read-only: a few tries, then say so. Never silently leaves it on. */
async function lock(ctx: Ctx): Promise<boolean> {
  let last = "";
  for (let attempt = 0; attempt < 3; attempt++) {
    try { await lockReadOnly(); return true; }
    catch (err) { last = message(err); await new Promise(resolve => setTimeout(resolve, 1000)); }
  }
  ctx.warn(`Write permission is still on: ${last}`);
  return false;
}

/**
 * Run stages from `from`; reports each stage's outcome. Permission returns to read-only after every
 * stage and on every exit (finished, stopped or paused). If that keeps failing, the install ends as
 * "needs you" with the instruction, never as done.
 */
export async function runInstall(ctx: Ctx, from: number, report: (index: number, state: "running" | StageResult) => void): Promise<void> {
  const stillOn = () => new NeedsYou("Write permission could not be returned to read-only. Set Read-only mode in the top bar, then press Try again.", "/", "Open My Rack");
  let locked = true;
  try {
    for (let index = from; index < STAGES.length; index++) {
      ctx.stopIf();
      report(index, "running");
      const result = await STAGES[index].run(ctx);
      if (!await lock(ctx)) throw stillOn();
      report(index, result);
    }
  } finally {
    locked = await lock(ctx);
  }
  if (!locked) throw stillOn();
}
