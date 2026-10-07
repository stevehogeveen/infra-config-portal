import React from "react";
import { createRoot } from "react-dom/client";
import { RackServerAccess } from "../../src/components/RackServerAccess";
createRoot(document.getElementById("root")!).render(<RackServerAccess deviceId="fixture" checkConnection />);
