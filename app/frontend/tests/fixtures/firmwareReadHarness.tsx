import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { FirmwareReadCheck } from "../../src/components/FirmwareReadCheck";
import "../../src/styles.css";
import "../../src/firmwarePackage.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";
createRoot(document.getElementById("root")!).render(<BrowserRouter><div className="app-shell-workbench"><div className="setup-body"><section className="rack-firmware-device"><FirmwareReadCheck profileId="fixture-kit" deviceId="fixture-server" packageName="Gen10.iso" packageCurrent /></section></div></div></BrowserRouter>);
