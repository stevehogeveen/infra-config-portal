import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { RackPlanner } from "../../src/components/RackPlanner";
import { SetupJourney, SetupReview } from "../../src/components/SetupJourney";
import { ActivityPage } from "../../src/components/ActivityPage";
import { RackFirmwareReview } from "../../src/components/RackFirmwareReview";
import { DisksRaidStep } from "../../src/components/StorageSteps";

function rack(mode: "rack" | "checklist" | "equipment" | "connect") {
  return <div className="rack-workbench"><RackPlanner mode={mode} profileId="fixture" profileName="Kit Alpha" /></div>;
}
ReactDOM.createRoot(document.getElementById("root")!).render(<BrowserRouter><Routes>
  <Route path="/activity-test" element={<ActivityPage />} />
  <Route path="/simple" element={rack("rack")} />
  <Route path="/equipment" element={rack("checklist")} />
  <Route path="/setup/guide" element={<SetupJourney step={0}>{rack("equipment")}</SetupJourney>} />
  <Route path="/setup/connect" element={<SetupJourney step={1}>{rack("connect")}</SetupJourney>} />
  <Route path="/setup/defaults" element={<SetupJourney step="defaults"><h1>Network settings</h1></SetupJourney>} />
  <Route path="/setup/check-firmware" element={<SetupReview step={2}><RackFirmwareReview profileId="fixture" /></SetupReview>} />
  <Route path="/setup/disks" element={<SetupJourney step={3}><DisksRaidStep profileId="fixture" /></SetupJourney>} />
  <Route path="/setup/raid" element={<SetupJourney step={3}><DisksRaidStep profileId="fixture" /></SetupJourney>} />
  <Route path="/setup/prepare-esxi" element={<SetupReview step={4}><p>Existing guarded tools</p></SetupReview>} />
  <Route path="/setup/install-windows" element={<SetupReview step={5}><p>Existing guarded tools</p></SetupReview>} />
</Routes></BrowserRouter>);
