/* The rack drawing shared by the flight board and the flight plan: a server (drive bays, one LED), a
   switch (ports, one LED), a Windows badge, and the cable between them. `lit` maps leg ids to
   todo | running | done | skipped | stopped. */
function drawRack({ legs = [], equipment = [], phase = "" }) {
  const esc = t => String(t ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const by = Object.fromEntries(legs.map(l => [l.id, l.state]));
  const lamp = ids => ids.some(i => by[i] === "stopped") ? "bad" : ids.some(i => by[i] === "running") ? "run" : ids.every(i => by[i] === "done" || legs.find(l => l.id === i)?.reason === "already_verified") ? "ok" : "";
  const ok = id => by[id] === "done" || legs.find(l => l.id === id)?.reason === "already_verified";
  const server = lamp(["connect", "firmware", "raid", "esxi"]), sw = lamp(["switch"]), vm = lamp(["windows", "acceptance"]);
  const bays = Array.from({ length: 8 }, (_, i) => `<rect class="rk-bay ${ok("raid") ? "on" : ""}" x="${28 + i * 22}" y="121" width="18" height="22" rx="2"/>`).join("");
  const ports = Array.from({ length: 24 }, (_, i) => `<rect class="rk-port ${ok("switch") ? "on" : ""}" x="${26 + (i % 12) * 15}" y="${184 + Math.floor(i / 12) * 11}" width="12" height="8" rx="1"/>`).join("");
  const built = phase === "done" && !legs.some(l => l.reason === "skipped_by_choice") ? `<g transform="rotate(-10 200 26)"><rect class="rk-stamp" x="164" y="14" width="72" height="24" rx="5"/><text class="rk-stamp-text" x="200" y="31" text-anchor="middle" style="font-size:12px">BUILT</text></g>` : "";
  const serverName = (equipment.find(e => e.kind === "server") || equipment.find(e => /dl|server|hpe/i.test(e.name)) || {}).name || "Server (not added yet)";
  const switchName = (equipment.find(e => e.kind === "switch") || equipment.find(e => /cisco|switch|catalyst/i.test(e.name)) || {}).name || "Switch (not added yet)";
  const dim = name => / \(not added yet\)$/.test(name) ? "opacity:.45" : "";
  return `<svg viewBox="0 0 250 236" xmlns="http://www.w3.org/2000/svg">
    <rect class="rk-frame" x="8" y="8" width="234" height="220" rx="10"/>
    <g class="rk-vm ${vm}"><rect x="70" y="22" width="110" height="60" rx="8"/><rect x="82" y="34" width="86" height="30" rx="3" fill="#0b1118"/>
      <text class="rk-text" x="125" y="53" text-anchor="middle">${esc(ok("windows") ? "windows01" : "Windows")}</text><circle class="rk-led ${vm}" cx="125" cy="74" r="4"/></g>
    <path class="rk-cable ${ok("switch") ? "ok" : ""}" d="M125 82 L125 108"/>
    <g style="${dim(serverName)}"><rect class="rk-unit" x="18" y="108" width="214" height="44" rx="4"/>${bays}<circle class="rk-led ${server}" cx="218" cy="132" r="5"/>
      <text class="rk-label" x="22" y="117">${esc(serverName.toUpperCase()).slice(0, 28)}</text></g>
    <path class="rk-cable ${ok("switch") ? "ok" : ""}" d="M38 152 L38 170"/>
    <g style="${dim(switchName)}"><rect class="rk-unit" x="18" y="170" width="214" height="44" rx="4"/>${ports}<circle class="rk-led ${sw}" cx="218" cy="193" r="5"/>
      <text class="rk-label" x="22" y="179">${esc(switchName.toUpperCase()).slice(0, 28)}</text></g>
    ${built}</svg>`;
}
