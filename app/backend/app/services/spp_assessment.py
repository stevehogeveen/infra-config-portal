"""Compare observed HPE identity with bounded, non-executed SPP metadata."""
import hashlib
import io
import re
from functools import lru_cache
from xml.etree import ElementTree as ET

import pycdlib

from app.services.firmware_packages import FirmwarePackageError, media_path, package_unchanged
from app.services.hardware_values import firmware_version, health, pci_identity
from app.services.hardware_health import drive_condition

XML_LIMIT = 24 * 1024**2


def parse_xml(data):
    if len(data) > XML_LIMIT:
        raise FirmwarePackageError("SPP metadata exceeds the inspection size limit.")
    text = data.decode("utf-8-sig")
    if "<!doctype" in text.lower() or "<!entity" in text.lower():
        raise FirmwarePackageError("SPP metadata contains prohibited XML declarations.")
    return ET.fromstring(text)


def xml_from_iso(iso, path):
    if iso.get_record(iso_path=path).data_length > XML_LIMIT:
        raise FirmwarePackageError("SPP metadata exceeds the inspection size limit.")
    output = io.BytesIO()
    iso.get_file_from_iso_fp(output, iso_path=path)
    data = output.getvalue()
    return parse_xml(data), data


def english(node, path):
    if node is None:
        return ""
    elements = node.findall(path)
    return next((item.text or "" for item in elements if item.get("lang") == "en"),
                elements[0].text or "" if elements else "")


def model_key(value):
    value = re.sub(r"\b(?:hpe|hp|proliant|server)\b", "", value.lower())
    return re.sub(r"[^a-z0-9+]", "", value.replace("+", "plus"))


def catalog_from_xml(bundle, systems, meta):
    if bundle.tag != "cpq_bundle" or systems.tag != "manifest" or meta.tag != "manifest":
        raise FirmwarePackageError("Unsupported SPP manifest format.")
    supported = []
    for system in systems.findall("./systems/system"):
        supported.append({"name": english(system, "./name/name_xlate"), "rom": system.get("firmwareid", ""),
                          "versions": {item.get("version") for item in system.findall("./product_version/id")}})
    components = []
    included = {item.text.lower() for item in bundle.findall("./contents/package") if item.text}
    for node in meta.findall("./meta[@lang='en']/product/product_version"):
        identity = node.find("id")
        version = node.find("version")
        kind = node.find("type")
        if identity is None or version is None or kind is None:
            continue
        # Compare OS-independent firmware payloads, never a Windows/Linux driver version.
        if kind.get("id") not in {"universal-fw-ilo", "universal-fw-sys", "universal-fw-generic", "universal-fw-drive",
                                  "smartcomponent-linux-firmware-drive", "smartcomponent-windows-firmware-drive", "smartcomponent-linux-firmware-generic"}:
            continue
        files = [item.text for item in node.findall("./files/file/name") if item.text and item.text.lower() in included]
        if not files:
            continue
        components.append({"id": identity.get("version"), "name": english(node, "./name/name_xlate"),
                           "category": english(node, "./category/category_xlate"),
                           "devices": supported_devices(node),
                           "kind": kind.get("id"), "version": version.get("value", ""), "files": files,
                           "roms": [item.get("rom") for item in node.findall("./products/product")],
                           "vendor_priority": (node.find("upgrade_requirement").get("value", "Unspecified")
                                               if node.find("upgrade_requirement") is not None else "Unspecified")})
    version = bundle.find("version")
    return {"title": english(bundle, "./name/name_xlate"), "release": version.get("value", "") if version is not None else "",
            "systems": supported, "components": components}


def supported_devices(node):
    matches = []
    for group in node.findall("./prerequisites/supported_devices/supported_devices_and"):
        devices = group.findall("supported_device")
        # Compound predicates require SUM; do not weaken AND into OR.
        if len(devices) != 1:
            continue
        device = devices[0]
        matches.append({"type": device.get("type"), **{item.get("name"): (item.text or "").strip()
                        for item in device.findall("supported_device_data")}})
    return matches


@lru_cache(maxsize=4)
def read_catalog(path, size, mtime):
    iso = pycdlib.PyCdlib()
    try:
        iso.open(path)
        baselines = []
        entries = 0
        filenames = set()
        for directory, dirs, files in iso.walk(iso_path="/"):
            entries += len(dirs) + len(files)
            if entries > 20000:
                raise FirmwarePackageError("SPP directory listing exceeds the inspection limit.")
            for name in files:
                clean = name.split(";")[0].lower()
                filenames.add(clean)
                if directory.upper() == "/PACKAGES" and re.fullmatch(r"bp\d+\.xml", clean):
                    baselines.append(directory + "/" + name)
        if len(baselines) != 1:
            raise FirmwarePackageError("A single unambiguous HPE baseline is required.")
        # ISO9660 aliases replace punctuation; HPE manifests use Rock Ridge filenames.
        if iso.has_rock_ridge() or iso.has_joliet():
            namespace = {"rr_path": "/"} if iso.has_rock_ridge() else {"joliet_path": "/"}
            for directory, dirs, files in iso.walk(**namespace):
                entries += len(dirs) + len(files)
                if entries > 40000:
                    raise FirmwarePackageError("SPP directory listing exceeds the inspection limit.")
                if directory.lower() == "/packages":
                    filenames.update(name.split(";")[0].lower() for name in files)
        bundle, raw_bundle = xml_from_iso(iso, baselines[0])
        systems, raw_systems = xml_from_iso(iso, "/MANIFEST/SYSTEM.XML;1")
        meta, raw_meta = xml_from_iso(iso, "/MANIFEST/META.XML;1")
        catalog = catalog_from_xml(bundle, systems, meta)
        for component in catalog["components"]:
            component["files_present"] = all(name.lower() in filenames for name in component["files"])
        catalog["metadata_sha256"] = hashlib.sha256(raw_bundle + raw_systems + raw_meta).hexdigest()
        return catalog
    except FirmwarePackageError:
        raise
    except Exception:
        raise FirmwarePackageError("SPP model and component manifests could not be parsed. The package may be incomplete or use an unsupported format.") from None
    finally:
        try:
            iso.close()
        except Exception:
            pass


def load_catalog(package):
    if not package_unchanged(package):
        raise FirmwarePackageError("Selected ISO is missing or changed. Inspect and select it again.")
    catalog = read_catalog(str(media_path(package["path"])), package["size_bytes"], package["modified_ns"])
    if not package_unchanged(package):
        raise FirmwarePackageError("Selected ISO changed during assessment. Reinspect it.")
    return catalog


def numeric_version(value, kind):
    if kind == "drive":
        match = re.fullmatch(r"HPD(\d+)", value, re.I)
        return (int(match.group(1)),) if match else None
    # Only documented iLO / ROM display forms; unknown vendor formats stay unknown.
    pattern = (r"^(?:iLO\s+\d+\s+v?)?(\d+(?:\.\d+)+)(?:$|\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{4}$)"
               if kind == "ilo" else r"^(?:[A-Z]\d{2}\s+v?)?(\d+(?:\.\d+)+)(?:$|\s+\(\d{2}/\d{2}/\d{4}\)$|_\d{2}-\d{2}-\d{4}$)")
    match = re.fullmatch(pattern, value.strip(), re.IGNORECASE)
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def comparison_row(label, installed, candidates, kind):
    row = {"component": label, "installed": installed or None, "target": None,
           "status": "Cannot determine", "reason": "No single matching package component and installed version.", "files": []}
    unique = {item["version"]: item for item in candidates}
    if len(unique) != 1 or not installed:
        return row
    candidate = next(iter(unique.values()))
    row.update(target=candidate["version"], files=sorted({file for item in candidates for file in item["files"]}), vendor_priority=candidate["vendor_priority"])
    if not candidate.get("files_present", False):
        row["reason"] = "Manifest references a firmware payload that is missing from this ISO."
        return row
    old = numeric_version(installed, kind)
    new = numeric_version(candidate["version"], kind)
    if old is None or new is None:
        row["reason"] = "Version format is not supported for automatic ordering."
        return row
    width = max(len(old), len(new))
    old += (0,) * (width - len(old))
    new += (0,) * (width - len(new))
    row["status"] = "Update available" if old < new else "Matches package" if old == new else "Installed newer"
    row["reason"] = ("Newer matching firmware is in this SPP. Upgrade prerequisites still require approval."
                     if old < new else "Numeric firmware version matches; no version increase in this SPP."
                     if old == new else "Do not downgrade to this package version.")
    return row


def assess(catalog, probe, planned_model):
    result = {"status": "Cannot determine", "detected_model": None, "planned_model": planned_model,
              "identity_mismatch": False, "rom_family": None, "package_title": catalog["title"],
              "package_release": catalog["release"], "metadata_sha256": catalog["metadata_sha256"],
              "checked_at": probe.get("checked_at"), "rows": [], "apply_enabled": False,
              "limitations": "Version comparison only. HPE SUM must validate prerequisites, signatures, dependencies and the installation method before updates. Unknown components are not cleared for installation."}
    systems = probe.get("systems") or []
    if len(systems) != 1 or not systems[0].get("Model"):
        result["reason"] = "A single detected server model is required from iLO."
        return result
    model = systems[0]["Model"]
    result.update(detected_model=model, identity_mismatch=bool(planned_model and model_key(planned_model) != model_key(model)))
    matches = [system for system in catalog["systems"] if model_key(system["name"]) == model_key(model)]
    if not matches:
        result.update(status="Incompatible package", reason="The detected server model is not listed in this SPP system manifest.")
        return result
    bios = systems[0].get("BiosVersion") or systems[0].get("BIOSVersion") or ""
    observed_rom = re.match(r"^([A-Z]\d{2})\b", bios, re.IGNORECASE)
    if len(matches) != 1 or (observed_rom and observed_rom.group(1).upper() != matches[0]["rom"].upper()):
        result["reason"] = "Detected model and ROM family are ambiguous or inconsistent."
        return result
    system = matches[0]
    result["rom_family"] = system["rom"]
    eligible = [item for item in catalog["components"] if item["id"] in system["versions"] and system["rom"] in item["roms"]]
    managers = probe.get("managers") or []
    ilo = managers[0].get("FirmwareVersion", "") if len(managers) == 1 else ""
    ilo_gen = re.search(r"\biLO\s*(\d+)\b", ilo, re.IGNORECASE)
    ilo_candidates = [item for item in eligible if item["kind"] == "universal-fw-ilo" and ilo_gen
                      and re.search(r"(?:Lights-Out|iLO)\s*" + re.escape(ilo_gen.group(1)) + r"\b", item["name"], re.IGNORECASE)]
    rows = [comparison_row("iLO", ilo, ilo_candidates, "ilo"),
            comparison_row("System ROM / BIOS", bios, [item for item in eligible if item["kind"] == "universal-fw-sys" and item["roms"] == [system["rom"]]], "bios")]
    rows.extend(component_rows(catalog, probe, system))
    result["rows"] = rows
    result["status"] = "Updates available" if any(row["status"] == "Update available" for row in rows) else "Partial assessment"
    result["reason"] = ("Newer firmware found for matched components; unassessed components are listed below."
                        if result["status"] == "Updates available" else "Review component results. Unassessed hardware prevents a whole-server up-to-date verdict.")
    return result


def _location_text(value) -> str:
    """Redfish Location objects become their label ("Slot 0"), never a printed dictionary."""
    if isinstance(value, dict):
        part = value.get("PartLocation") if isinstance(value.get("PartLocation"), dict) else value
        label = part.get("ServiceLabel") or (f"{part.get('LocationType')} {part.get('LocationOrdinalValue')}" if part.get("LocationType") else "")
        return str(label or "").replace("=", " ")
    return str(value or "")


def component_rows(catalog, probe, system):
    storage = probe.get("storage") or {}
    pci = probe.get("pci_devices", [])
    networks = [r for r in probe.get("network_adapters", []) if firmware_version(r) or r.get("Model")]
    if not networks:
        networks = [r for r in pci if r.get("ClassCode") == 2 or any(w in str(r.get("Name", "")).lower() for w in ["ethernet", "network", "flexlom"])]
    groups = [("Storage controller", [r for r in storage.get("controllers", []) if r.get("Model")], "numeric"),
              ("Drive", storage.get("physical_drives", []), "drive"),
              ("Network adapter", networks, "numeric")]
    rows = []
    for label, resources, kind in groups:
        if not resources:
            rows.append({"component": label, "installed": None, "target": None, "status": "Cannot determine", "files": [],
                         "reason": "iLO did not return sufficient component identity. Refresh inventory; HPE SUM may be needed for discovery."})
        for resource in resources:
            model = resource.get("Model") or ("Unidentified drive" if label == "Drive" else resource.get("Name")) or "Unidentified hardware"
            location = _location_text(resource.get("Location")) or resource.get("Id") or ""
            matches = []
            unsupported = []
            utilities = []
            identity = pci_identity(resource)
            if label != "Drive" and len(identity) != 4:
                # Same reported model, one exact PCI product identity. Never substring-match a product family.
                key = model_key(re.sub(r"\s*-\s*NIC$", "", model, flags=re.I))
                aliases = [p for p in pci if model_key(re.sub(r"\s*-\s*NIC$", "", p.get("Name", ""), flags=re.I)) == key]
                identities = {tuple(sorted(pci_identity(p).items())) for p in aliases if len(pci_identity(p)) == 4}
                if len(identities) == 1:
                    identity = dict(next(iter(identities)))
            for component in catalog["components"]:
                if not component.get("files_present"):
                    continue
                destination = unsupported if component.get("roms") and system["rom"] not in component["roms"] else utilities if component["kind"] == "smartcomponent-linux-firmware-generic" else matches
                for supported in component.get("devices", []):
                    if label == "Drive" and supported.get("type") in {"sas", "sata", "scsi"} and set(supported) == {"type", "id"} and model.upper() == supported.get("id", "").upper():
                        destination.append(component)
                    elif label != "Drive" and supported.get("type") == "pci" and set(supported) == {"type", "ven", "dev", "subven", "subdev"} and all(identity.get(k) == supported[k].lower().removeprefix("0x").zfill(4) for k in ["ven", "dev", "subven", "subdev"]):
                        destination.append(component)
            row = comparison_row(f"{label}: {model}" + (f" / {location}" if location else ""), firmware_version(resource), matches, kind)
            row.update(health=drive_condition(resource)["health"] if label == "Drive" else health(resource), model=model, location=str(location), group=label)
            if row["installed"] and row["status"] == "Cannot determine" and not matches:
                row["reason"] = "Installed version read. No exact hardware-ID match found in the selected SPP; this does not mean up to date."
                if label == "Drive":
                    row["reason"] += " This is a firmware matching limitation, not evidence that the drive has failed."
                if unsupported:
                    row["reason"] = f"PCI hardware matches a package, but its supported server ROM list does not include {system['rom']}. HPE compatibility review required; do not install based on the adapter match alone."
                    row["files"] = sorted({f for c in unsupported for f in c["files"]})
                elif utilities:
                    row["reason"] = "Matching firmware update utility found. Its utility version is not the adapter firmware version; HPE SUM must inspect the embedded firmware before comparison."
                    row["files"] = sorted({f for c in utilities for f in c["files"]})
            if row["health"] not in {"OK", "Unknown"}:
                row["reason"] = f"Hardware health: {row['health']}. Resolve this before rebuilding. " + row["reason"]
            rows.append(row)
    # The iLO can list one controller twice (HPE and standard Redfish views); show it once.
    unique, seen = [], set()
    # Drives come twice as well: once with their bay ("2I:1:5") and once with a bare index ("4").
    with_bays = {row["component"].split(" / ")[0] for row in rows if row["component"].startswith("Drive: ") and ":" in row["component"].split(" / ")[-1]}
    rows = [row for row in rows if not (row["component"].startswith("Drive: ") and row["component"].split(" / ")[0] in with_bays
                                         and ":" not in row["component"].split(" / ")[-1])]
    for row in rows:
        key = (row["component"], row.get("installed"))
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique
