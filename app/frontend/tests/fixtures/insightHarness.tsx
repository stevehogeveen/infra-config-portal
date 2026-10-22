import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { AskPage, TimeLapse, TracePage } from "../../src/components/InsightPages";
import { parseIloTag, TagCamera } from "../../src/components/TagCamera";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";
import "../../src/studio.css";

(window as any).parseIloTag = parseIloTag;
const view = new URLSearchParams(location.search).get("view");
const history = [
  { id: "1", at: "2026-10-15T09:00:00Z", area: "Server check", message: "iLO answered.", outcome: "ok", actor: "op" },
  { id: "2", at: "2026-10-15T10:00:00Z", area: "Disks & RAID", message: "RAID built.", outcome: "ok", actor: "op" },
  { id: "3", at: "2026-10-15T11:00:00Z", area: "Switch", message: "No DHCP address.", outcome: "failed", actor: "op" },
];
createRoot(document.getElementById("root")!).render(<MemoryRouter>
  <div className="app-shell-workbench sd-frame" style={{ padding: 24 }}>
    {view === "trace" ? <TracePage profileId="fixture" /> : view === "ask" ? <AskPage /> : view === "camera" ? <TagCamera onUse={fields => { (window as any).used = fields; }} onClose={() => undefined} /> : <TimeLapse entries={history as any} />}
  </div>
</MemoryRouter>);
