import { useEffect, useRef, useState } from "react";
import { Upload, X } from "lucide-react";
import { api } from "../api";

// kind "vm": a VM export for the ESXi host: an .ova, or an .ovf with its .vmdk and .mf files.
const KINDS = {
  iso: { exts: [".iso"], limit: 20 * 1024 ** 3, noun: "ISO", hint: "Choose an ISO file between 1 byte and 20 GB.", accept: ".iso", drop: "an ISO", choose: "ISO file" },
  vm: { exts: [".ova", ".ovf", ".vmdk", ".mf", ".nvram", ".cert"], limit: 128 * 1024 ** 3, noun: "file", hint: "Choose an .ova, or the files of an .ovf export (.ovf, .vmdk, .nvram, .mf), up to 128 GB each.", accept: ".ova,.ovf,.vmdk,.mf,.nvram,.cert", drop: "an OVA or OVF file", choose: "OVA or OVF file" },
} as const;

export function MediaDropZone({profileId, folder, disabled, onUploaded, onUploading, kind = "iso"}: {profileId:string;folder:string;disabled:boolean;onUploaded:()=>Promise<void>;onUploading:(busy:boolean)=>void;kind?:"iso"|"vm"}) {
  const spec = KINDS[kind];
  const input=useRef<HTMLInputElement>(null);
  const cancel=useRef<(()=>void)|null>(null);
  const [dragging,setDragging]=useState(false);
  const [uploading,setUploading]=useState(false);
  const [percent,setPercent]=useState(0);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  useEffect(()=>()=>cancel.current?.(),[]);
  async function upload(files:FileList|null) {
    if(disabled || cancel.current || !files?.length)return;
    setError("");setMessage("");setDragging(false);
    if(files.length!==1){setError(`Choose one ${spec.noun} at a time.`);return;}
    const file=files[0];
    if(!spec.exts.some(ext=>file.name.toLowerCase().endsWith(ext)) || file.size===0 || file.size>spec.limit){setError(spec.hint);return;}
    setUploading(true);onUploading(true);setPercent(0);
    const transfer=api.uploadMedia(profileId,folder,file,setPercent,kind);
    cancel.current=transfer.cancel;
    try{await transfer.promise;await onUploaded();setMessage(`${file.name} uploaded. Select it below to inspect it.`);}
    catch(err){setError(err instanceof Error?err.message:String(err));}
    finally{cancel.current=null;setUploading(false);onUploading(false);if(input.current)input.current.value="";}
  }
  return <div className="media-upload">
    <div className={`media-drop-zone${dragging?" dragging":""}`} onDragOver={event=>{event.preventDefault();if(!uploading&&!disabled)setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={event=>{event.preventDefault();setDragging(false);void upload(event.dataTransfer.files);}}>
      <Upload size={26}/><strong>Drop {spec.drop} here</strong><span>Destination: {folder || "Main media folder"}</span>
      <button type="button" disabled={disabled||uploading} onClick={()=>input.current?.click()}><Upload size={16}/>Choose {spec.choose}</button>
      <input ref={input} type="file" accept={spec.accept} aria-label={`Upload ${spec.choose}`} hidden onChange={event=>void upload(event.target.files)}/>
    </div>
    {uploading && <div className="media-upload-progress"><progress max={100} value={percent} aria-label="ISO upload progress"/><span role="status">{percent===100?"Finishing upload...":`Uploading ${percent}%`}</span><button type="button" onClick={()=>cancel.current?.()}><X size={16}/>Cancel upload</button></div>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
  </div>;
}
