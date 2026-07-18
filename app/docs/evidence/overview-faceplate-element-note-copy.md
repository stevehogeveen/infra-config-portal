# Overview Faceplate Element Copy Evidence

Date: 2026-07-18

Slice: first-click element notes inside the Overview device setup drawer.

Observed operator copy after clicking device faceplate elements:
- Cisco switch port: `Shows what this port should carry and which VLAN lane it belongs to.`
- HPE iLO NIC: `Shows the management address and whether sign-in still needs attention.`
- HPE server drive bay: `Shows this bay's saved RAID role and local datastore plan.`
- NetApp controller port: `Shows how this controller port fits the shared storage path.`

Regression coverage:
- Element note starts hidden until the operator clicks a port, NIC, bay, or controller port.
- Default element note does not contain `proof`, `source`, `device_settings`, `workflow`, `live-proof`, or `read-only`.
- Advanced proof remains hidden by default.

Validation:
- `npm run test:e2e -- --grep "overview faceplate element clicks reveal concise details"`: 1 passed.
- `npm run test:e2e -- --grep "overview device workspace matrix|overview faceplate element clicks reveal concise details|operator button matrix"`: 3 passed.
- `npm run build`: passed.
- `npm run test:e2e`: 79 passed, 4 skipped.
- `git diff --check`: passed.
