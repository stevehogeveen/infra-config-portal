# NetApp Console Deep Probe Report

Checked at: 2026-06-07T21:15:05Z

## Result

- Status: `blocked`
- No usable NetApp console prompt, boot state, login flow, or raw bytes were captured.
- No NetApp credentials, commands, boot interrupts, Ctrl+C, break, boot menu input, or configuration actions were sent.
- No serial probe process was left running after the checks.

## Current OS-Visible Serial State

- `/dev/serial/by-id/`: absent
- `/dev/ttyUSB*`: absent
- `/dev/ttyACM*`: absent
- `python3 -m serial.tools.list_ports -v`: 32 `ttyS` entries only
- `lsusb`: no current Microchip MCP2221, Prolific, FTDI, CP210, or USB serial adapter
- `lsusb -t`: no current USB serial driver binding
- Kernel modules: `pl2303` and `usbserial` are loaded, but no Prolific USB serial device is present
- Recent kernel journal search: no USB serial attach/drop evidence in the checked window

## Lab-Builder Evidence

Old lab-builder evidence confirms the NetApp console was previously found through USB serial:

- NetApp cluster shell: `/dev/ttyACM0` at `115200`
- NetApp login candidate: `/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00` at `115200`
- Cisco console was the Prolific adapter at `9600`

That means the expected NetApp path is USB ACM/Microchip at `115200`, not the current built-in `ttyS` ports.

## Current App Probe

Updated NetApp discovery now uses NetApp-safe wake bytes only:

- `newline`
- `carriage-return`

Updated NetApp discovery now probes multiple ranked candidates instead of stopping after one:

- Candidate count: `32`
- Selectable candidates: `32`
- Probed candidates: `4`
- Skipped candidates: `28`
- Selected fallback candidate: `/dev/ttyS5` at `115200`

Probed candidate outcomes:

- `/dev/ttyS5`: opened at common baud rates, zero bytes read
- `/dev/ttyS4`: opened at common baud rates, zero bytes read
- `/dev/ttyS1`: timed out opening/probing
- `/dev/ttyS0`: serial I/O configuration errors

Reports updated:

- `artifacts/codex-runs/netapp-console-autodiscovery-report.md`
- `artifacts/codex-runs/netapp-console-autodiscovery-redacted.json`
- `artifacts/codex-runs/netapp-console-state-report.md`
- `artifacts/codex-runs/netapp-console-state-redacted.json`

## Independent Probe Methods Tried

- PySerial candidate/baud scan with newline and carriage return only
- DTR/RTS combinations on `/dev/ttyS4` and `/dev/ttyS5`
- Raw `stty` plus `dd` reads on `/dev/ttyS4` and `/dev/ttyS5` at `115200` and `9600`
- `picocom` timed captures on `/dev/ttyS4` and `/dev/ttyS5` at `115200` and `9600`

All independent checks returned zero captured bytes from the openable `ttyS` ports.

## Current Blocker Classification

The host can see built-in `ttyS` devices, but it cannot currently see the USB serial adapters that lab-builder previously used for NetApp. The most likely blocker is physical/USB visibility, not ONTAP credentials or app prompt parsing.

Next physical checks:

- Confirm the NetApp USB serial adapter is the Microchip MCP2221 or a `ttyACM` device.
- Move/reseat the NetApp USB serial adapter and watch for `/dev/ttyACM0` or `/dev/serial/by-id/usb-Microchip*`.
- If the cable is attached through a USB hub/dock, try a direct host USB port.
- If the cable is attached to a console server instead of local USB, provide the TCP console endpoint so the app can add a `tcp_console/ser2net` probe path.
