import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { WriteScopeControl, WriteScopePill } from "../../src/components/studio/WriteScope";
import "../../src/styles.css";
import "../../src/workflow.css";
import "../../src/studio.css";

createRoot(document.getElementById("root")!).render(<BrowserRouter><div className="app-shell-workbench">
  <header className="sd-top"><WriteScopePill /></header>
  <div className="sd-frame"><div className="sd-main"><WriteScopeControl /></div></div>
</div></BrowserRouter>);
