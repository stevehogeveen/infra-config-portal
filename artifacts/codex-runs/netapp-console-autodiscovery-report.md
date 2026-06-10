# NetApp Console Discovery

Checked at: 2026-06-10T19:44:46.115730+00:00
Action: `console-discovery`
Status: `blocked`
Provider mode: `local-lab-readwrite`

## Selection
- Configured port hint: `not set`
- Hint role: `optional_hint_only`
- Autodiscovery enabled: `True`
- Manual env update required: `False`
- Selected port: `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0`
- Selected baud: `9600`
- Prompt/state: `Unclassified console output`
- Prompt detected: `False`
- Selection confidence: `high`
- Selection source: `auto-stable-candidate`
- Selection origin: `autodiscovery`
- Selection reason: stable /dev/serial/by-id path; candidate name matches common USB serial adapter
- Candidate count: `36`
- Selectable candidates: `33`
- Probed candidates: `4`
- Skipped candidates: `29`
- Attempt count: `20`
- Last console blocker: `Serial candidates were discovered, but no valid NetApp prompt, boot state, or login flow was detected.`

## Candidate Summary
- `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0` | type=`by-id` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T19:42:32+00:00` | rank=`-10` | confidence=`high` | reason=stable /dev/serial/by-id path; candidate name matches common USB serial adapter
- `/dev/ttyUSB0` | type=`ttyUSB` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T19:42:32+00:00` | rank=`90` | confidence=`medium` | reason=ttyUSB USB serial fallback; candidate name matches common USB serial adapter
- `/dev/ttyS20` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.401399+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS21` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.404788+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS22` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.405144+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS23` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.405336+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS24` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.405032+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS25` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.406573+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS26` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.406406+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS27` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.404788+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS28` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.405809+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS29` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.406406+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS30` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.405809+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS31` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.406693+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS19` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.403298+00:00` | rank=`221` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS18` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.401857+00:00` | rank=`222` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS17` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.400595+00:00` | rank=`223` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS16` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.401851+00:00` | rank=`224` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS15` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.401593+00:00` | rank=`225` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS14` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.400542+00:00` | rank=`226` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS13` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.401729+00:00` | rank=`227` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS12` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.399713+00:00` | rank=`228` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS11` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.401445+00:00` | rank=`229` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS10` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.406035+00:00` | rank=`230` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS9` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.407400+00:00` | rank=`231` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS8` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.406406+00:00` | rank=`232` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS7` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.408978+00:00` | rank=`233` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS6` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.405276+00:00` | rank=`234` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS5` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T19:44:20+00:00` | rank=`235` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS4` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T19:41:32+00:00` | rank=`236` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS3` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.405809+00:00` | rank=`237` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS2` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.403085+00:00` | rank=`238` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS0` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-10T13:04:02.399713+00:00` | rank=`240` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00` | type=`by-id` | exists=`True` | rw=`True/True` | in_use=`True` | mtime=`2026-06-10T19:44:42+00:00` | rank=`565` | confidence=`low` | reason=stable /dev/serial/by-id path; candidate name matches NetApp serial hint; path appears to be in use
- `/dev/ttyACM0` | type=`ttyACM` | exists=`True` | rw=`True/True` | in_use=`True` | mtime=`2026-06-10T19:44:42+00:00` | rank=`665` | confidence=`low` | reason=ttyACM USB serial fallback; candidate name matches NetApp serial hint; path appears to be in use
- `/dev/ttyS1` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`True` | mtime=`2026-06-10T17:48:28+00:00` | rank=`839` | confidence=`low` | reason=ttyS device has a recent modified timestamp; path appears to be in use

## Management Topology
- Connected management ports: `cluster_mgmt`
- Note: Only one NetApp management port is connected at the moment.

## Attempts
- `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0` @ `115200`: No console output (checked)
- `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0` @ `9600`: Unclassified console output (checked)
- `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0` @ `19200`: Unreadable console text (checked)
- `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0` @ `38400`: Unreadable console text (checked)
- `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0` @ `57600`: Unreadable console text (checked)
- `/dev/ttyUSB0` @ `115200`: Unreadable console text (checked)
- `/dev/ttyUSB0` @ `9600`: Unreadable console text (checked)
- `/dev/ttyUSB0` @ `19200`: Unreadable console text (checked)
- `/dev/ttyUSB0` @ `38400`: No console output (checked)
- `/dev/ttyUSB0` @ `57600`: No console output (checked)
- `/dev/ttyS20` @ `115200`: Serial open failed (blocked)
- `/dev/ttyS20` @ `9600`: Serial open failed (blocked)
- `/dev/ttyS20` @ `19200`: Serial open failed (blocked)
- `/dev/ttyS20` @ `38400`: Serial open failed (blocked)
- `/dev/ttyS20` @ `57600`: Serial open failed (blocked)
- `/dev/ttyS21` @ `115200`: Serial open failed (blocked)
- `/dev/ttyS21` @ `9600`: Serial open failed (blocked)
- `/dev/ttyS21` @ `19200`: Serial open failed (blocked)
- `/dev/ttyS21` @ `38400`: Serial open failed (blocked)
- `/dev/ttyS21` @ `57600`: Serial open failed (blocked)

## Blockers
- Serial candidates were discovered, but no valid NetApp prompt, boot state, or login flow was detected.

## Warnings
- Only newline and carriage return wake bytes are allowed for this NetApp console probe.
- No NetApp credentials, commands, boot interrupts, or configuration actions are sent.
- Serial auto-discovery includes /dev/serial/by-id/*, /dev/ttyUSB*, /dev/ttyACM*, and /dev/ttyS*.
- Only one NetApp management port is connected at the moment.

## Not Attempted
- Ctrl+C, Ctrl+Z, break, boot menu selection, or any boot interruption
- username or password entry
- cluster setup commands
- SP, node, SVM, LIF, volume, export, or datastore creation
- ONTAP API write
- vCenter or ESXi datastore mount
- controller reboot, takeover/giveback, wipe, or upgrade
