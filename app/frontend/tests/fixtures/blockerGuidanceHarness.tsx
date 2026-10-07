import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { BlockerGuidance } from "../../src/components/BlockerGuidance";
import type { BlockerDetail } from "../../src/api";
import "../../src/styles.css";
import "../../src/workflow.css";
import "../../src/studio.css";

const clicks: string[] = [];
(window as unknown as { clicks: string[] }).clicks = clicks;
const blockers = [
  "At least one enabled healthy power supply with input voltage is required.",
  "Fresh cooling and temperature inventory is required.",
  "Present cooling and temperature sensor evidence is required.",
  "Save the iLO address first.",
  "Some brand-new backend message.",
];
const details: BlockerDetail[] = [
  { code: "psu_no_input", text: blockers[0], fix_kind: "physical", fix: "Connect at least one healthy power supply to a working outlet.", action: "read_again" },
  { code: "thermal_incomplete", text: blockers[1], fix_kind: "app", fix: "Read the iLO again.", action: "read_again" },
  { code: "thermal_incomplete", text: blockers[2], fix_kind: "app", fix: "Read the iLO again.", action: "read_again" },
  { code: "connection_missing", text: blockers[3], fix_kind: "app", fix: "Save the exact server's iLO address and sign-in.", action: "open_connection" },
];
createRoot(document.getElementById("root")!).render(<BrowserRouter><main style={{ padding: 16, maxWidth: 560 }}>
  <BlockerGuidance title="Fix this first" blockers={blockers} details={details} deviceId="srv-1"
    handlers={{ read_again: () => clicks.push("read_again"), narrow_scope_firmware: () => clicks.push("scope") }} />
  <div data-testid="empty"><BlockerGuidance blockers={[]} details={details} /></div>
  <div data-testid="nohandler"><BlockerGuidance title="Plain" blockers={[blockers[1]]} details={details} /></div>
</main></BrowserRouter>);
