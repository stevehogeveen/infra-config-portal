import { useEffect, useState } from "react";
import { ArrowUp, Folder, RefreshCw, ExternalLink, Check, Copy } from "lucide-react";
import { api, type FirmwarePackageSource as Source } from "../api";
import "../firmwarePackage.css";
import { MediaDropZone } from "./MediaDropZone";

/** A partial answer (an older backend, a failed read) must not take the page down: lists default to empty. */
function complete<T extends { folders?: unknown[]; files?: unknown[] }>(value: T): T {
  return { ...value, folders: value?.folders ?? [], files: value?.files ?? [] };
}

export function FirmwarePackageSource({profileId, onChange}: {profileId:string; onChange:(source:Source|null)=>void}) {
  const [source,setSource] = useState<Source|null>(null);
  const [folder,setFolder] = useState("");
  const [file,setFile] = useState("");
  const [loading,setBusy] = useState(false);
  const [uploading,setUploading] = useState(false);
  const busy = loading || uploading;
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");
  const [manageOpen,setManageOpen] = useState(false);
  useEffect(() => {
    let active=true;
    setBusy(true); setSource(null); onChange(null);
    api.firmwarePackageSource(profileId).then(raw=>{const value=complete(raw);if(active){setSource(value); onChange(value);}})
      .catch(err=>{if(active)setError(err.message);}).finally(()=>{if(active)setBusy(false);});
    return ()=>{active=false;};
  },[profileId]);
  async function browse(next:string) {
    setBusy(true);setError("");setNotice("");
    try {const value=complete(await api.firmwarePackageSource(profileId,next));setSource(value);onChange(value);setFolder(value.folder);setFile("");}
    catch(err){setError(err instanceof Error?err.message:String(err));}
    finally{setBusy(false);}
  }
  async function select() {
    setBusy(true);setError("");setNotice("");
    try {
      const selected=await api.selectFirmwarePackage(profileId,file);
      const next={...source!,selected,selection_current:true};setSource(next);onChange(next);
      setManageOpen(false);
      setNotice("Package selection saved for this kit. No update approved or installed.");
    }catch(err){setError(err instanceof Error?err.message:String(err));}
    finally{setBusy(false);}
  }
  return <section className="firmware-package-source" aria-label="Firmware package">
    <header><h2>Firmware package</h2><a href={source?.download_url || "https://support.hpe.com/hpesc/public/docDisplay?docId=c03190790&docLocale=en_US&page=GUID-BB4D055A-56A2-4D75-A949-197C4BDC7F2A.html"} target="_blank" rel="noopener noreferrer"><ExternalLink size={16}/>Get HPE SPP</a><a href={source?.documentation_url || "https://support.hpe.com/hpesc/public/docDisplay?docId=c03190790"} target="_blank" rel="noopener noreferrer">HPE release notes and server support</a></header>
    {source?.selected && <div className="selected-media-summary"><Check size={22}/><div><strong>Selected package: {source.selected.file_name}</strong><p>{source.selection_current ? "Server-specific comparison results are below." : "File missing or changed. Inspect and select it again."}</p></div></div>}
    {source && <><details className="media-manager" open={manageOpen || !source.selected} onToggle={event=>{if(source.selected)setManageOpen(event.currentTarget.open);}}><summary>{source.selected ? "Change package or add files" : "Choose your SPP package"}</summary>
      <p>Download the SPP from HPE, then add the ISO below.</p>
      <details><summary>Media folder and Docker settings</summary><dl className="firmware-paths"><div><dt>Folder on this computer</dt><dd>{source.host_root || "Docker host: artifacts/Media in the project folder"}</dd></div><div><dt>Folder inside Docker</dt><dd>{source.root}</dd></div></dl>
      <button type="button" disabled={!source.host_root} onClick={async()=>{try{await navigator.clipboard.writeText(source.host_root!);setNotice("Folder path copied.");}catch{setError("Clipboard unavailable. Select the displayed folder path to copy it.");}}}><Copy size={16}/>Copy folder path</button>
      <details><summary>Use a different folder</summary><p>For another folder on this computer or a network share, mount it into the backend container first. A browser cannot give Docker access to an arbitrary Windows folder.</p><p>Set a read-only Docker bind mount from your folder to <code>/media/firmware</code>, set <code>FIRMWARE_MEDIA_ROOT=/media/firmware</code> and <code>FIRMWARE_MEDIA_HOST_PATH</code> to its host path, then recreate the backend.</p></details>
      </details>
      <MediaDropZone key={profileId} profileId={profileId} folder={source.folder} disabled={busy} onUploaded={()=>browse(source.folder)} onUploading={setUploading}/>
      <form className="firmware-folder-form" onSubmit={event=>{event.preventDefault();void browse(folder);}}><label>Subfolder in the media folder<input aria-label="Media subfolder" value={folder} disabled={busy} onChange={event=>setFolder(event.target.value)} placeholder="Leave blank for the main folder"/></label><button disabled={busy} type="submit"><RefreshCw size={16}/>Scan folder</button></form>
      <div className="firmware-folders">{source.folder && <button disabled={busy} onClick={()=>void browse(source.folder.split("/").slice(0,-1).join("/"))}><ArrowUp size={16}/>Parent folder</button>}{source.folders.map(item=><button disabled={busy} key={item.path} onClick={()=>void browse(item.path)}><Folder size={16}/>{item.name}</button>)}</div>
      {source.warning && <p role="status">{source.warning}</p>}
      {!source.files.length ? <p>No ISO files found in this folder. Copy the downloaded SPP here, then scan again.</p> : <div className="firmware-file-picker"><label>ISO package<select aria-label="ISO package" value={file} disabled={busy} onChange={event=>setFile(event.target.value)}><option value="">Choose an ISO</option>{source.files.map(item=><option key={item.path} value={item.path}>{item.name} ({(item.size_bytes/1024**3).toFixed(2)} GB)</option>)}</select></label><button disabled={!file || busy} onClick={()=>void select()}><Check size={16}/>Inspect and select package</button></div>}
      {source.selected && <details className="firmware-selected"><summary>ISO inspection details</summary><dl><div><dt>ISO volume label</dt><dd>{source.selected.volume_label || "Not provided"}</dd></div><div><dt>Release hint (unverified)</dt><dd>{source.selected.release_hint || "Unknown"}</dd></div></dl><details><summary>Baseline and manifest files found ({source.selected.manifest_files.length})</summary><ul>{source.selected.manifest_files.map(path=><li key={path}>{path}</li>)}</ul></details><p>File inspection only. Use the per-server results for hardware matching and version comparisons.</p></details>}
      </details>
    </>}
    {loading && <p role="status">Reading package metadata...</p>}{error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </section>;
}
