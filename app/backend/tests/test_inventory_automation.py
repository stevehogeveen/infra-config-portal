from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import fakeredis
import pytest
from rq import Queue, SimpleWorker
from rq.serializers import JSONSerializer
from rq.timeouts import TimerDeathPenalty
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
import yaml

from app.automation import ansible_inventory, queue, targets, tasks
from app.automation.contracts import SystemFact
from app.models import AuditEvent, DeviceInventory, IloDeviceCredential


class InProcessWorker(SimpleWorker):
    death_penalty_class = TimerDeathPenalty


@pytest.fixture
def automation(db_session, monkeypatch):
    connection = fakeredis.FakeRedis()
    test_queue = Queue("inventory", connection=connection, serializer=JSONSerializer)
    monkeypatch.setattr(queue, "inventory_queue", lambda: test_queue)
    monkeypatch.setattr(tasks, "SessionLocal", sessionmaker(bind=db_session.bind))
    db_session.add(
        DeviceInventory(
            id="fixture-a",
            device_type="ilo",
            display_name="Fixture A",
            host="ilo-a.example.test",
        )
    )
    db_session.add(
        IloDeviceCredential(
            device_id="fixture-a",
            credentials_json={
                "host": "ilo-a.example.test",
                "username": "fixture-user",
                "password": "fixture-secret",
            },
        )
    )
    db_session.commit()
    monkeypatch.setattr(tasks, "run_inventory", lambda _: pytest.fail("Mock must not run Ansible"))
    return test_queue


def run_worker(test_queue):
    worker = InProcessWorker(
        [test_queue], connection=test_queue.connection, serializer=JSONSerializer
    )
    worker.work(burst=True, logging_level="WARNING")


def test_api_queue_worker_and_latest_result(client, db_session, automation):
    response = client.post("/api/v1/devices/fixture-a/inventory-jobs", json={})
    assert response.status_code == 202
    body = response.json()
    job = automation.fetch_job(body["job_id"])
    assert "fixture-secret" not in json.dumps(job.args)
    assert "ilo-a.example.test" not in json.dumps(job.args)
    assert body["status"] == "queued"
    run_worker(automation)
    response = client.get("/api/v1/devices/fixture-a/inventory-jobs")
    result = response.json()
    assert result["status"] == "completed", result["result"]["summary"]
    assert result["current"] is False
    assert result["result"]["source"] == "mock"
    assert result["result"]["systems"] == []
    events = list(db_session.scalars(select(AuditEvent)))
    assert {event.event_type for event in events} == {
        "automation.inventory.queued",
        "automation.inventory.finished",
    }


def test_rejects_client_execution_options_and_wrong_device(client, automation):
    for payload in [
        {"playbook": "/tmp/other.yml"},
        {"operation": "raid.apply"},
        {"host": "elsewhere.test"},
    ]:
        assert (
            client.post("/api/v1/devices/fixture-a/inventory-jobs", json=payload).status_code == 422
        )
    response = client.post("/api/v1/devices/fixture-a/inventory-jobs", json={}).json()
    assert (
        client.get(f"/api/v1/devices/fixture-b/inventory-jobs/{response['job_id']}").status_code
        == 404
    )
    assert client.post("/api/v1/devices/missing/inventory-jobs", json={}).status_code == 404


def test_target_change_before_execution_blocks_and_new_job_uses_new_target(
    client, db_session, automation
):
    first = client.post("/api/v1/devices/fixture-a/inventory-jobs", json={}).json()
    record = db_session.get(IloDeviceCredential, "fixture-a")
    record.credentials_json = {**record.credentials_json, "host": "moved.example.test"}
    db_session.commit()
    run_worker(automation)
    result = client.get(f"/api/v1/devices/fixture-a/inventory-jobs/{first['job_id']}").json()
    assert result["status"] == "blocked"
    assert result["result"]["systems"] == []
    second = client.post("/api/v1/devices/fixture-a/inventory-jobs", json={}).json()
    run_worker(automation)
    assert (
        client.get(f"/api/v1/devices/fixture-a/inventory-jobs/{second['job_id']}").json()["status"]
        == "completed"
    )


def test_profile_and_mode_changes_block(client, automation, monkeypatch):
    client.post("/api/v1/devices/fixture-a/inventory-jobs", json={})
    monkeypatch.setattr(tasks, "profile_revision", lambda: "changed")
    run_worker(automation)
    assert client.get("/api/v1/devices/fixture-a/inventory-jobs").json()["status"] == "blocked"
    assert targets.execution_blockers(SimpleNamespace(), "local-readonly")


def test_target_change_during_executor_discards_result(db_session, automation, monkeypatch):
    job = queue.enqueue_inventory(db_session, "fixture-a", "operator")
    envelope = automation.fetch_job(job.job_id).args[0]
    envelope["provider_mode"] = "local-readonly"
    monkeypatch.setattr(tasks, "execution_blockers", lambda *_: [])

    def moved(config):
        credential = db_session.get(IloDeviceCredential, "fixture-a")
        credential.credentials_json = {**credential.credentials_json, "host": "moved.example.test"}
        db_session.commit()
        return [SystemFact(model="Fixture")]

    monkeypatch.setattr(tasks, "run_inventory", moved)
    result = tasks.execute_inventory(envelope)
    assert result["status"] == "blocked"
    assert result["systems"] == []


def test_exception_does_not_expose_credentials(db_session, automation, monkeypatch):
    job = queue.enqueue_inventory(db_session, "fixture-a", "operator")
    envelope = automation.fetch_job(job.job_id).args[0]
    envelope["provider_mode"] = "local-readonly"
    monkeypatch.setattr(tasks, "execution_blockers", lambda *_: [])

    def failed(config):
        raise RuntimeError(config.password)

    monkeypatch.setattr(tasks, "run_inventory", failed)
    result = tasks.execute_inventory(envelope)
    assert result["status"] == "failed"
    assert "fixture-secret" not in json.dumps(result)


def test_runner_contract_and_private_variables(db_session, automation, monkeypatch):
    config, _ = targets.resolve_target(db_session, "fixture-a")
    directories = []

    def fake_run(**kwargs):
        private = Path(kwargs["private_data_dir"])
        directories.append(private)
        variables = json.loads((private / "env" / "extravars").read_text())
        assert variables["inventory_host"] == config.host
        assert variables["inventory_password"] == "fixture-secret"
        assert kwargs["inventory"]["all"]["hosts"] == {
            "controller": {"ansible_connection": "local"}
        }
        assert kwargs["playbook"] == "playbooks/ilo_inventory.yml"
        assert (
            kwargs["event_handler"](
                {
                    "event": "runner_on_ok",
                    "event_data": {
                        "task": "Export system inventory",
                        "res": {
                            "ansible_stats": {
                                "data": {
                                    "system": {
                                        "ret": True,
                                        "entries": [
                                            [
                                                {"system_uri": "/redfish/v1/Systems/1"},
                                                {
                                                    "Model": "Fixture",
                                                    "SerialNumber": "fixture-serial",
                                                    "Password": "must-not-escape",
                                                },
                                            ]
                                        ],
                                    }
                                }
                            }
                        },
                    },
                }
            )
            is False
        )
        return SimpleNamespace(rc=0, status="successful")

    monkeypatch.setitem(sys.modules, "ansible_runner", SimpleNamespace(run=fake_run))
    facts = ansible_inventory.run_inventory(config)
    assert facts[0].model == "Fixture"
    assert "must-not-escape" not in facts[0].model_dump_json()
    assert all(not directory.exists() for directory in directories)


@pytest.mark.parametrize(
    "system",
    [
        {"ret": False, "entries": []},
        {"ret": True, "entries": []},
        {"ret": True, "entries": [{"Model": "unexpected-shape"}]},
    ],
)
def test_no_false_inventory_on_module_failures(system):
    with pytest.raises(targets.AutomationBlocked):
        ansible_inventory.normalize_systems({"system": system})


def test_playbook_is_fixed_readonly_operation():
    play = yaml.safe_load((ansible_inventory.PROJECT / "playbooks/ilo_inventory.yml").read_text())[
        0
    ]
    assert play["gather_facts"] is False
    inventory, export = play["tasks"]
    assert inventory["community.general.redfish_info"]["command"] == "GetSystemInventory"
    assert inventory["no_log"] is True
    assert export["name"] == ansible_inventory.RESULT_TASK


def test_queue_unconfigured_reports_blocker(monkeypatch):
    monkeypatch.delenv("AUTOMATION_REDIS_URL", raising=False)
    with pytest.raises(targets.AutomationBlocked, match="not configured"):
        queue.inventory_queue()


def test_observations_expire_and_access_change_invalidates_them(
    db_session, automation, monkeypatch
):
    submitted = queue.enqueue_inventory(db_session, "fixture-a", "operator")
    job = automation.fetch_job(submitted.job_id)
    envelope = dict(job.args[0])
    envelope["provider_mode"] = "local-readonly"
    monkeypatch.setattr(job, "_args", (envelope,))
    monkeypatch.setattr(queue, "settings", SimpleNamespace(provider_mode="local-readonly"))
    result = {
        "device_id": "fixture-a",
        "status": "completed",
        "source": "ansible",
        "checked_at": datetime.now(UTC).isoformat(),
        "summary": "Fixture observation.",
        "systems": [{"model": "Fixture"}],
    }
    monkeypatch.setattr(job, "get_status", lambda **_: SimpleNamespace(value="finished"))
    monkeypatch.setattr(job, "return_value", lambda: result)
    monkeypatch.setattr(automation, "fetch_job", lambda _: job)
    assert queue.read_inventory_run(db_session, "fixture-a", job.id).current
    result["checked_at"] = (datetime.now(UTC) - timedelta(minutes=6)).isoformat()
    assert not queue.read_inventory_run(db_session, "fixture-a", job.id).current
    result["checked_at"] = datetime.now(UTC).isoformat()
    credential = db_session.get(IloDeviceCredential, "fixture-a")
    credential.credentials_json = {**credential.credentials_json, "host": "changed.example.test"}
    db_session.commit()
    assert not queue.read_inventory_run(db_session, "fixture-a", job.id).current


def test_compose_worker_is_isolated_and_defaults_to_mock():
    path = Path(__file__).resolve().parents[2] / "docker-compose.automation.yml"
    services = yaml.safe_load(path.read_text())["services"]
    worker = services["automation-worker"]
    assert worker["environment"]["PROVIDER_MODE"] == "mock"
    assert worker["read_only"] is True
    assert worker["cap_drop"] == ["ALL"]
    assert "ports" not in services["redis"]
    assert all("docker.sock" not in mount for mount in worker["volumes"])
