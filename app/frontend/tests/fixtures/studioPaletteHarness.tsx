import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import type { LabProfile } from "../../src/types";
import { StudioProvider } from "../../src/components/studio/StudioContext";
import { CommandPalette } from "../../src/components/studio/CommandPalette";
import "../../src/studio.css";

const profile = { id: "fixture-p", name: "Palette kit", source: "saved" } as LabProfile;
createRoot(document.getElementById("root")!).render(<BrowserRouter>
  <StudioProvider profile={profile}><button type="button">Before palette</button><CommandPalette />
    <dialog id="danger"><p>Destructive confirmation</p><button type="button">Cancel</button></dialog>
    <button type="button" onClick={() => (document.getElementById("danger") as HTMLDialogElement).showModal()}>Open confirmation</button>
  </StudioProvider>
</BrowserRouter>);
