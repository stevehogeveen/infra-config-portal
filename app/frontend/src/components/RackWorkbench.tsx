import { useEffect, useState } from "react";
import { api } from "../api";
import { RackPlanner } from "./RackPlanner";
import type { DeviceInventoryItem, LabProfileList } from "../types";

export function RackWorkbench({ mode = "rack" }: { mode?: "rack" | "equipment" | "connect" | "checklist" }) {
  const [context, setContext] = useState<{ profiles: LabProfileList; devices: DeviceInventoryItem[] } | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setError("");
    Promise.all([api.labProfiles(), api.deviceInventory()]).then(([profiles, devices]) => {
      if (!cancelled) setContext({ profiles, devices });
    }).catch((err) => { if (!cancelled) setError(String(err.message || err)); });
    return () => { cancelled = true; };
  }, [attempt]);
  if (error) return <section className="workbench-loading"><h1>Rack home</h1><p role="alert">{error}</p><button type="button" onClick={() => setAttempt(attempt + 1)}>Reconnect</button></section>;
  if (!context) return <section className="workbench-loading"><h1>Rack home</h1><p>Loading saved equipment...</p></section>;
  const profile = context.profiles.active_profile ?? context.profiles.runtime_profile;
  if (!profile) return <section className="workbench-loading"><h1>Rack home</h1><p>No active kit. Select a kit in Lab defaults.</p></section>;
  return <div className="rack-workbench"><RackPlanner key={`${profile.id}:${mode}`} mode={mode} profileId={profile.id} profileName={profile.name} devices={context.devices} /></div>;
}
