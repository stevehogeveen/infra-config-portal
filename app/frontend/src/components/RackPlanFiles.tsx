import { useId, useRef, useState } from "react";
import { Save, FolderOpen, X } from "lucide-react";
import type { RackPlan } from "./RackPlanner";
import { exportRackFile, importRackFile, MAX_RACK_FILE_BYTES } from "../rackPlanFiles";
import "../rackPlanFiles.css";

type SavePicker = (options: { id: string; suggestedName: string; types: { description: string; accept: Record<string, string[]> }[] }) => Promise<{ name: string; createWritable: () => Promise<{ write: (data: Blob) => Promise<void>; close: () => Promise<void>; abort: () => Promise<void> }> }>;

export function RackPlanFiles({ plan, defaultName, disabled, invalid, dirty, validate, onLoad, onMessage, onError, onPersist, onPrepare }: {
  plan: RackPlan; defaultName: string; disabled: boolean; invalid: boolean; dirty: boolean;
  validate: (plan: RackPlan) => string | null; onLoad: (plan: RackPlan) => void;
  onMessage: (message: string) => void; onError: (error: string) => void;
  onPersist: () => Promise<boolean>;
  onPrepare?: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const heading = useId();
  const [name, setName] = useState(defaultName);
  const [reading, setReading] = useState(false);
  const [fileError, setFileError] = useState("");
  const [saving, setSaving] = useState(false);
  const picker = (window as Window & { showSaveFilePicker?: SavePicker }).showSaveFilePicker;
  const [location, setLocation] = useState(picker ? "choose" : "browser");
  async function saveCopy() {
    const problem = validate(plan);
    if (problem) { setFileError(problem); return; }
    const blob = new Blob([JSON.stringify(exportRackFile(plan, name), null, 2)], { type: "application/json" });
    const filename = `rack-${name.trim().replace(/[^a-z0-9_-]+/gi, "-").slice(0, 80) || "plan"}.rack-plan.json`;
    let picked = false;
    setSaving(true); setFileError("");
    try {
      if (location === "choose") {
        if (!picker) throw new Error("This browser cannot open a save-location picker.");
        const handle = await picker.call(window, { id: "rack-plans", suggestedName: filename, types: [{ description: "Rack plan", accept: { "application/json": [".json"] } }] });
        picked = true;
        const stream = await handle.createWritable();
        try { await stream.write(blob); await stream.close(); }
        catch (error) { await stream.abort().catch(() => {}); throw error; }
      } else {
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url; link.download = filename;
        document.body.appendChild(link); link.click(); link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      if (!await onPersist()) {
        setFileError("The copy was saved or sent to your browser, but the active kit could not be saved. Your draft is still here. Close this window to review the server error.");
        return;
      }
      dialog.current?.close(); onError("");
      onMessage(`Rack plan saved. ${location === "choose" ? "Copy saved to your chosen location." : "Copy sent to your browser's download location."}`);
    } catch (error) {
      if (!picked && error instanceof DOMException && error.name === "AbortError") return;
      setFileError(error instanceof Error ? error.message : String(error));
    } finally { setSaving(false); }
  }
  async function readFile(file?: File) {
    if (!file) return;
    setReading(true);
    try {
      if (file.size > MAX_RACK_FILE_BYTES) throw new Error("Rack plan files must be smaller than 1 MB.");
      const imported = importRackFile(await file.text(), plan, validate);
      if (!window.confirm(`Load "${imported.name}" and replace the current rack layout?${dirty ? " Unsaved changes will be replaced." : ""} Saved connection records will be kept.`)) return;
      onLoad(imported.plan); setName(imported.name); onError("");
      onMessage(`Loaded ${imported.name}. Review the layout, then save a copy to keep the active kit.`);
    } catch (error) { onError(error instanceof Error ? error.message : String(error)); }
    finally { setReading(false); if (fileInput.current) fileInput.current.value = ""; }
  }
  return <div className="rack-file-actions" role="group" aria-label="Rack plan files">
    <button type="button" disabled={disabled || invalid || reading || saving} onClick={() => { onPrepare?.(); setFileError(""); dialog.current?.showModal(); }}><Save size={16} />Save a copy</button>
    <button type="button" disabled={disabled || reading || saving} onClick={() => { onPrepare?.(); fileInput.current?.click(); }}><FolderOpen size={16} />{reading ? "Loading plan" : "Load plan"}</button>
    <input ref={fileInput} type="file" accept=".json,application/json" aria-label="Rack plan file" hidden onChange={event => void readFile(event.target.files?.[0])} />
    <dialog ref={dialog} className="rack-file-dialog" aria-labelledby={heading} onCancel={event => { if (saving) event.preventDefault(); }} onClick={event => { if (!saving && event.target === event.currentTarget) dialog.current?.close(); }}>
      <form onSubmit={event => { event.preventDefault(); if (!saving) void saveCopy(); }}>
        <header><h2 id={heading}>Save a rack plan copy</h2><button type="button" disabled={saving} title="Close" aria-label="Close save copy" onClick={() => dialog.current?.close()}><X size={20} /></button></header>
        <label>Plan name<input autoFocus required maxLength={120} disabled={saving} value={name} onChange={event => setName(event.target.value)} /></label>
        <label>Save location<select aria-label="Save location" value={location} disabled={saving} onChange={event => setLocation(event.target.value)}><option value="choose" disabled={!picker}>Choose folder and filename</option><option value="browser">Browser download location</option></select></label>
        {!picker && <p>Folder selection is unavailable in this browser.</p>}
        <p>{plan.rack_units}U / {plan.equipment.length} equipment items / No credentials</p>
        {fileError && <p role="alert">{fileError}</p>}
        <footer><button type="button" disabled={saving} onClick={() => dialog.current?.close()}>Cancel</button><button type="submit" disabled={!name.trim() || saving}><Save size={16} />{saving ? "Saving" : "Save"}</button></footer>
      </form>
    </dialog>
  </div>;
}
