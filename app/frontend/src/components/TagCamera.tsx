import { useEffect, useRef, useState } from "react";
import { Camera, Check, X, ZoomIn, ZoomOut } from "lucide-react";

/*
 * Camera help for the iLO pull-out tag: hold the tag up to the PC camera, take a photo, and the
 * browser's own text and barcode readers (when this browser has them) pick out the iLO name, user,
 * password and serial. Nothing is filled until the operator presses Use. Without a text reader the
 * frozen photo stays on screen, zoomable, to type from. The photo never leaves this browser tab and
 * the camera is switched off when the window closes.
 */

export type TagFields = { host?: string; username?: string; password?: string; serial?: string };

const after = (lines: string[], label: RegExp) => {
  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(label);
    if (!match) continue;
    const rest = lines[i].slice((match.index ?? 0) + match[0].length).replace(/^[\s:.\-=]+/, "").trim();
    if (rest) return rest.split(/\s+/)[0];
    const next = (lines[i + 1] || "").trim();
    if (next) return next.split(/\s+/)[0];
  }
  return undefined;
};

/** Pick the iLO details out of what a text reader saw on an HPE pull-out tag. Pure; tested directly. */
export function parseIloTag(text: string, barcodes: string[] = []): TagFields {
  const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const fields: TagFields = {};
  const dns = after(lines, /\bDNS\s*Name\b/i) || lines.join(" ").match(/\bILO[A-Z0-9]{8,14}\b/i)?.[0];
  if (dns && /^[A-Za-z0-9][A-Za-z0-9.-]{2,62}$/.test(dns)) fields.host = dns;
  const user = after(lines, /\bUser\s*(?:Name)?\b/i);
  if (user && /^[A-Za-z0-9._-]{1,32}$/.test(user)) fields.username = user;
  const password = after(lines, /\bPassword\b/i);
  if (password && /^[A-Za-z0-9]{6,16}$/.test(password)) fields.password = password;
  const serial = after(lines, /\bSerial\s*(?:Number|No\.?)?\b|\bS\/N\b/i) || barcodes.find(code => /^[A-Z0-9]{10}$/.test(code));
  if (serial && /^[A-Z0-9]{8,14}$/i.test(serial)) fields.serial = serial.toUpperCase();
  return fields;
}

type Detector = { detect: (source: CanvasImageSource) => Promise<Array<{ rawText?: string; rawValue?: string }>> };
const textDetector = (): Detector | null => { const T = (window as unknown as { TextDetector?: new () => Detector }).TextDetector; try { return T ? new T() : null; } catch { return null; } };
const barcodeDetector = (): Detector | null => { const B = (window as unknown as { BarcodeDetector?: new () => Detector }).BarcodeDetector; try { return B ? new B() : null; } catch { return null; } };

export function TagCamera({ onUse, onClose }: { onUse: (fields: TagFields) => void; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [state, setState] = useState<"starting" | "live" | "photo" | "no-camera">("starting");
  const [found, setFound] = useState<TagFields | null>(null);
  const [reader, setReader] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState("");
  const stop = () => { stream.current?.getTracks().forEach(track => track.stop()); stream.current = null; };
  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal();
    let cancelled = false;
    (async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("This browser cannot use a camera here.");
        const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } }, audio: false });
        if (cancelled) { media.getTracks().forEach(track => track.stop()); return; }
        stream.current = media;
        if (video.current) { video.current.srcObject = media; await video.current.play().catch(() => undefined); }
        setState("live");
      } catch (err) {
        if (!cancelled) { setState("no-camera"); setError(err instanceof Error && err.name === "NotAllowedError" ? "The camera was not allowed. Allow it in the browser's address bar, or type the details." : "No camera was found. Type the details from the tag."); }
      }
    })();
    return () => { cancelled = true; stop(); };
  }, []);
  async function snap() {
    const v = video.current, c = canvas.current;
    if (!v || !c || !v.videoWidth) return;
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d")!.drawImage(v, 0, 0);
    stop();
    setState("photo");
    const text = textDetector(), codes = barcodeDetector();
    setReader(!!text);
    try {
      const words = text ? (await text.detect(c)).map(item => item.rawText || "").join("\n") : "";
      const values = codes ? (await codes.detect(c)).map(item => item.rawValue || "") : [];
      setFound(parseIloTag(words, values));
    } catch { setFound({}); }
  }
  const close = () => { stop(); onClose(); };
  const labels: Array<[keyof TagFields, string]> = [["host", "iLO name"], ["username", "User"], ["password", "Password"], ["serial", "Serial"]];
  const any = found && labels.some(([key]) => found[key]);
  return <dialog ref={dialog} className="inst tc-dialog" aria-label="Read the iLO tag" onCancel={event => { event.preventDefault(); close(); }}>
    <header className="inst-h">
      <span className="inst-icon"><Camera size={22} aria-hidden="true" /></span>
      <div><h2>Read the iLO tag</h2><p>Pull the tag out of the server's front and hold it up to the camera.</p></div>
      <button type="button" aria-label="Close camera" onClick={close}><X size={20} /></button>
    </header>
    <div className="inst-body"><section className="inst-main">
      <div className="tc-view" style={{ display: state === "live" ? undefined : "none" }}><video ref={video} muted playsInline aria-label="Camera view" /></div>
      <div className="tc-view tc-photo" style={{ display: state === "photo" ? undefined : "none" }}><canvas ref={canvas} aria-label="Photo of the tag" style={{ transform: `scale(${zoom})` }} /></div>
      {state === "starting" && <p role="status">Starting the camera…</p>}
      {state === "no-camera" && <p className="fw-stop" role="alert">{error}</p>}
      {state === "photo" && <>
        <div className="tc-zoom"><button type="button" className="secondary-action" aria-label="Zoom out" onClick={() => setZoom(z => Math.max(1, z - 0.5))}><ZoomOut size={15} /></button>
          <button type="button" className="secondary-action" aria-label="Zoom in" onClick={() => setZoom(z => Math.min(4, z + 0.5))}><ZoomIn size={15} /></button></div>
        {any ? <dl className="ei-summary" aria-label="Read from the tag">{labels.filter(([key]) => found![key]).map(([key, label]) =>
          <div key={key}><dt>{label}</dt><dd>{key === "password" ? "•".repeat(found!.password!.length) + " (read)" : found![key]}</dd></div>)}</dl>
          : <p className="ex-hint">{reader ? "Nothing readable was found. Try again closer and steadier, or type the details from the photo." : "This browser has no built-in text reader, so type the details from the photo (zoom in if needed)."}</p>}
      </>}
    </section></div>
    <footer className="inst-f">
      <button type="button" className="secondary-action" onClick={close}>Cancel</button>
      <span className="inst-grow" />
      {state === "live" && <button type="button" className="primary-action" onClick={() => void snap()}><Camera size={16} aria-hidden="true" />Take photo</button>}
      {state === "photo" && any && <button type="button" className="primary-action" onClick={() => { const fields = found!; close(); onUse(fields); }}><Check size={16} aria-hidden="true" />Use these details</button>}
    </footer>
  </dialog>;
}
