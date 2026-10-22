/** Drive-bay helpers shared by the Disks & RAID page and the RAID plan editor. */

export function bayOrder(location: string) {
  const parts = location.split(":");
  const box = Number(parts[1]), bay = Number(parts[2]);
  return parts.length === 3 && Number.isInteger(box) && Number.isInteger(bay) ? box * 1000 + bay : Number.MAX_SAFE_INTEGER;
}
/**
 * The iLO lists only occupied bays. When every reported bay sits in one drive cage (the same box
 * number), bay numbers run through that cage, so the numbers in between are empty slots. Nothing
 * past the highest reported bay is guessed.
 */
export function gapBays(locations: string[]) {
  const parsed = locations.map(location => location.split(":")).filter(parts => parts.length === 3 && /^\d+$/.test(parts[1]) && /^\d+$/.test(parts[2]));
  if (!parsed.length || parsed.length !== locations.length || new Set(parsed.map(parts => parts[1])).size !== 1) return [];
  const numbers = new Set(parsed.map(parts => Number(parts[2])));
  const high = Math.max(...numbers);
  const gaps: string[] = [];
  for (let bay = 1; bay < high; bay++) if (!numbers.has(bay)) gaps.push(`?:${parsed[0][1]}:${bay}`);
  return gaps;
}

export function bayNumber(location: string) {
  const last = location.split(":").pop();
  return last && /^\d+$/.test(last) ? last : location;
}

export function size(bytes: number) {
  if (!bytes) return "";
  return bytes >= 1e12 ? `${(bytes / 1e12).toFixed(bytes >= 1e13 ? 0 : 1)} TB` : bytes < 1e10 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e9)} GB`;
}

/* The iLO reports each disk and logical drive twice: once through HPE's storage view (with the bay)
   and once through standard Redfish (without it). Show one of each, preferring the one with a bay. */
export function merged<D extends { location: string; model?: string | null }, V extends { name: string; raid: string; bays?: string[] | null }>(drives: D[], volumes: V[]) {
  // Each located drive has at most one bay-less twin of the same model. Bay-less drives beyond
  // that count are real drives the iLO could not place, so they still show.
  const twins = new Map<string, number>();
  for (const drive of drives) if (drive.location && drive.location !== "Unknown bay") twins.set(drive.model ?? "", (twins.get(drive.model ?? "") ?? 0) + 1);
  const withBays = new Set(volumes.filter(volume => volume.bays?.length).map(volume => volume.name + "|" + volume.raid));
  return {
    drives: drives.filter(drive => {
      if (drive.location && drive.location !== "Unknown bay") return true;
      const left = twins.get(drive.model ?? "") ?? 0;
      if (left > 0) { twins.set(drive.model ?? "", left - 1); return false; }
      return true;
    }),
    volumes: volumes.filter(volume => volume.bays?.length || !withBays.has(volume.name + "|" + volume.raid)),
  };
}
