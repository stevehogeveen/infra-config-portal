"""First setup of a Cisco switch over its console cable.

Gives a new switch its name, an admin user, a management address (static or DHCP on a VLAN
interface) and SSH, then optionally saves. It works on any connection with the pyserial surface
(read, write, in_waiting, close): a local port or one relayed by the console helper.

How it walks the console:
  - "Would you like to enter the initial configuration dialog?" is answered "no" (the app sets
    the switch up itself), "terminate autoinstall?" is answered "yes", "Press RETURN" gets Enter.
  - ">" gets "enable"; a switch that asks for an enable password, a console login, or sits in
    configuration mode or ROMMON is not touched: those mean someone set it up before.
  - Every configuration line must come back to the config prompt without an IOS error ("% ...");
    the first error stops the run, leaves configuration mode and reports the line (no secrets).
  - configure() never sends anything destructive: no erase, reload, delete, copy over startup or
    boot changes. The one destructive routine, factory_erase(), is separate and is only called by
    the locked-down "Reset for the next person" flow (services/switch_reset.py).
"""

from __future__ import annotations

import ipaddress
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

WIZARD = re.compile(r"initial configuration dialog\?\s*\[yes/no\]:\s*$", re.I)
AUTOINSTALL = re.compile(r"terminate autoinstall\?\s*\[yes\]:\s*$", re.I)
PRESS_RETURN = re.compile(r"Press RETURN to get started!?\s*$", re.I)
EXEC = re.compile(r"(?:^|\n)[A-Za-z][\w.-]{0,62}>\s*$")
PRIV = re.compile(r"(?:^|\n)[A-Za-z][\w.-]{0,62}#\s*$")
CONFIG = re.compile(r"(?:^|\n)[A-Za-z][\w.-]{0,62}\(config[^)]*\)#\s*$")
LOGIN = re.compile(r"(?:Username|Login|Password):\s*$", re.I)
ROMMON = re.compile(r"(?:^|\n)(?:switch:|rommon\s*\d*\s*>)\s*$", re.I)
REPLACE_KEYS = re.compile(r"replace them\?\s*\[yes/no\]:\s*$", re.I)
CONFIRM = re.compile(r"\[confirm\]\s*$", re.I)
# Reset only: each erase question is matched exactly; anything else is cancelled (Ctrl-C) and stops.
ERASE_CONFIRM = re.compile(r"remove all configuration files! Continue\? \[confirm\]\s*$", re.I)
DELETE_NAME = re.compile(r"Delete filename \[vlan\.dat\]\?\s*$", re.I)
DELETE_CONFIRM = re.compile(r"Delete flash:/?vlan\.dat\? \[confirm\]\s*$", re.I)
SAVE_PROMPT = re.compile(r"System configuration has been modified\. Save\? \[yes/no\]:\s*$", re.I)
RELOAD_CONFIRM = re.compile(r"Proceed with reload\? \[confirm\]\s*$", re.I)
ANY_QUESTION = re.compile(r"(\[confirm\]|\[yes/no\]:?|\?\s*\[[^\]\n]*\]\??)\s*$", re.I)
# Any "%" line from IOS is treated as a refusal, except the known progress notes of key generation.
IOS_MESSAGE = re.compile(r"^\s*%[^\n]*", re.M)
IOS_INFO = re.compile(r"%\s*(Generating \d+ bit RSA keys|The key modulus size is|You already have RSA keys|They will be replaced|Do you really want to replace|Key pair was not generated)", re.I)
HOSTNAME = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,62}$")
DOMAIN = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,31}$")
PORT_NAME = re.compile(r"^(Gi|Te|Tw|Fo|Hu|Fa|GigabitEthernet|TenGigabitEthernet|TwoGigabitEthernet|FortyGigabitEthernet|HundredGigE|FastEthernet)\d+(/\d+){1,2}$", re.I)
PORT_STATUS = re.compile(r"^(\S+)\s.*?\b(connected|notconnect|disabled|err-disabled|inactive|sfpAbsent|monitoring)\b", re.I)


SHORT_NAMES = {"gigabitethernet": "gi", "tengigabitethernet": "te", "twogigabitethernet": "tw",
               "fortygigabitethernet": "fo", "hundredgige": "hu", "fastethernet": "fa"}


def _port_key(name: str) -> str:
    """Gi1/0/48 and GigabitEthernet1/0/48 are the same port."""
    match = re.match(r"^([A-Za-z]+)(.*)$", name.strip())
    if not match:
        return name.lower()
    letters = match.group(1).lower()
    return SHORT_NAMES.get(letters, letters[:2]) + match.group(2)


def find_uplink(console_output: str) -> tuple[list[str], list[str]]:
    """From 'show interfaces status': (connected ports, every port)."""
    connected, every = [], []
    for raw in console_output.splitlines():
        match = PORT_STATUS.match(raw.strip())
        if match and PORT_NAME.match(match.group(1)):
            every.append(match.group(1))
            if match.group(2).lower() == "connected":
                connected.append(match.group(1))
    return connected, every


class SetupStopped(Exception):
    """The run stopped before or while configuring; ``sent`` says whether config was sent."""

    def __init__(self, message: str, *, sent: bool) -> None:
        super().__init__(message)
        self.sent = sent


@dataclass
class SetupPlan:
    hostname: str
    domain: str
    username: str
    password: str
    enable_secret: str | None
    vlan: int
    mode: str  # "dhcp" or "static"
    address: str | None = None
    prefix: int | None = None
    gateway: str | None = None
    save: bool = True
    # The port with the cable to the network: "auto" (the only connected port) or a port name.
    uplink: str = "auto"
    uplink_mode: str = "access"  # "access" (untagged in the management VLAN) or "trunk"

    def needs_uplink(self) -> bool:
        """VLAN 1 reaches every port already; any other VLAN must be put on the cabled port."""
        return self.uplink != "auto" or self.vlan != 1 or self.uplink_mode == "trunk"

    def problems(self) -> list[str]:
        out = []
        if not HOSTNAME.match(self.hostname or ""):
            out.append("The switch name must start with a letter and use only letters, digits and hyphens.")
        if not DOMAIN.match(self.domain or ""):
            out.append("Enter a domain name such as lab.local (SSH keys need one).")
        if not USERNAME.match(self.username or ""):
            out.append("The admin username must start with a letter (letters, digits, . _ -).")
        if not _safe_secret(self.password):
            out.append("The admin password needs 8 to 64 characters: letters, digits and symbols, without spaces or '?'.")
        if self.enable_secret is not None and not _safe_secret(self.enable_secret):
            out.append("The enable password needs 8 to 64 characters: letters, digits and symbols, without spaces or '?'.")
        if not 1 <= int(self.vlan) <= 4094 or int(self.vlan) in range(1002, 1006):
            out.append("The management VLAN must be 1-1001 or 1006-4094.")
        if self.mode not in {"dhcp", "static"}:
            out.append("Choose DHCP or a static address.")
        if self.uplink != "auto" and not PORT_NAME.match(self.uplink or ""):
            out.append("The network cable port must look like Gi1/0/48 (or choose auto-detect).")
        if self.uplink_mode not in {"access", "trunk"}:
            out.append("Choose how the network cable port carries the management VLAN.")
        if self.mode == "static":
            try:
                network = ipaddress.IPv4Interface(f"{self.address}/{self.prefix}")
                gateway = ipaddress.IPv4Address(str(self.gateway))
                if network.ip == network.network.network_address or network.ip == network.network.broadcast_address:
                    out.append("The address is the network or broadcast address of that subnet.")
                if gateway not in network.network or gateway == network.ip:
                    out.append("The gateway must be another address in the same subnet.")
            except ValueError:
                out.append("Enter a valid IPv4 address, prefix length (for example 24) and gateway.")
        return out

    def commands(self, uplink_port: str | None = None) -> list[tuple[str, str]]:
        """(line sent, line shown) pairs; secrets never appear in the shown line."""
        lines: list[tuple[str, str]] = [("line console 0", "line console 0"), ("logging synchronous", "logging synchronous"), ("exit", "exit"),
                                        (f"hostname {self.hostname}", f"hostname {self.hostname}"),
                                        (f"ip domain name {self.domain}", f"ip domain name {self.domain}"),
                                        ("no ip domain lookup", "no ip domain lookup"),
                                        (f"username {self.username} privilege 15 secret {self.password}",
                                         f"username {self.username} privilege 15 secret ********")]
        if self.enable_secret:
            lines.append((f"enable secret {self.enable_secret}", "enable secret ********"))
        if self.vlan != 1:
            lines += [(f"vlan {self.vlan}", f"vlan {self.vlan}"), ("exit", "exit")]
        if uplink_port:
            # The cabled port must carry the management VLAN, or the address never comes up.
            lines += [(f"interface {uplink_port}", f"interface {uplink_port}"),
                      ("description Lab Builder uplink", "description Lab Builder uplink")]
            if self.uplink_mode == "trunk":
                lines.append(("switchport mode trunk", "switchport mode trunk"))
            else:
                lines += [("switchport mode access", "switchport mode access"),
                          (f"switchport access vlan {self.vlan}", f"switchport access vlan {self.vlan}")]
            lines += [("no shutdown", "no shutdown"), ("exit", "exit")]
        lines.append((f"interface Vlan{self.vlan}", f"interface Vlan{self.vlan}"))
        if self.mode == "static":
            mask = str(ipaddress.ip_network(f"0.0.0.0/{self.prefix}").netmask)
            lines.append((f"ip address {self.address} {mask}", f"ip address {self.address} {mask}"))
        else:
            lines.append(("ip address dhcp", "ip address dhcp"))
        lines += [("no shutdown", "no shutdown"), ("exit", "exit")]
        if self.mode == "static":
            lines += [(f"ip default-gateway {self.gateway}", f"ip default-gateway {self.gateway}"),
                      (f"ip route 0.0.0.0 0.0.0.0 {self.gateway}", f"ip route 0.0.0.0 0.0.0.0 {self.gateway}")]
        lines += [("crypto key generate rsa general-keys modulus 2048", "crypto key generate rsa general-keys modulus 2048"),
                  ("ip ssh version 2", "ip ssh version 2"),
                  ("line vty 0 15", "line vty 0 15"), ("login local", "login local"),
                  ("transport input ssh", "transport input ssh"), ("exit", "exit")]
        return lines

    def preview(self) -> list[str]:
        uplink = None
        if self.needs_uplink():
            uplink = self.uplink if self.uplink != "auto" else "<the one port with a network cable, found on the switch>"
        shown = ["configure terminal", *[f" {shown}" for _, shown in self.commands(uplink)], "end"]
        if self.save:
            shown.append("write memory")
        return shown


def _safe_secret(value: str | None) -> bool:
    # Printable ASCII only: a control character (Ctrl-C, Ctrl-Z, ESC, backspace) could end the
    # command early and turn the rest of the secret into a command of its own.
    return bool(value) and 8 <= len(value) <= 64 and all(0x21 <= ord(c) <= 0x7E and c != "?" for c in value)


def scrub(text: str, *secrets: str | None) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "********")
    return text


def ios_error(text: str) -> str | None:
    for match in IOS_MESSAGE.finditer(text):
        if not IOS_INFO.search(match.group(0)):
            return match.group(0).strip()
    return None


# Older IOS spells a few commands differently; one alternative is tried after an "% Invalid".
ALTERNATIVES = {"ip domain name": "ip domain-name"}


@dataclass
class Console:
    connection: Any
    log: Callable[[str], None] = lambda _: None
    buffer: str = ""
    sent: list[str] = field(default_factory=list)

    def send(self, data: str, shown: str | None = None) -> None:
        self.connection.write(data.encode())
        if shown is not None:
            self.sent.append(shown)

    def expect(self, patterns: dict[str, re.Pattern], timeout: float) -> tuple[str, str]:
        """Read until one pattern matches the end of the output; returns (name, text read)."""
        deadline = time.monotonic() + timeout
        text = ""
        while True:
            waiting = int(getattr(self.connection, "in_waiting", 0) or 0)
            chunk = self.connection.read(max(waiting, 1))
            if chunk:
                text += chunk.decode("utf-8", errors="replace").replace("\r", "")
                if len(text) > 200_000:
                    text = text[-100_000:]
                tail = text[-400:]
                for name, pattern in patterns.items():
                    if pattern.search(tail):
                        return name, text
                continue
            if time.monotonic() > deadline:
                return "timeout", text
            time.sleep(0.02)


ENTRY = {"config": CONFIG, "priv": PRIV, "exec": EXEC, "login": LOGIN, "rommon": ROMMON,
         "wizard": WIZARD, "autoinstall": AUTOINSTALL, "press_return": PRESS_RETURN}


def reach_privileged(console: Console) -> str:
    """From whatever state a new switch is in, get to the # prompt. Returns the starting state."""
    console.send("\r")
    first = None
    for _ in range(12):
        name, _text = console.expect(ENTRY, timeout=25)
        first = first or name
        if name == "priv":
            return first
        if name == "wizard":
            console.send("no\r", "no (skip the setup dialog)")
        elif name == "autoinstall":
            console.send("yes\r", "yes (stop autoinstall)")
        elif name == "press_return":
            console.send("\r")
        elif name == "exec":
            console.send("enable\r", "enable")
            got, _ = console.expect({"priv": PRIV, "login": LOGIN, "exec": EXEC}, timeout=15)
            if got == "priv":
                return first
            if got == "login":
                console.send("\x03")  # leave the password prompt without guessing
                raise SetupStopped("The switch asks for an enable password, so it has been set up before. Nothing was changed.", sent=False)
        elif name == "login":
            raise SetupStopped("The switch asks for a console login, so it has been set up before. Nothing was changed.", sent=False)
        elif name == "config":
            raise SetupStopped("The switch is sitting in configuration mode (someone left it mid-change). Nothing was changed.", sent=False)
        elif name == "rommon":
            raise SetupStopped("The switch is in its boot loader (ROMMON), not running its software. Nothing was changed.", sent=False)
        else:  # timeout: wake it once more
            console.send("\r")
    raise SetupStopped("The switch did not reach its normal prompt. Nothing was changed.", sent=False)


def configure(console: Console, plan: SetupPlan, progress: Callable[[str], None] = lambda _: None) -> dict[str, Any]:
    """Apply the plan from the # prompt. Returns what was sent (shown form) and whether it saved."""
    def at_priv(timeout: float, sent: bool, what: str) -> str:
        name, text = console.expect({"priv": PRIV, "config": CONFIG}, timeout=timeout)
        if name == "timeout":
            # A syslog line (for example "%SSH-5-ENABLED") printed after the prompt hides it; a bare Enter brings it back.
            console.send("\r")
            again, more = console.expect({"priv": PRIV, "config": CONFIG}, timeout=10)
            name, text = again, text + more
        if name != "priv":
            raise SetupStopped(f"The switch did not return to its # prompt {what}." + (" Settings already sent are running but not saved." if sent else " Nothing was changed."), sent=sent)
        return text

    console.send("terminal length 0\r")
    at_priv(10, False, "after 'terminal length 0'")
    uplink = None
    if plan.needs_uplink():
        console.send("show interfaces status\r")
        connected, every = find_uplink(at_priv(30, False, "after 'show interfaces status'"))
        if plan.uplink != "auto":
            uplink = next((port for port in every if _port_key(port) == _port_key(plan.uplink)), None)
            if not uplink:
                raise SetupStopped(f"The switch has no port called {plan.uplink}. Nothing was changed.", sent=False)
        elif len(connected) == 1:
            uplink = connected[0]
        elif not connected:
            raise SetupStopped("No port on the switch has a network cable connected, so the management VLAN could not be put on one. Plug the switch into your network and try again. Nothing was changed.", sent=False)
        else:
            raise SetupStopped(f"Several ports have cables ({', '.join(connected[:6])}). Choose the one going to your network in the settings. Nothing was changed.", sent=False)
    console.send("configure terminal\r", "configure terminal")
    name, _ = console.expect({"config": CONFIG}, timeout=15)
    if name != "config":
        raise SetupStopped("The switch did not enter configuration mode. Nothing was changed.", sent=False)
    progress("configuring")
    for line, shown in plan.commands(uplink):
        slow = line.startswith("crypto key")
        console.send(line + "\r", shown)
        expected = {"config": CONFIG, "replace": REPLACE_KEYS, "confirm": CONFIRM} if slow else {"config": CONFIG, "confirm": CONFIRM}
        name, text = console.expect(expected, timeout=240 if slow else 20)
        if name != "replace" and slow and REPLACE_KEYS.search(text):
            name = "replace"  # the question arrived with warning lines around it; it is still the question
        if name == "replace":
            console.send("no\r", "no (keep the existing SSH keys)")
            name, text = console.expect({"config": CONFIG}, timeout=30)
        if name == "confirm":
            # None of these commands should ask; an unexpected question is cancelled, never approved.
            console.send("\x03")
            console.expect({"config": CONFIG, "priv": PRIV}, timeout=10)
            console.send("end\r")
            console.expect({"priv": PRIV}, timeout=10)
            raise SetupStopped(f"The switch asked an unexpected question after '{shown}'. It was cancelled; configuration stopped there and was not saved.", sent=True)
        error = ios_error(text)
        alternative = next((alt for key, alt in ALTERNATIVES.items() if line.startswith(key)), None)
        if error and alternative:
            alt_line = line.replace(next(k for k in ALTERNATIVES if line.startswith(k)), alternative, 1)
            console.send(alt_line + "\r", shown.replace(next(k for k in ALTERNATIVES if shown.startswith(k)), alternative, 1))
            name, text = console.expect({"config": CONFIG}, timeout=20)
            error = ios_error(text)
        if name == "timeout" or error:
            console.send("end\r")
            console.expect({"priv": PRIV}, timeout=10)
            reason = scrub(error, plan.password, plan.enable_secret) if error else "no reply"
            raise SetupStopped(f"The switch refused '{shown}': {reason}. Configuration stopped there and was not saved.", sent=True)
    console.send("end\r", "end")
    at_priv(15, True, "after leaving configuration mode")
    console.send("show ip ssh\r")
    if not re.search(r"SSH Enabled", at_priv(15, True, "after 'show ip ssh'"), re.I):
        raise SetupStopped("The settings were sent but the switch reports SSH is not enabled. They were not saved.", sent=True)
    saved = False
    if plan.save:
        progress("saving")
        console.send("write memory\r", "write memory")
        name, text = console.expect({"priv": PRIV, "confirm": CONFIRM}, timeout=120)
        if name == "confirm":
            console.send("\x03")
            raise SetupStopped("Saving asked an unexpected question; it was cancelled. The settings are running but not saved.", sent=True)
        saved = name == "priv" and "[OK]" in text
        if not saved:
            raise SetupStopped("The settings are running but saving them did not confirm ([OK] not seen).", sent=True)
    return {"sent": list(console.sent), "saved": saved, "uplink": uplink}


def read_address(console: Console, vlan: int) -> tuple[str | None, str | None]:
    """Read-only: the management interface's address and status from the # prompt."""
    console.send(f"show ip interface brief | include Vlan{vlan}\r")
    _, text = console.expect({"priv": PRIV}, timeout=15)
    for raw in text.splitlines():
        parts = raw.split()
        if parts and parts[0].lower() == f"vlan{vlan}" and len(parts) >= 2:
            address = parts[1]
            status = " ".join(parts[4:]) if len(parts) > 4 else None
            try:
                ipaddress.ip_address(address)
                return address, status
            except ValueError:
                return None, status
    return None, None


# Everything after one of these prefixes is a secret: the whole remainder of the line is masked.
# (Covers user/enable secrets and passwords, line passwords, nested RADIUS/TACACS keys, key-strings,
# HSRP/VRRP authentication, PPP, FTP/HTTP client passwords, NTP keys, ISAKMP/IPsec keys, WLAN PSKs,
# SSH public-key hashes and any line that still says "secret", "password" or "key" with a value.)
SECRET_PREFIXES = [
    r"username \S+ .*?(?:secret|password)(?: \d)?",
    r"enable (?:secret|password)(?: level \d+)?(?: \d)?",
    r"password(?: \d)?",                                   # line vty / con passwords
    r"(?:tacacs|radius)(?:-server)? .*?\bkey(?: \d)?",
    r"key(?: \d)?",                                        # nested key inside radius/tacacs server blocks
    r"key-string(?: \d)?",
    r"(?:snmp-server community)",
    r"snmp-server user .*?(?:auth|priv) \S+",
    r"ntp authentication-key \d+ md5",
    r"standby \d+ authentication(?: md5 key-string(?: \d)?| text)?",
    r"vrrp \d+ authentication(?: md5 key-string(?: \d)?| text)?",
    r"ppp (?:chap|pap) (?:password|sent-username \S+ password)(?: \d)?",
    r"ip (?:ftp|http client) password(?: \d)?",
    r"crypto isakmp key(?: \d)?",
    r"pre-shared-key(?: local| remote)?(?: \d)?",
    r"(?:wpa-psk|psk)(?: (?:ascii|hex))?(?: \d)?",
    r"key-hash \S+",
    r"aaa .*?\bkey(?: \d)?",
    r"neighbor \S+ password(?: \d)?",
    r".*\b(?:secret|password)(?: \d)?",                   # anything else that admits a secret
]
SECRET_LINE = re.compile(r"^(\s*(?:" + "|".join(SECRET_PREFIXES) + r"))\s+\S.*$", re.M | re.I)
HEX_BLOB = re.compile(r"^\s*[0-9A-F]{8}(?: [0-9A-F]{8})+\s*$", re.M)   # certificate / key bodies
MORE = re.compile(r"--More--\s*$")
KEEP_WORDS = re.compile(r"^\s*(?:no |service |ip ssh version|ip ssh bulk|login |transport |aaa new-model|password encryption)", re.I)


# A log line the switch prints into the middle of command output, e.g.
# "*Oct 22 14:42:38.254: %CDP-4-NATIVE_VLAN_MISMATCH: Native VLAN mismatch discovered on ... (670)." It arrives
# after a line break and the interrupted output resumes right behind it, so the line is removed and the two
# halves of the interrupted line are joined again.
SYSLOG_LINE = re.compile(
    r"\r?\n?\*?(?:[A-Z][a-z]{2} +\d{1,2} \d\d:\d\d:\d\d(?:\.\d+)?(?: [A-Z]{2,5})?: )?"
    r"%[A-Z0-9_-]+-\d-[A-Z0-9_]+: [^\r\n]*?(?:\.(?=[a-z!])|(?=\r?\n|$))")


def strip_syslog(text: str) -> str:
    """Remove log lines printed into captured output, rejoining the line they interrupted."""
    return SYSLOG_LINE.sub("", text or "")


def sanitize_config(text: str) -> str:
    """Mask every secret-bearing value in an IOS configuration; the rest stays readable."""
    def mask(match: re.Match) -> str:
        line = match.group(0)
        if KEEP_WORDS.match(line) and not re.search(r"\b(?:secret|key-string|community)\b", line, re.I):
            return line
        return match.group(1) + " ********"
    text = SECRET_LINE.sub(mask, text)
    return HEX_BLOB.sub("  [certificate or key data removed]", text)


def read_running_config(console: Console) -> str | None:
    """Read-only: the running configuration from the # prompt, with secrets masked. None if it did not come back.

    Pages ('--More--') are continued with a space, within a time bound; a configuration longer than the
    capture window is marked incomplete rather than silently cut.
    """
    console.send("terminal length 0\r")
    console.expect({"priv": PRIV}, timeout=10)
    console.send("show running-config\r")
    deadline = time.monotonic() + 120
    chunks: list[str] = []
    while True:
        name, text = console.expect({"priv": PRIV, "more": MORE}, timeout=max(1.0, deadline - time.monotonic()))
        chunks.append(MORE.sub("", text))
        if name == "more" and time.monotonic() < deadline:
            console.send(" ")
            continue
        break
    if name != "priv":
        return None
    whole = "".join(chunks)
    if "Current configuration" not in whole and "version " not in whole:
        return None
    body = strip_syslog(whole.split("show running-config", 1)[-1])
    lines = [line for line in body.splitlines() if not PRIV.search("\n" + line)]
    config = sanitize_config("\n".join(lines).strip())
    if len(whole) >= 100_000:
        config = "[configuration longer than the capture window; the beginning may be missing]\n" + config
    return config or None


def read_serial(console: Console) -> str | None:
    """Read-only: the chassis serial number from show version."""
    console.send("show version | include [Ss]ystem [Ss]erial [Nn]umber|Processor board ID\r")
    _, text = console.expect({"priv": PRIV}, timeout=20)
    match = re.search(r"System [Ss]erial [Nn]umber\s*:\s*(\S+)", text) or re.search(r"Processor board ID\s+(\S+)", text)
    return match.group(1) if match else None



def wake_for_reset(console: Console, enable_password: str | None) -> None:
    """Reach the # prompt without ever approving a question left pending on the console.

    Every wake starts with Ctrl-C (which cancels a pending [confirm] or [yes/no]) before Enter.
    A switch already showing its setup dialog has nothing to erase; any other unknown state stops.
    """
    def wake() -> None:
        console.send("\x03")
        time.sleep(0.3)
        console.send("\r")

    wake()
    for _ in range(8):
        name, _text = console.expect(ENTRY, timeout=20)
        if name == "priv":
            return
        if name in {"wizard", "autoinstall"}:
            console.send("\x03")
            raise SetupStopped("The switch already shows its new-switch setup dialog: it has no settings to erase. Nothing was changed.", sent=False)
        if name == "press_return":
            console.send("\r")
        elif name == "config":
            console.send("\x03")  # Ctrl-C leaves configuration mode without applying a half-typed line
        elif name == "exec":
            console.send("enable\r", "enable")
            got, _ = console.expect({"priv": PRIV, "login": LOGIN, "exec": EXEC}, timeout=15)
            if got == "priv":
                return
            if got == "login" and enable_password:
                console.send(enable_password + "\r", "******** (saved enable password)")
                got, _ = console.expect({"priv": PRIV, "login": LOGIN, "exec": EXEC}, timeout=15)
                if got == "priv":
                    return
            console.send("\x03")
            raise SetupStopped("The switch refused the saved enable password (or none is saved). Nothing was changed.", sent=False)
        elif name == "login":
            raise SetupStopped("The switch asks for a console login the app does not have. Nothing was changed.", sent=False)
        elif name == "rommon":
            raise SetupStopped("The switch is in its boot loader (ROMMON). Nothing was changed.", sent=False)
        else:
            wake()
    raise SetupStopped("The switch did not reach its # prompt. Nothing was changed.", sent=False)


def factory_erase(console: Console, progress: Callable[[str], None] = lambda _: None, boot_timeout: float = 1500.0) -> dict[str, Any]:
    """Return a switch to factory settings from the # prompt, then watch it restart.

    Sends: write erase, delete flash:vlan.dat (a missing file is fine), reload answering "no" to
    saving. Only the exact expected question of each command is answered; any other question is
    cancelled with Ctrl-C and the run stops. Each send happens once. Done means the switch came back
    showing its new-switch setup dialog. Raises SetupStopped (sent=True once anything was sent).
    """
    def step(patterns: dict[str, re.Pattern], timeout: float, what: str) -> tuple[str, str]:
        name, text = console.expect({**patterns, "priv": PRIV, "other": ANY_QUESTION}, timeout=timeout)
        if name == "other":
            console.send("\x03")
            raise SetupStopped(f"The switch asked an unexpected question during {what}; it was cancelled.", sent=True)
        if name == "timeout":
            console.send("\x03")
            raise SetupStopped(f"The switch stopped answering during {what}.", sent=True)
        return name, text

    progress("erasing the saved settings")
    console.send("write erase\r", "write erase")
    name, text = step({"confirm": ERASE_CONFIRM}, 30, "write erase")
    if name == "confirm":
        console.send("\r", "[confirm]")
        name, text = step({}, 120, "write erase")
    if ios_error(text):
        raise SetupStopped(f"write erase was refused: {ios_error(text)}. The switch was not restarted.", sent=True)

    progress("removing the VLAN database")
    console.send("delete flash:vlan.dat\r", "delete flash:vlan.dat")
    name, text = step({"name": DELETE_NAME}, 30, "delete flash:vlan.dat")
    if name == "name":
        console.send("\r", "vlan.dat")
        name, text = step({"confirm": DELETE_CONFIRM}, 30, "delete flash:vlan.dat")
        if name == "confirm":
            console.send("\r", "[confirm]")
            step({}, 60, "delete flash:vlan.dat")

    progress("restarting the switch")
    console.send("reload\r", "reload")
    name, text = step({"save": SAVE_PROMPT, "confirm": RELOAD_CONFIRM}, 30, "reload")
    if name == "save":
        console.send("no\r", "no (do not save the running settings)")
        name, text = step({"confirm": RELOAD_CONFIRM}, 30, "reload")
    if name != "confirm":
        raise SetupStopped("The switch did not start its restart. The settings are erased; restart it by hand (power cycle).", sent=True)
    console.send("\r", "[confirm]")

    progress("waiting for the switch to start again (about 10 minutes)")
    deadline = time.monotonic() + boot_timeout
    while time.monotonic() < deadline:
        name, _text = console.expect({"wizard": WIZARD, "press_return": PRESS_RETURN, "exec": EXEC, "priv": PRIV, "login": LOGIN},
                                     timeout=max(1.0, deadline - time.monotonic()))
        if name == "wizard":
            return {"sent": list(console.sent), "factory": True}
        if name == "press_return":
            console.send("\r")
            continue
        if name in {"exec", "priv", "login"}:
            return {"sent": list(console.sent), "factory": False}
    raise SetupStopped("The switch has not shown its setup dialog 25 minutes after the restart. Check it on the console.", sent=True)
