import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { ResetPage } from "../../src/components/ResetPage";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";
import "../../src/studio.css";

createRoot(document.getElementById("root")!).render(<MemoryRouter initialEntries={["/reset"]}>
  <div className="app-shell-workbench sd-frame" style={{ padding: 24 }}><ResetPage profileId="fixture" /></div>
</MemoryRouter>);
