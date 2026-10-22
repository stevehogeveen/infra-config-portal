import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { KitInstaller } from "../../src/components/KitInstaller";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";
import "../../src/studio.css";

const fast = () => new Promise<void>(resolve => setTimeout(resolve, 20));
createRoot(document.getElementById("root")!).render(<MemoryRouter>
  <div className="app-shell-workbench sd-frame" style={{ padding: 24 }}><KitInstaller profileId="fixture" sleep={fast} /></div>
</MemoryRouter>);
