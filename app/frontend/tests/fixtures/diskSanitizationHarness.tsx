import React from "react";
import {createRoot} from "react-dom/client";
import {DiskSanitization} from "../../src/components/DiskSanitization";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";
const noop = () => {};
createRoot(document.getElementById("root")!).render(<main className="app-shell-workbench"><DiskSanitization profileId="fixture" deviceId="server" disabled={false} onBusy={noop} onChanged={noop}/></main>);
