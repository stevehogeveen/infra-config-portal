# Lab Builder roadmap (agreed 2026-10-15)

The operator asked for every idea from the Claude + Codex brainstorm except the talking guide.
Each phase ships tested and reviewed (Codex reviews the diff) before the next starts.

## Phase 1 - quick wins (done 2026-10-15)
- **Done notifications**: bell in the top bar; when on, a desktop notification and a chime when a
  long job (firmware, RAID, ESXi, Windows, switch setup) finishes or needs attention.
- **What am I waiting for**: running jobs show elapsed time and the current phase.
- **Find this exact box**: blink the server's blue ID light from the app; serial number shown
  next to the rack image. (Indicator LED only; recorded in history.)
- **Labels with QR codes**: printable label sheet per device (name, model, serial, addresses, QR).
- **Pick up where you left off**: My Rack opens with a "resume" card for anything running or
  stopped mid-way, before suggesting anything new.

## Phase 2 - bigger features (done 2026-10-15)
- **Health on the rack**: temperatures, fans and power supplies from iLO painted on the rack.
- **Cable map**: switch MAC table / CDP-LLDP neighbours matched to server NIC MACs; cables drawn
  on the rack; a cable in the wrong port is flagged.
- **Pre-flight check**: one read-only pass before the first change (media checksums, address
  conflicts, disk space, saved sign-ins, console helper, tools).
- **Kit recipes / build it again**: save a finished kit as a recipe; start a new kit from it.
- **Hand-over pack**: one printable document (versions, addresses, cable map, every check's proof;
  secrets excluded) with a rebuild-from-recipe button.

## Phase 3 - whole-kit confidence (done 2026-10-15)
- **Whole-kit acceptance test**: the Windows VM boots, reaches its gateway, resolves a name and
  survives a reboot (guarded VM power action; needs the VM's admin sign-in).
- **Reset for the next person**: guarded "return to factory" flow (RAID delete/erase, ESXi wipe,
  switch erase) with the same review/confirm/verify pattern. Destructive: built last, off by default.
- **Rehearsal rack**: a practice kit that runs the whole build against simulated hardware,
  including failures, without touching real equipment.

How it shipped: the acceptance test is step 4 on Install Windows. The restart counts only when
Windows' own boot time changes. Reset is ⋯ → "Reset for the next person". It needs
LAB_ALLOW_FACTORY_RESET=true, the typed RESET THIS KIT, and per-switch typed phrases. It
reuses the disk wipe installer and erases the switch over its console with exact prompts only.
The rehearsal rack is ⋯ → "Practice run". It runs in the browser only and makes no API calls.

## Phase 4 - wild ideas (done 2026-10-15)
- **Camera help**: read the iLO pull-out tag (address, user, password) with the PC camera, no typing;
  identify equipment in a rack photo for human review.
- **Time-lapse**: scrub through run history and watch the rack go green step by step.
- **Trace the path**: animate VM -> ESXi -> vmnic -> switch port and show where evidence stops.
- **Ask the lab**: ask "why is VLAN 100 here?" and get the plan entry, approved change and check.

How it shipped:
- **Camera help**: "Read the iLO tag with the camera" on the server connection form. It uses the
  browser's own text and barcode readers when present, and nothing is filled until Use is pressed.
  Without a text reader, the frozen photo stays on screen (zoomable) to type from. The photo never
  leaves the tab. Not built: identifying equipment in a rack photo (it needs a vision model; this
  PC has no internet for one).
- **Time-lapse**: a scrubber and play button at the top of Run history.
- **Trace the path**: ⋯ "Trace the path" (`GET /rack-plans/{p}/trace`, stored records only).
- **Ask the lab**: ⋯ "Ask the lab" (`GET /ask?q=`). It searches plan, change and check records;
  password-like fields are never searched.

## Kit Pilot (added 2026-10-16/18)
A separate program (`kit-pilot/`, `start-kit-pilot.cmd`) that flies the whole build through Lab
Builder's guarded API: Briefing (interview-style setup, one question at a time, reads the equipment
as it goes, every option asked in the dialogue), Flight plan (form view), Flight board (one button,
rack drawing, flight log), the finder (DHCP: finds iLO/ESXi/switch on the subnet without sign-in,
reads this PC's own network), a one-page report with the switch's real configuration (masked) and
what the setup changed, and a chaos checker proving six safety laws against every fault at every
request. Not yet run on the real kit: the switch first setup waits on cabling.
