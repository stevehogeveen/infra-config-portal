import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { WindowsStep } from "../../src/components/WindowsStep";
import type { LabProfileList } from "../../src/types";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";
import "../../src/studio.css";

const context = (window as unknown as { windowsFixture: LabProfileList }).windowsFixture;
createRoot(document.getElementById("root")!).render(<MemoryRouter initialEntries={["/setup/install-windows"]}>
  <div className="app-shell-workbench" style={{ padding: 24 }}><WindowsStep labProfileState={context} /></div>
</MemoryRouter>);
