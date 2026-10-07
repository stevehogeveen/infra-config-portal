from copy import deepcopy

import pytest

from app.services.spp_assessment import assess, comparison_row, parse_xml, catalog_from_xml
from app.services.firmware_packages import FirmwarePackageError


def catalog():
    return {"title": "Gen10 SPP", "release": "2026.05", "metadata_sha256": "fixture",
            "systems": [{"name": "HPE ProLiant DL360 Gen10 Server", "rom": "U32", "versions": {"ilo", "rom"}}],
            "components": [{"id": ident, "name": name, "kind": kind, "version": version,
                            "files": [ident + ".fwpkg"], "roms": ["U32"], "files_present": True,
                            "vendor_priority": "Optional"}
                           for ident, name, kind, version in [
                               ("ilo", "HPE Integrated Lights-Out 5", "universal-fw-ilo", "3.19"),
                               ("rom", "DL360 Gen10 U32", "universal-fw-sys", "3.66_04-01-2026")]]}


def probe():
    return {"systems": [{"Model": "ProLiant DL360 Gen10", "BiosVersion": "U32 v1.46 (10/02/2018)"}],
            "managers": [{"FirmwareVersion": "iLO 5 v1.37"}]}


def test_detected_identity_overrides_planned_label():
    result = assess(catalog(), probe(), "HPE DL360 Gen11")
    assert result["identity_mismatch"]
    assert result["detected_model"] == "ProLiant DL360 Gen10"
    assert [row["status"] for row in result["rows"][:2]] == ["Update available"] * 2
    assert all(row["status"] == "Cannot determine" for row in result["rows"][2:])
    assert not result["apply_enabled"]


def test_wrong_generation_or_rom_never_approved():
    observation = probe()
    observation["systems"][0]["Model"] = "ProLiant DL360 Gen11"
    assert assess(catalog(), observation, "HPE DL360 Gen10")["status"] == "Incompatible package"
    observation = probe()
    observation["systems"][0]["BiosVersion"] = "U46 v1.46 (10/02/2018)"
    assert assess(catalog(), observation, "")["status"] == "Cannot determine"


@pytest.mark.parametrize("installed,status", [("3.19", "Matches package"), ("3.20", "Installed newer"), ("unknown", "Cannot determine")])
def test_version_ordering(installed, status):
    assert comparison_row("iLO", installed, [catalog()["components"][0]], "ilo")["status"] == status


def test_ambiguous_missing_and_unmapped_components():
    c = catalog()
    duplicate = deepcopy(c["components"][0])
    duplicate["version"] = "4.0"
    c["components"].append(duplicate)
    assert assess(c, probe(), "")["rows"][0]["status"] == "Cannot determine"
    c = catalog()
    c["components"][0]["files_present"] = False
    c["components"][1]["id"] = "not-supported-for-system"
    assert all(row["status"] == "Cannot determine" for row in assess(c, probe(), "")["rows"])


def test_xml_rejects_entity_expansion_and_drivers():
    with pytest.raises(FirmwarePackageError):
        parse_xml(b'<!DOCTYPE foo [<!ENTITY x "value">]><foo>&x;</foo>')
    bundle = parse_xml(b'<cpq_bundle><contents><package>driver.exe</package></contents></cpq_bundle>')
    systems = parse_xml(b'<manifest/>')
    meta = parse_xml(b'<manifest><meta lang="en"><product><product_version><id version="driver"/><type id="driver"/><version value="99.0"/><files><file><name>driver.exe</name></file></files></product_version></product></meta></manifest>')
    assert catalog_from_xml(bundle, systems, meta)["components"] == []


def test_api_requires_kit_membership_current_target_and_package(client, db_session, monkeypatch):
    from app.api import rack_plans
    from app.services.audit import record_audit_event
    kit = client.post("/api/v1/lab/profiles", json={"name":"Assessment kit", "profile_topology":"custom", "subnet_cidr":"192.0.2.0/24"}).json()
    base = f"/api/v1/rack-plans/{kit['id']}"
    saved = client.put(base, json={"equipment":[{"id":"s", "name":"Server", "kind":"server", "model":"HPE DL360 Gen11", "position":1, "height":1}]}).json()
    device = saved["equipment"][0]["device_id"]
    url = base + "/firmware-assessment?device_id=" + device
    assert client.get(base + "/firmware-assessment?device_id=unknown").status_code == 404
    assert "Select an SPP" in client.get(url).json()["reason"]
    record_audit_event(db_session, actor="test", event_type="kit.firmware_package_selected", message="Fixture", data={"profile_id":kit['id'], "package":{"file_name":"fixture.iso"}})
    db_session.commit()
    state = {"last_probe_is_current":False,"last_probe_target_matches_access_host":True,"last_probe_status":"ok"}
    monkeypatch.setattr(rack_plans, "read_ilo_access_settings", lambda *a:state)
    monkeypatch.setattr(rack_plans, "get_probe_result", lambda *a, **kw: ({**probe(),"status":"ok"}, "2026-09-14T12:00:00Z"))
    monkeypatch.setattr(rack_plans, "load_catalog", lambda *a:catalog())
    assert client.get(url).json()["status"] == "Cannot determine"
    state["last_probe_is_current"] = True
    state["last_probe_target_matches_access_host"] = False
    assert client.get(url).json()["status"] == "Cannot determine"
    state["last_probe_target_matches_access_host"] = True
    assert client.get(url).json()["status"] == "Updates available"
    assert client.get(url).json()["identity_mismatch"]
    def changed(*a):
        raise FirmwarePackageError("Selected ISO changed")
    monkeypatch.setattr(rack_plans, "load_catalog", changed)
    assert client.get(url).json()["status"] == "Cannot determine"


def test_exact_drive_identity_and_nested_version():
    c = catalog()
    c['components'].append({'id':'drive','name':'Drive firmware','kind':'smartcomponent-linux-firmware-drive',
                           'version':'HPD9','files':['drive.rpm'],'roms':[],'files_present':True,'vendor_priority':'Recommended',
                           'devices':[{'type':'sas','id':'EXACTMODEL'}]})
    p = probe()
    p['storage']={'physical_drives':[{'Model':'EXACTMODEL','Location':'1I:1:1','FirmwareVersion':{'Current':{'VersionString':'HPD1'}},'Status':{'Health':'OK'}},
                                   {'Model':'EXACTMODEL-X','Location':'1I:1:2','FirmwareVersion':{'Current':{'VersionString':'HPD1'}},'Status':{'Health':'Critical'}}]}
    drives=[r for r in assess(c,p,'')['rows'] if r.get('group')=='Drive']
    assert drives[0]['status']=='Update available'
    assert drives[1]['status']=='Cannot determine'
    assert drives[1]['health']=='Critical'


def test_pci_identity_match_and_server_support_are_both_required():
    c=catalog()
    component={'id':'controller','name':'Fixture firmware','kind':'universal-fw-generic','version':'8.00','files':['controller.fwpkg'],
               'roms':['U32'],'files_present':True,'vendor_priority':'Recommended','devices':[{'type':'pci','ven':'9005','dev':'028f','subven':'103c','subdev':'0602'}]}
    c['components'].append(component)
    p=probe()
    p['storage']={'controllers':[{'Model':'Fixture controller','FirmwareVersion':{'Current':{'VersionString':'1.66'}}}]}
    p['pci_devices']=[{'Name':'Fixture controller','VendorID':0x9005,'DeviceID':0x028f,'SubsystemVendorID':0x103c,'SubsystemDeviceID':0x0602}]
    row=next(r for r in assess(c,p,'')['rows'] if r.get('group')=='Storage controller')
    assert row['status']=='Update available'
    component['roms']=['U46']
    row=next(r for r in assess(c,p,'')['rows'] if r.get('group')=='Storage controller')
    assert row['status']=='Cannot determine'
    assert 'does not include U32' in row['reason']
