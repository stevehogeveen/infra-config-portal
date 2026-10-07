import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { GuardedExecution } from "../../src/components/GuardedExecution";
import { Guide, GuideActionProvider, useGuideActions } from "../../src/components/studio/Guide";
import "../../src/styles.css";
import "../../src/workflow.css";
import "../../src/studio.css";

const params = new URLSearchParams(location.search);
const kind = params.get("kind") === "drives" ? "drives" : "firmware";
function Harness() {
  const actions = useGuideActions();
  const [device, setDevice] = useState("fixture-server");
  const [mounted, setMounted] = useState(true);
  const name = device === "fixture-server" ? "Server Alpha" : "Server Beta";
  return <GuideActionProvider value={actions.value}>
    <Guide eyebrow="Fixture guide" say="Fixture sentence." actionRef={actions.ref} />
    <p><button type="button" onClick={() => setDevice(value => value === "fixture-server" ? "fixture-other" : "fixture-server")}>Switch fixture server</button>
      <button type="button" onClick={() => setMounted(value => !value)}>Toggle fixture mount</button><span data-testid="device">{device}</span></p>
    {mounted && <GuardedExecution kind={kind} profileId="fixture-kit" deviceId={device} deviceName={name} hoist />}
  </GuideActionProvider>;
}
createRoot(document.getElementById("root")!).render(<BrowserRouter><div className="sd-frame"><div className="sd-main"><Harness /></div></div></BrowserRouter>);
