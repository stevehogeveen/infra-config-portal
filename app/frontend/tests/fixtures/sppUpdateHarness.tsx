import React, { StrictMode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { FirmwareOverview } from "../../src/components/FirmwareOverview";
import { SppUpdatePanel, useSppAvailability } from "../../src/components/SppUpdatePanel";
import "../../src/styles.css";
import "../../src/workflow.css";
import "../../src/studio.css";

// The boot-disc panel on its own (the firmware page reaches it through the one Update firmware
// window), opened the way the page used to, so its own tests keep exercising it directly.
function BootDiscPanel() {
  const spp = useSppAvailability("kit", "srv");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(false);
  const panel = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (open) panel.current?.showModal(); else panel.current?.close(); }, [open]);
  if (spp.state !== "available") return null;
  return <section aria-label="Boot-disc panel harness">
    <button type="button" onClick={() => setOpen(true)}>{active || spp.inProgress ? "Update in progress · open" : "Boot-disc update"}</button>
    <dialog ref={panel} className="fw-panel" aria-label="Update firmware on Fixture server" onCancel={event => { event.preventDefault(); setOpen(false); }}>
      <SppUpdatePanel profileId="kit" deviceId="srv" onActivity={setActive} onClose={() => setOpen(false)} />
    </dialog>
  </section>;
}

// StrictMode on purpose: effects run setup, cleanup, setup, which must not drop responses.
createRoot(document.getElementById("root")!).render(<StrictMode><BrowserRouter><main style={{ padding: 16 }}>
  <FirmwareOverview profileId="kit" deviceId="srv" deviceName="Fixture server" model="Planned model" packageName="fixture.iso" packageCurrent />
  <BootDiscPanel />
</main></BrowserRouter></StrictMode>);
