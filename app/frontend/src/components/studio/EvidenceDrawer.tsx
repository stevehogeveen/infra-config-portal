import { Link } from "react-router-dom";
import { useStudio, type DeviceEvidence } from "./StudioContext";
import { ProvenanceChip, shortTime } from "./ProvenanceChip";
import type { RaidOperationStatus } from "../../api";

const operationName: Record<string, string> = { clear: "Remove existing RAID", create: "Create new RAID", reset: "Reset storage controller", sanitize: "Erase physical disks" };
const statusWord: Record<RaidOperationStatus["status"], string> = {
  not_started: "no operation recorded", staged: "staged, waiting for power-on confirmation", waiting: "waiting for verified results",
  uncertain: "outcome unknown", verified: "verified", needs_attention: "needs attention", failed: "failed",
};

export function StorageRecord({ status }: { status: RaidOperationStatus }) {
  if (status.status === "not_started" || !status.operation) return null;
  const sanitizeVerified = status.operation === "sanitize" && status.status === "verified";
  const scope = status.sanitization?.drives?.length ?? status.erase_scope?.length ?? null;
  return <div className="sd-evg">
    <div className="sd-ev-t"><strong>Recorded storage result</strong><ProvenanceChip kind="recorded" time={status.verified_at || status.submitted_at}>recorded</ProvenanceChip></div>
    <dl className="sd-kv">
      <div><dt>result</dt><dd>{sanitizeVerified ? "Disk erasure verified" : `${operationName[status.operation]} · ${statusWord[status.status]}`}</dd></div>
      {status.submitted_at && <div><dt>requested</dt><dd>{shortTime(status.submitted_at)}</dd></div>}
      {status.boot_started_at && <div><dt>power-on</dt><dd>{shortTime(status.boot_started_at)}, requested</dd></div>}
      {status.verified_at && <div><dt>verified</dt><dd>{shortTime(status.verified_at)}</dd></div>}
      {scope !== null && scope > 0 && <div><dt>scope</dt><dd>{scope} reviewed disk{scope === 1 ? "" : "s"}</dd></div>}
    </dl>
    <p className="sd-fine">{status.status === "verified" ? "Recorded result, not a live check. " : ""}A request, a boot or an empty RAID list alone is never counted as proof.</p>
  </div>;
}

function DeviceEvidencePanel({ item }: { item: DeviceEvidence }) {
  const access = item.access;
  const connectLink = `/setup/connect?device=${encodeURIComponent(item.deviceId || item.id)}`;
  if (item.kind !== "server") return <div className="sd-evg">
    <div className="sd-ev-t"><strong>{item.name}</strong><ProvenanceChip kind="blank">no check</ProvenanceChip></div>
    <p>The app has no read-only check for this kind of equipment yet, so nothing about it is proven.</p>
    <p className="sd-fine">Its kind and position come from your saved plan. Nothing here turns green until this piece answers a check itself.</p>
  </div>;
  if (!item.deviceId) return <div className="sd-evg">
    <div className="sd-ev-t"><strong>{item.name}</strong><ProvenanceChip kind="blank">draft</ProvenanceChip></div>
    <p>This server is still a rack draft. Save the rack layout, then connect it.</p>
  </div>;
  const probed = !!access?.last_probe_time;
  if (item.accessUnavailable) return <div className="sd-evg">
    <div className="sd-ev-t"><strong>{item.name}</strong><ProvenanceChip kind="warn">unavailable</ProvenanceChip></div>
    <p>Its saved connection and last check could not be read just now, so nothing about this server is shown as proven.</p>
    <Link className="sd-btn sd-btn-sm" to={connectLink}>Open its connection check</Link>
  </div>;
  const chip = item.proven ? <ProvenanceChip kind="proven" time={access!.last_probe_time}>proven</ProvenanceChip>
    : item.attention === "failed" ? <ProvenanceChip kind="danger">{access?.last_probe_status || "failed"}</ProvenanceChip>
    : item.attention === "stale" ? <ProvenanceChip kind="warn">not current</ProvenanceChip>
    : <ProvenanceChip kind="blank">never answered</ProvenanceChip>;
  return <div className="sd-evg">
    <div className="sd-ev-t"><strong>{item.name}</strong>{chip}</div>
    {!probed ? <p>No read-only check has been recorded for this server. Model, bays and drives stay unknown until it answers.</p>
      : !access!.last_probe_target_matches_access_host ? <p>The last check was for a different address than the one saved now, so it is not proof for this target.</p>
      : <p>A read-only check of the server's iLO{access!.host ? <> at <span className="sd-mono">{access!.host}</span></> : null}. Nothing was written.</p>}
    {probed && <dl className="sd-kv">
      <div><dt>checked</dt><dd>{shortTime(access!.last_probe_time)}</dd></div>
      <div><dt>outcome</dt><dd>{access!.last_probe_status}{item.attention === "stale" ? " · not current" : ""}</dd></div>
      <div><dt>iLO</dt><dd className={item.proven && access!.observed_ilo_firmware ? "pv" : undefined}>{item.proven && access!.observed_ilo_firmware || "not read"}</dd></div>
      <div><dt>ROM</dt><dd className={item.proven && access!.observed_bios_version ? "pv" : undefined}>{item.proven && access!.observed_bios_version || "not read"}</dd></div>
      <div><dt>TLS setting</dt><dd>{access!.verify_tls ? "verify certificate: on (saved setting)" : "verify certificate: off (saved setting)"}</dd></div>
      <div><dt>drives</dt><dd>not read in this check</dd></div>
    </dl>}
    {access?.last_probe_message && <p className="sd-fine">{access.last_probe_message}</p>}
    <Link className="sd-btn sd-btn-sm" to={connectLink}>Open its connection check</Link>
  </div>;
}

export function EvidenceDrawer() {
  const studio = useStudio();
  if (!studio) return null;
  const item = studio.selected;
  const pip = item?.proven ? "ok" : item?.attention === "failed" ? "bad" : "";
  const railLabel = item ? `${item.name}${item.proven ? ` · ${shortTime(item.answeredAt)}` : ""}` : "nothing selected";
  const others = studio.devices.filter(entry => entry.id !== item?.id);
  return <aside className={`sd-drawer ${studio.drawerOpen ? "" : "collapsed"}`} aria-label="Evidence drawer">
    <div className="sd-dr-in">
      <div className="sd-dr-head"><b>Evidence · last check</b><button type="button" className="sd-dr-toggle" onClick={() => studio.setDrawerOpen(false)} aria-label="Fold the evidence drawer"><kbd>E</kbd><svg className="sd-ic sd-ic-s" viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="2.5" width="12" height="11" rx="2" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M10 2.5v11" stroke="currentColor" strokeWidth="1.4" /></svg></button></div>
      <div className="sd-dr-body">
        {!item ? <div className="sd-evg"><p><b>Nothing selected.</b> Choose a piece of equipment in the rail to see what its last read-only check returned.</p></div> : <>
          <DeviceEvidencePanel item={item} />
          {item.storage && <StorageRecord status={item.storage} />}
          {item.storageRead?.state === "unavailable" && <div className="sd-evg"><div className="sd-ev-t"><strong>Recorded storage result</strong><ProvenanceChip kind="warn">status unknown</ProvenanceChip></div><p>The recorded storage status could not be read. It is unknown, not "none".</p><p className="sd-fine">{item.storageRead.message}</p></div>}
        </>}
        {others.length > 0 && <div className="sd-evg">
          <h5>Other equipment</h5>
          <ul className="sd-reads">{others.map(entry => <li key={entry.id}><time>{entry.proven ? shortTime(entry.answeredAt) : "—"}</time><span>{entry.name} · {entry.proven ? "answered" : entry.attention === "failed" ? "check failed" : entry.attention === "stale" ? "last answer not current" : entry.kind === "server" ? "never answered" : "no check available"}</span></li>)}</ul>
          <p className="sd-fine">Green appears only for a current read of this exact device, always with its time. One device's answer never colours another.</p>
        </div>}
      </div>
      <button type="button" className="sd-dr-rail" onClick={() => studio.setDrawerOpen(true)} aria-label="Open the evidence drawer"><span className={`sd-pip ${pip}`} /><span>Evidence · <em>{railLabel}</em> · E</span></button>
    </div>
  </aside>;
}
