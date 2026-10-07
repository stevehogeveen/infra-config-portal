import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { FirmwareOverview } from "../../src/components/FirmwareOverview";
import "../../src/styles.css";
import "../../src/workflow.css";
import "../../src/studio.css";

createRoot(document.getElementById("root")!).render(<BrowserRouter><main style={{ padding: 16 }}>
  <FirmwareOverview profileId="kit" deviceId="srv" deviceName="Fixture server" model="Planned model" packageName="fixture.iso" packageCurrent />
</main></BrowserRouter>);
