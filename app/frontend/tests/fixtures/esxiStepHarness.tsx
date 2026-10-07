import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { EsxiStep } from "../../src/components/EsxiStep";
import type { LabProfileList } from "../../src/types";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";
import "../../src/studio.css";

const context = (window as unknown as { esxiFixture: LabProfileList }).esxiFixture;
createRoot(document.getElementById("root")!).render(<MemoryRouter initialEntries={["/setup/prepare-esxi"]}>
  <div className="app-shell-workbench" style={{ padding: 24 }}><EsxiStep labProfileState={context} onReloadLabProfile={async () => {}} /></div>
</MemoryRouter>);
