import React from "react";
import { createRoot } from "react-dom/client";
import { FirmwarePackageSource } from "../../src/components/FirmwarePackageSource";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
createRoot(document.getElementById("root")!).render(<div style={{padding:16}}><FirmwarePackageSource profileId="fixture-kit" onChange={()=>{}}/></div>);
