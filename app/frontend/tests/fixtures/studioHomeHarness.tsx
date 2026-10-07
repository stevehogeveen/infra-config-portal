import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import type { LabProfile } from "../../src/types";
import { StudioProvider } from "../../src/components/studio/StudioContext";
import { RackHomeFrame } from "../../src/components/SetupJourney";
import { RackPlanner } from "../../src/components/RackPlanner";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";
import "../../src/studio.css";

// The Studio My Rack home exactly as App mounts it: provider, frame (rail, guide, drawer) and rack.
const profile = { id: "fixture", name: "Kit Single Gen 10", source: "saved", subnet_cidr: "192.0.2.0/27", gateway: "192.0.2.1" } as LabProfile;
createRoot(document.getElementById("root")!).render(<BrowserRouter>
  <div className="app-shell app-shell-simple app-shell-workbench"><main className="content content-rack">
    <StudioProvider profile={profile}><RackHomeFrame><div className="rack-workbench">
      <RackPlanner mode="rack" profileId="fixture" profileName="Kit Single Gen 10" />
    </div></RackHomeFrame></StudioProvider>
  </main></div>
</BrowserRouter>);
