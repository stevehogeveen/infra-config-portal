import React, {useState} from "react";
import {createRoot} from "react-dom/client";
import {BrowserRouter} from "react-router-dom";
import {RackConnection} from "../../src/components/RackConnection";
import {SetupJourney} from "../../src/components/SetupJourney";
import type {RackPlan} from "../../src/components/RackPlanner";
import "../../src/styles.css";
import "../../src/workbenchTheme.css";
import "../../src/rackPlanner.css";
import "../../src/workflow.css";
const plan: RackPlan = {revision:1,rack_units:12,equipment:["s","other"].map((id,index)=>({id,device_id:id,name:index?"Second server":"Test server",kind:"server",model:"HPE DL360",position:index+1,height:1,mount:"rack",ports:0,bay_count:10,occupied_bays:[]}))};
function Fixture(){const [selected,onSelect]=useState("s");return <BrowserRouter><div className="app-shell-workbench"><SetupJourney step={1}><RackConnection plan={plan} profileId="fixture" loaded busy={false} error="" selectedId={selected} onSelect={onSelect} devices={[]}/></SetupJourney></div></BrowserRouter>;}
createRoot(document.getElementById("root")!).render(<Fixture/>);
