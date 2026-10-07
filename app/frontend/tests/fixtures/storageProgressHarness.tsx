import React, {useState} from "react";
import {createRoot} from "react-dom/client";
import {RaidOperation} from "../../src/components/RaidOperation";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/workflow.css";

function Harness() {
  const [next,setNext]=useState("");
  return <main className="app-shell-workbench" style={{maxWidth:1100,margin:"0 auto",padding:16}}>
    <h2>Drives &amp; RAID</h2>
    <RaidOperation profileId="fixture" deviceId="fixture" revision={0} disabled={false}
      onActive={()=>{}} onBusy={()=>{}} onVerified={()=>{}} onContinue={setNext} onRecovery={()=>setNext("recovery")}/>
    {next&&<p role="status">Next selected: {next}</p>}
  </main>;
}
createRoot(document.getElementById("root")!).render(<Harness/>);
