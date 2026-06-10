# NetApp Console Discovery

Checked at: 2026-06-10T00:35:43.149970+00:00
Action: `console-read-state`
Status: `ready`
Provider mode: `local-lab-readwrite`

## Selection
- Configured port hint: `not set`
- Hint role: `optional_hint_only`
- Autodiscovery enabled: `True`
- Manual env update required: `False`
- Selected port: `/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00`
- Selected baud: `115200`
- Prompt/state: `NetApp cluster setup wizard`
- Prompt detected: `True`
- Selection confidence: `high`
- Selection source: `prompt-evidence`
- Selection origin: `autodiscovery`
- Selection reason: cluster setup
- Candidate count: `35`
- Selectable candidates: `35`
- Probed candidates: `4`
- Skipped candidates: `31`
- Attempt count: `1`
- Last console blocker: `none`

## Candidate Summary
- `/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00` | type=`by-id` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T22:26:16+00:00` | rank=`-35` | confidence=`high` | reason=stable /dev/serial/by-id path; candidate name matches NetApp serial hint
- `/dev/ttyACM0` | type=`ttyACM` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T22:26:16+00:00` | rank=`65` | confidence=`medium` | reason=ttyACM USB serial fallback; candidate name matches NetApp serial hint
- `/dev/ttyACM1` | type=`ttyACM` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:56:20.595289+00:00` | rank=`65` | confidence=`medium` | reason=ttyACM USB serial fallback; candidate name matches NetApp serial hint
- `/dev/ttyS20` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.921228+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS21` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.921554+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS22` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.922104+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS23` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.923676+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS24` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.919990+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS25` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.921206+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS26` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.924195+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS27` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.921412+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS28` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.924195+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS29` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.923992+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS30` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.925251+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS31` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.922912+00:00` | rank=`220` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS19` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.920460+00:00` | rank=`221` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS18` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.920927+00:00` | rank=`222` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS17` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.919384+00:00` | rank=`223` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS16` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.920927+00:00` | rank=`224` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS15` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.921175+00:00` | rank=`225` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS14` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.921035+00:00` | rank=`226` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS13` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.921412+00:00` | rank=`227` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS12` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.922841+00:00` | rank=`228` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS11` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.919288+00:00` | rank=`229` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS10` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.918000+00:00` | rank=`230` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS9` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.922576+00:00` | rank=`231` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS8` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.926330+00:00` | rank=`232` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS7` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.928310+00:00` | rank=`233` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS6` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.924254+00:00` | rank=`234` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS5` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.943403+00:00` | rank=`235` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS4` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:30+00:00` | rank=`236` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS3` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.922313+00:00` | rank=`237` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS2` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.920408+00:00` | rank=`238` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS1` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.921035+00:00` | rank=`239` | confidence=`medium` | reason=ttyS device has a recent modified timestamp
- `/dev/ttyS0` | type=`ttyS` | exists=`True` | rw=`True/True` | in_use=`False` | mtime=`2026-06-09T20:33:13.920927+00:00` | rank=`240` | confidence=`medium` | reason=ttyS device has a recent modified timestamp

## Management Topology
- Connected management ports: `cluster_mgmt`
- Note: Only one NetApp management port is connected at the moment.

## Attempts
- `/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00` @ `115200`: NetApp cluster setup wizard (checked)

## Blockers
- None

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
