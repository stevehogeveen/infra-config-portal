import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { KitContract } from "../../src/components/KitContract";
import "../../src/styles.css";
import "../../src/studio.css";

createRoot(document.getElementById("root")!).render(<MemoryRouter initialEntries={["/contract"]}><KitContract profileId="fixture" /></MemoryRouter>);
