import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { KitLibrary } from "../../src/components/KitLibrary";
import { api } from "../../src/api";
import type { LabProfileList } from "../../src/types";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
function Harness() {
  const [state, setState] = useState<LabProfileList | null>(null);
  async function reload() { setState(await api.labProfiles()); }
  useEffect(() => { void reload(); }, []);
  return <BrowserRouter><KitLibrary state={state} onReload={reload} /></BrowserRouter>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
