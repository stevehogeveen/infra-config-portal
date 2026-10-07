import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { DisksRaidStep } from "../../src/components/StorageSteps";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";
import "../../src/studio.css";

createRoot(document.getElementById("root")!).render(<BrowserRouter><div className="app-shell-workbench"><div className="sd-frame"><div className="sd-main"><Routes>
  <Route path="/disks-fixture" element={<DisksRaidStep profileId="fixture" />} />
  <Route path="/raid-fixture" element={<DisksRaidStep profileId="fixture" />} />
</Routes></div></div></div></BrowserRouter>);
