import {useEffect,useRef,useState} from 'react';
import {Power, RefreshCw} from 'lucide-react';
import {api} from '../api';

type Review = Awaited<ReturnType<typeof api.previewResetShutdown>>;

export function ShutdownForReset({profileId,deviceId,disabled,onBusy,context="reset",onPowerOff,initialPower,initialPowerAt}:{profileId:string;deviceId:string;disabled:boolean;onBusy:(value:boolean)=>void;context?:"reset"|"erase";onPowerOff?:()=>void;initialPower?:string;initialPowerAt?:number}) {
  const [review,setReview]=useState<Review|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [error,setError]=useState('');
  const [phrase,setPhrase]=useState('');
  const [ack,setAck]=useState(false);
  const [submitted,setSubmitted]=useState(false);
  const [power,setPower]=useState<{power:string;pending_changes?:boolean;at:number}|null>(()=>initialPower&&initialPowerAt?{power:initialPower,at:initialPowerAt}:null);
  const [checking,setChecking]=useState(false);
  const [monitor,setMonitor]=useState(false);
  const [now,setNow]=useState(Date.now());
  const mounted=useRef(true);
  const reading=useRef(false);
  useEffect(()=>{if(context==='erase')void preview(false);},[profileId,deviceId,context]);
  useEffect(()=>{onBusy(busy||checking);},[busy,checking,onBusy]);
  useEffect(()=>{mounted.current=true;const timer=setInterval(()=>setNow(Date.now()),15000);return()=>{mounted.current=false;clearInterval(timer);};},[]);
  async function readPower(){
    if(reading.current)return false;
    reading.current=true;setChecking(true);
    try{
      const state=await api.resetPowerState(profileId,deviceId);
      if(!mounted.current)return false;
      setPower({...state,at:Date.now()});setNow(Date.now());setError('');
      if(state.power==='Off'){setMonitor(false);setMessage(state.pending_changes?'Server is off, but pending storage changes need review.':context==='erase'?'Server is off. Refreshing erase readiness.':'Server is off. You can now review the controller reset below.');onPowerOff?.();}
      return state.power==='Off';
    }catch(e){if(mounted.current){setPower(null);setError(`Power state unavailable: ${e instanceof Error?e.message:String(e)} No additional power request was sent.`);}return false;}
    finally{reading.current=false;if(mounted.current)setChecking(false);}
  }
  useEffect(()=>{
    if(!monitor)return;
    let active=true;
    let timer:ReturnType<typeof setTimeout>;
    const started=Date.now();
    async function poll(){
      const off=await readPower();
      if(!active||off)return;
      if(Date.now()-started>=600000){setMonitor(false);setMessage('Power monitoring stopped after ten minutes. Check power state again or review the forced power-off fallback. No power request was repeated.');return;}
      timer=setTimeout(()=>void poll(),10000);
    }
    void poll();
    return()=>{active=false;clearTimeout(timer);};
  },[monitor,profileId,deviceId]);
  function working(value:boolean){setBusy(value);onBusy(value);}
  async function preview(force:boolean){
    working(true);setError('');setReview(null);setPhrase('');setAck(false);setSubmitted(false);
    try{setReview(await api.previewResetShutdown(profileId,deviceId,force));}
    catch(e){setError(e instanceof Error?e.message:String(e));}finally{working(false);}
  }
  async function check(){
    await readPower();
  }
  async function apply(){
    if(!review||submitted)return;
    working(true);setSubmitted(true);setError('');setPower(null);
    try{setMessage((await api.applyResetShutdown(profileId,deviceId,review.preview_id,phrase)).message);}
    catch(e){setError(`${e instanceof Error?e.message:String(e)} Check power state before doing anything else.`);}finally{working(false);setMonitor(true);}
  }
  return <section className="shutdown-workflow" aria-label={context==='erase'?'Shutdown before disk erasure':'Shutdown before storage reset'}>
    {context==="reset"&&<h4>1. Shut down the server</h4>}
    <p>The running OS must stop before {context==='erase'?'disk erasure':'storage reset'}. No array is deleted by these power controls.</p>
    <div className="shutdown-power" role="status" aria-label="Observed server power">
      <Power size={20}/><div><strong>Server power: {power?(now-power.at>60000?'Last observed '+power.power:power.power):checking?'Checking...':'Unknown'}</strong>
      <small>{checking?'Reading iLO...':power?`Read ${new Date(power.at).toLocaleTimeString()}`:'Not checked in this view'}{monitor?' · Monitoring shutdown':''}</small></div>
    </div>
    <div className="raid-operation-actions">
      {!review&&!submitted&&<button className="secondary-action" disabled={disabled||busy||checking||monitor} onClick={()=>void preview(false)}><Power size={16}/>Shut down server...</button>}
      {!monitor&&(!review||submitted)&&<button className="secondary-action" disabled={disabled||busy||checking} onClick={()=>void check()}><RefreshCw size={16}/>Check power state</button>}
    </div>
    {submitted&&power?.power!=='Off'&&<details><summary>Server still running?</summary><p>Forced power-off can interrupt writes and corrupt data. It requires a previous shutdown request, a two-minute wait, and separate confirmation. It is never automatic.</p><button className="secondary-action" disabled={disabled||busy||checking} onClick={()=>void preview(true)}>Review forced power-off</button></details>}
    {busy&&<p role="status">Reading or submitting this server's power operation...</p>}
    {message&&!monitor&&<p role="status">{message}</p>}{error&&<p role="alert" className="workflow-alert">{error}</p>}
    {monitor&&<p className="storage-live-progress" role="status">Shutdown requested. Waiting for iLO to confirm power is off. Checking automatically; no disks are being erased.</p>}
    {review&&!submitted&&<div>
      <h4>{review.force?'Confirm forced power-off':'Confirm shutdown request'}: {review.name}</h4>
      <p>iLO action: {review.payload.ResetType}. {review.payload.ResetType==='PushPowerButton'?'This simulates a momentary power-button press; the OS may not respond.':''}</p>
      {!!review.blockers.length&&<ul className="workflow-pending">{review.blockers.map(b=><li key={b}>{b}</li>)}</ul>}
      <fieldset className="shutdown-confirmations" disabled={disabled||busy||checking||submitted||!review.apply_enabled}>
        <label className="workflow-checkbox"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>I approve downtime on this server and accept possible data loss{review.force?' from forced power-off':''}.</label>
        <label className="workflow-field">Type {review.confirmation}<input aria-label="Shutdown confirmation phrase" autoComplete="off" value={phrase} onChange={e=>setPhrase(e.target.value)}/></label>
        <div className="raid-operation-actions shutdown-submit"><button className="primary-action" disabled={!ack||phrase!==review.confirmation} onClick={()=>void apply()}><Power size={16}/>{review.force?'Confirm forced power-off':'Send shutdown request'}</button></div>
      </fieldset>
    </div>}
    {context==='reset' && <><h4>2. Reset storage, then verify</h4>
    <p>Once power is confirmed Off, review the controller reset below. After staging, use Start server and verify RAID in the operation status above. Do not create replacement arrays until reset verification completes.</p></>}
  </section>;
}
