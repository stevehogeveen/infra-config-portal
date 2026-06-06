# Cisco Console Port Access Report

- Checked at: `2026-06-06T18:19:52Z`
- User: `administrator`
- Groups: `administrator adm dialout cdrom sudo dip plugdev users lpadmin docker`
- Sudo required for this diagnostic: `no`

## Enumerated Devices

### `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0`

- ls: lrwxrwxrwx 1 root root 13 Jun  5 10:16 /dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0 -> ../../ttyUSB0
- realpath: `/dev/ttyUSB0`
- readable_by_current_user: `yes`
- writable_by_current_user: `yes`
- lsof: no owner reported
- fuser: no owner reported

### `/dev/ttyUSB0`

- ls: crw-rw---- 1 root dialout 188, 0 Jun  6 14:10 /dev/ttyUSB0
- readable_by_current_user: `yes`
- writable_by_current_user: `yes`
- lsof: no owner reported
- fuser: no owner reported


## Access Notes

- This diagnostic used current-user read/write checks only.
- If read/write is no, add the backend user to the device group such as dialout and restart the shell/session.
