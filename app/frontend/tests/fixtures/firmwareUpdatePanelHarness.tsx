import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { FirmwareUpdatePanel } from "../../src/components/FirmwareUpdatePanel";
import "../../src/styles.css";
import "../../src/workflow.css";
import "../../src/studio.css";

createRoot(document.getElementById("root")!).render(<BrowserRouter><div className="app-shell-workbench"><div className="fw-panel" style={{ position: "static", height: "auto" }}>
  <FirmwareUpdatePanel profileId="kit" deviceId="srv" deviceName="HPE DL360 3" step="1.48" onActivity={() => {}} onChanged={() => {}} />
</div></div></BrowserRouter>);
