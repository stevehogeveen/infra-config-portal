import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import type { LabProfile } from "../../src/types";
import { StudioProvider, useStudio } from "../../src/components/studio/StudioContext";
import { StudioFrame } from "../../src/components/studio/StudioFrame";
import "../../src/studio.css";

function Snapshot() {
  const data = useStudio()!;
  return <output data-testid="snapshot">{JSON.stringify({
    profile: data.profileId, loading: data.loading,
    devices: data.devices.map(item => ({ id: item.id, proven: item.proven })),
  })}</output>;
}

function Harness() {
  const [id, setId] = useState("fixture-a");
  const profile = { id, name: id, source: "saved" } as LabProfile;
  return <BrowserRouter><button onClick={() => setId("fixture-b")}>Switch fixture kit</button>
    <StudioProvider profile={profile}><StudioFrame viewing={2}>
      <Snapshot />
    </StudioFrame></StudioProvider>
  </BrowserRouter>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
