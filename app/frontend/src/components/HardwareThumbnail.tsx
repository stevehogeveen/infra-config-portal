import { useId, useRef } from "react";
import { Maximize2, X } from "lucide-react";
import type { PlannedEquipment } from "./RackPlanner";
import serverImage from "../assets/hardware/hpe-server-front.png";
import switchImage from "../assets/hardware/catalyst-front.png";
import upsImage from "../assets/hardware/ups-front.png";
import pduImage from "../assets/hardware/pdu-front.png";
import storageImage from "../assets/hardware/storage-front.png";
import switchSfpImage from "../assets/hardware/catalyst-sfp-front.png";
import eatonImage from "../assets/hardware/eaton-1550-front.png";
import dl380Image from "../assets/hardware/dl380-front.png";
import netappImage from "../assets/hardware/netapp-drives-front.png";
import "../hardwareArt.css";

type Rect = readonly [number, number, number, number];
type Photo = { src: string; width: number; height: number; face: Rect };
const photos: Record<PlannedEquipment["kind"], Photo> = {
  server: { src: serverImage, width: 2172, height: 724, face: [28, 200, 2116, 305] },
  switch: { src: switchImage, width: 2158, height: 729, face: [6, 248, 2146, 204] },
  ups: { src: upsImage, width: 2172, height: 724, face: [10, 153, 2152, 390] },
  pdu: { src: pduImage, width: 2172, height: 724, face: [16, 246, 2140, 187] },
  storage: { src: storageImage, width: 2172, height: 724, face: [35, 187, 2098, 331] }
};
const variants = {
  dl380: { src: dl380Image, width: 2164, height: 727, face: [12, 160, 2140, 371] as Rect },
  netapp: { src: netappImage, width: 2172, height: 724, face: [9, 154, 2154, 393] as Rect },
  eaton: { src: eatonImage, width: 2172, height: 724, face: [24, 247, 2128, 211] as Rect },
  sfp: { src: switchSfpImage, width: 2156, height: 729, face: [6, 246, 2144, 207] as Rect }
};

// Crop in the browser: source images stay intact and carriers remain configurable.
function PhotoCrop({ photo, rect = photo.face }: { photo: Photo; rect?: Rect }) {
  const [x, y, width, height] = rect;
  return <span className="hw-photo"><img src={photo.src} alt="" draggable={false}
    style={{ width: `${photo.width / width * 100}%`, height: `${photo.height / height * 100}%`, left: `${-x / width * 100}%`, top: `${-y / height * 100}%` }} /></span>;
}

export function hardwareName(name: string, kind: PlannedEquipment["kind"]) {
  return kind === "server" && /^(?:hpe?\s+)?ilo$/i.test(name.trim()) ? "HPE server" : name;
}

export function HardwareThumbnail({ item, rack = false }: { item: PlannedEquipment; rack?: boolean }) {
  const bays = Math.max(0, Math.min(24, Math.trunc(item.bay_count || 0)));
  const variant = item.kind === "server" && /\bDL380\b/i.test(item.model) ? "dl380" : item.kind === "storage" && bays > 0 ? "netapp" : item.kind === "ups" && /eaton/i.test(item.model) ? "eaton" : item.kind === "switch" && item.uplink_ports === 4 ? "sfp" : null;
  const photo = variant ? variants[variant] : photos[item.kind];
  const verticalDrives = variant === "dl380" || variant === "netapp";
  const ports = item.ports === 48 ? 48 : item.ports === 24 ? 24 : 0;
  const rows = verticalDrives ? 1 : bays > 5 ? 2 : 1;
  const filled: Rect = variant === "dl380" ? [162, 182, 64, 340] : variant === "netapp" ? [106, 192, 64, 322] : [191, 224, 347, 131];
  const blank: Rect = variant === "dl380" ? [1100, 182, 65, 340] : variant === "netapp" ? [1099, 192, 64, 322] : [191, 374, 347, 115];
  return <span className={`hw-art hw-${item.kind} ${variant ? `hw-${variant}` : ""} ${rack ? "hw-in-rack" : ""}`} data-ports={ports} data-bays={bays} aria-hidden="true">
    <PhotoCrop photo={photo} />
    {(item.kind === "server" || variant === "netapp") && <span className="hw-drive-field">
      {bays ? <span className="hw-bays" data-testid={rack ? `bays-${item.id}` : undefined} style={{ gridTemplateColumns: `repeat(${Math.ceil(bays / rows)}, minmax(0, 1fr))`, gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))` }}>
        {Array.from({ length: bays }, (_, index) => {
          const occupied = item.occupied_bays.includes(index + 1);
          return <span className={`hw-bay ${occupied ? "occupied" : "empty"}`} data-bay={index + 1} key={index}>
            <PhotoCrop photo={photo} rect={occupied ? filled : blank} />
            <span className="hw-bay-number">{index + 1}</span>
          </span>;
        })}
      </span> : <PhotoCrop photo={photos.ups} rect={[400, 186, 830, 315]} />}
    </span>}
    {item.kind === "switch" && <span className="hw-network-field">
      <PhotoCrop photo={photos.switch} rect={[1620, 299, 350, 75]} />
      <span className="hw-ports" data-testid={rack ? `ports-${item.id}` : undefined} style={{ width: ports === 48 ? "100%" : "50%", gridTemplateColumns: `repeat(${ports === 48 ? 24 : 12}, minmax(0, 1fr))` }}>
        {Array.from({ length: ports }, (_, index) => <i className="hw-port" key={index} data-port={index + 1}>
          <PhotoCrop photo={photos.switch} rect={[262, 297, 44, 46]} />
          <span>{index + 1}</span>
        </i>)}
      </span>
    </span>}
    {variant === "sfp" && <span className="hw-sfp-ports">{Array.from({ length: 4 }, (_, index) => <span className="hw-sfp-port" data-sfp={index + 1} key={index}><PhotoCrop photo={photo} rect={[1666, 346, 64, 48]} /></span>)}</span>}
  </span>;
}

export function HardwarePreview({ item }: { item: PlannedEquipment }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  return <>
    <button type="button" className="hw-preview-button" aria-label="Enlarge equipment image" title="Enlarge equipment image" onClick={() => dialog.current?.showModal()}>
      <HardwareThumbnail item={item} /><Maximize2 size={17} />
    </button>
    <dialog ref={dialog} className="hw-detail-dialog" aria-labelledby={titleId} onClick={event => { if (event.target === event.currentTarget) dialog.current?.close(); }}>
      <header><div><h2 id={titleId}>{item.name}</h2><p>{item.model || item.kind.toUpperCase()} / Planned appearance</p></div><button type="button" aria-label="Close equipment image" title="Close" onClick={() => dialog.current?.close()}><X size={22} /></button></header>
      <HardwareThumbnail item={item} />
      <footer><span>Hardware not verified</span>{(item.kind === "server" || item.kind === "storage") && <span>{item.bay_count ? `${item.occupied_bays.filter(bay => bay <= item.bay_count).length} drives / ${item.bay_count} bays planned` : "Drive configuration unknown"}</span>}{item.kind === "switch" && <span>{item.ports ? `${item.ports} Ethernet / ${item.uplink_ports || 0} SFP ports planned` : "Port count unknown"}</span>}</footer>
    </dialog>
  </>;
}
