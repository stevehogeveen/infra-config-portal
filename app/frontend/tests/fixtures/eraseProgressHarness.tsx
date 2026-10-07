import React from "react";
import {createRoot} from "react-dom/client";
import {RaidOperation} from "../../src/components/RaidOperation";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";

createRoot(document.getElementById("root")!).render(
  <main className="app-shell-workbench"><RaidOperation profileId="fixture" deviceId="fixture" revision={0} disabled={false}
    onActive={()=>{}} onBusy={()=>{}} onVerified={()=>{}}
    onRetryErase={()=>{document.body.dataset.retryOpened="true";}}/></main>
);
