# Rack Hardware Visuals

## Planned Equipment

The hardware picker shares one catalog (`frontend/src/hardwareCatalog.ts`) across
the guided setup and rack editor. Equipment remains in the existing rack-plan
API and browser-draft flow; changing its appearance does not contact hardware.

| Preset | Rack Space | Front Configuration |
| --- | --- | --- |
| HPE DL360 | 1U | Up to 10 SFF drive bays |
| HPE DL380 | 2U | Up to 24 SFF drive bays |
| Cisco Catalyst 9300 | 1U | 24 Ethernet ports by default; 48 available; optional 4-port SFP module |
| Rackmount UPS | 2U | Existing black UPS design |
| Eaton 1550 | 1U | Representative Eaton 5P 1550 rackmount design |
| PDU | 1U or side mount | Existing eight-outlet design |
| NetApp storage | 2U | 24 SFF drive bays |

DL360 and DL380 offer Gen10 Plus and Gen11 model choices. These are capacity
limits for planning, not a guarantee that a particular chassis has the necessary
backplane, cage, controller, firmware, or supported drives. New server/storage
plans start with empty bays. The picker shows a populated example; the rack and
detail view show the user's occupied-bay selection. A drive can be added or removed
individually without removing its bay.

`uplink_ports` is stored alongside the Ethernet port count in the existing layout
JSON; old plans default to no selected SFP module. Storage now supports the same
bay/occupancy fields as servers. Named DL360/DL380 dimensions and capacity limits
are validated by both the editor and save API. Legacy layouts remain readable;
incompatible old model/height combinations require correction before saving.
No database migration is required.

## Artwork And References

The PNG files in `frontend/src/assets/hardware/` are original AI-generated,
photorealistic illustrations created on 2026-09-11 after studying the references
below. They are not vendor product photographs or exact SKU identification.
Gen10 Plus and Gen11 share representative chassis materials; generation-specific
bezel, connector and label details are not authoritative. The Eaton depiction is
based on the 1U 5P1550IR, not every regional 1550 VA variant. The NetApp depiction
is a generic exposed 24-SFF front, not a claim about an installed controller model.

- [Cisco Catalyst 9300 front panels and network modules](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst9300/hardware/install/b_c9300_hig/Product-overview.html)
- [HPE DL360 Gen11](https://www.hpe.com/uk/en/compute/hpe-proliant-compute/dl360-gen11.html)
- [HPE DL360 drive-box configurations](https://support.hpe.com/hpesc/public/docDisplay?docId=sd00002444en_us&docLocale=en_US&page=GUID-DF9B0BF4-CE01-4C22-8FD2-A064BA9C8930.html)
- [HPE DL380 Gen11 configurations](https://www.hpe.com/pt/en/collaterals/collateral.a50004307enw.html)
- [Eaton 5P1550IR](https://www.eaton.com/gb/en-gb/skuPage.5P1550IR.html)
- [NetApp AFF A250 reference](https://www.netapp.com/blog/new-nvme-entry-system-aff-a250/)

`HardwareThumbnail.tsx` crops the full-resolution PNGs in CSS, masks the original
port/drive fields, and composes the exact requested count from photographed-style
carrier/port tiles. Do not rely on the number of bays in an underlying generated
image: generated geometry is not a source of truth. Unknown drive configurations
show a closed/vented front rather than invented drive occupancy. Preview images
never establish power, connectivity, firmware health, or readiness.

The inspector's enlarge control opens the same configurable front in a native
dialog with keyboard dismissal and focus return. Images are decorative; equipment
names, planned capacities, and editing controls remain accessible text.
Rack-unit pixels scale with the rack's available width, including drag/drop hit
testing. Narrow elevations omit the tiny chassis name strip; selection still
exposes the full name in the inspector and each equipment button's accessible name.

## Verification

- Frontend build: `npm run build` in `app/frontend`.
- Browser coverage: `npm run test:e2e -- tests/hardware-art.spec.ts tests/rack-planner.spec.ts tests/setup-journey.spec.ts --workers=1`.
- API coverage: `python -m pytest tests/test_rack_plans.py -q` in `app/backend`.

Browser tests cover exact 24/48 Ethernet counts, four SFP ports, drive occupancy,
model limits, persistence, drag/drop, desktop/mobile screenshots, image loading,
and the enlarged preview. Backend tests use an isolated in-memory database.
