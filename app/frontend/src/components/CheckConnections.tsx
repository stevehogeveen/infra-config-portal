import { useState } from "react";
import { PlugZap } from "lucide-react";
import { api, switchApi } from "../api";
import { requestStudioRefresh } from "./studio/StudioContext";
import type { PlannedEquipment } from "./RackPlanner";

/**
 * My Rack: one read-only check for every saved server (iLO sign-in and inventory read) and
 * switch (SSH sign-in and show commands), so the rack turns green without visiting each step.
 * Nothing on the equipment changes. Equipment without saved sign-in details is skipped.
 */
export function CheckConnections({ equipment }: { equipment: PlannedEquipment[] }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState("");
  const targets = equipment.filter(item => item.device_id && (item.kind === "server" || item.kind === "switch"));
  if (!targets.length) return null;
  async function run() {
    setBusy(true); setResult("");
    const outcomes = await Promise.all(targets.map(async item => {
      try {
        if (item.kind === "server") {
          const probe = await api.probeProvider("ilo-redfish", item.device_id!);
          return probe.status === "ok" ? "ok" : `${item.name}: ${probe.message || "did not answer"}`;
        }
        const access = await switchApi.read(item.device_id!);
        if (!access.host || !access.password_configured) return `${item.name}: not set up yet (Connect equipment)`;
        const check = await switchApi.check(item.device_id!);
        return check.status === "ok" ? "ok" : `${item.name}: ${check.message}`;
      } catch (err) {
        return `${item.name}: ${err instanceof Error ? err.message : String(err)}`;
      }
    }));
    const answered = outcomes.filter(outcome => outcome === "ok").length;
    const problems = outcomes.filter(outcome => outcome !== "ok");
    setResult(`${answered} of ${targets.length} answered.${problems.length ? " " + problems.join(" · ") : ""}`);
    setBusy(false);
    requestStudioRefresh();
  }
  return <div className="check-connections">
    <button type="button" className="secondary-action" disabled={busy} onClick={() => void run()}><PlugZap size={16} />{busy ? "Checking…" : "Check connections"}</button>
    {result && <span role="status">{result}</span>}
  </div>;
}
