import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { RackSwitchAccess } from "../../src/components/RackSwitchAccess";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";
import "../../src/studio.css";

createRoot(document.getElementById("root")!).render(<MemoryRouter initialEntries={["/setup/connect"]}>
  <div className="app-shell-workbench sd-frame" style={{ padding: 24 }}><RackSwitchAccess profileId="fixture" deviceId="sw" deviceName="Cisco switch 1" /></div>
</MemoryRouter>);
