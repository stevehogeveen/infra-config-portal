# Cisco Console Discovery

- Status: ok
- Prompt state: exec
- Configured port hint: not set
- Auto-discovered selected port: /dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0
- Selected baud: 9600
- Candidate count: 2
- Last console blocker: none

## Candidate Summary
- /dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0 | stable=True | exists=True | readable=True | writable=True | in_use=False | rank=-25 | recommendation=selected-auto
- /dev/ttyUSB0 | stable=False | exists=True | readable=True | writable=True | in_use=False | rank=100 | recommendation=fallback-auto-candidate

## Attempts
- /dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0 @ 9600 via newline: checked prompt=unknown captured=False
- /dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0 @ 9600 via enter: checked prompt=exec captured=True
