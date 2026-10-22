import React from "react";
import { createRoot } from "react-dom/client";
import { RehearsalPage } from "../../src/components/RehearsalPage";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";
import "../../src/studio.css";

createRoot(document.getElementById("root")!).render(<div className="app-shell-workbench sd-frame" style={{ padding: 24 }}><RehearsalPage tick={25} /></div>);
