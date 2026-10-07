import pytest
from app.services.erase_options import erase_options


@pytest.mark.parametrize("model", ["HPE DL360 Gen10", "HPE DL360 Gen10 Plus", "HPE DL380 Gen11"])
def test_generation_never_implies_an_execution_adapter(model):
    probe = {"systems":[{"Model":model}], "storage":{"physical_drives":[{"MediaType":"HDD"}]}}
    catalog = erase_options(probe, current=True)
    assert catalog["models"] == [model]
    assert not any(o["selectable"] for o in catalog["options"])
    assert "validated erase execution path" in catalog["options"][0]["reason"]


@pytest.mark.parametrize("media,enabled", [
    (["HDD"], {"auto","OnePass","SanitizeRestrictedOverwrite"}),
    (["SSD"], {"auto","SanitizeRestrictedBlockErase"}),
    (["HDD","SSD"], {"auto"}),
    (["Unknown"], set()),
    ([], set()),
])
def test_options_follow_drive_media_not_server_name(media, enabled):
    catalog = erase_options({"storage":{"physical_drives":[{"MediaType":m} for m in media]}},
                            executor_available=True,current=True,arrays_present=False)
    assert {o["id"] for o in catalog["options"] if o["selectable"]} == enabled
    assert all(o["status"] != "Supported" for o in catalog["options"])
    assert "NOT secure erasure" in catalog["reset"]["protection"]


def test_stale_evidence_cannot_offer_execution_or_identify_current_device():
    catalog = erase_options({"systems":[{"Model":"Old server"}],
        "storage":{"physical_drives":[{"MediaType":"HDD"}]}},executor_available=True,current=False)
    assert not catalog["models"] and not any(o["selectable"] for o in catalog["options"])
