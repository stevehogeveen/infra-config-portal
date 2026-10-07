import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import type { LabProfile } from "../../src/types";
import { StudioProvider } from "../../src/components/studio/StudioContext";
import { StudioRail } from "../../src/components/studio/StudioRail";
import "../../src/studio.css";

const profile = { id: "fixture-r", name: "Rail kit", source: "saved", subnet_cidr: "192.0.2.0/24" } as LabProfile;
createRoot(document.getElementById("root")!).render(<BrowserRouter>
  <StudioProvider profile={profile}><StudioRail viewing={null} /></StudioProvider>
</BrowserRouter>);
