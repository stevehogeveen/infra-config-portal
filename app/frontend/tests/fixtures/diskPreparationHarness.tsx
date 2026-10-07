import React from "react";
import {createRoot} from "react-dom/client";
import {BrowserRouter} from "react-router-dom";
import {DiskPreparation} from "../../src/components/DiskPreparation";
import {SetupJourney} from "../../src/components/SetupJourney";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";
createRoot(document.getElementById("root")!).render(<BrowserRouter><div className="app-shell-workbench"><SetupJourney step={1}><DiskPreparation profileId="fixture" deviceId="s"/></SetupJourney></div></BrowserRouter>);
