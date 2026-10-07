import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { FirmwareBridgePrep } from "../../src/components/FirmwareBridgePrep";
import { GuardedExecution } from "../../src/components/GuardedExecution";
import "../../src/styles.css";
import "../../src/workflow.css";
import "../../src/studio.css";

createRoot(document.getElementById("root")!).render(<BrowserRouter><div className="sd-frame"><div className="sd-main">
  <FirmwareBridgePrep profileId="kit" deviceId="srv" deviceName="HPE DL360 3" />
  <GuardedExecution kind="firmware" profileId="kit" deviceId="srv" deviceName="HPE DL360 3" />
</div></div></BrowserRouter>);
