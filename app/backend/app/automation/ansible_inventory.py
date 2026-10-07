import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from app.automation.contracts import SystemFact
from app.automation.targets import AutomationBlocked

PROJECT = Path(__file__).resolve().parents[3] / "automation"
RESULT_TASK = "Export system inventory"


def normalize_systems(facts: dict) -> list[SystemFact]:
    system = facts.get("system", {})
    if not isinstance(system, dict) or system.get("ret") is not True:
        raise AutomationBlocked("The inventory module did not return system evidence.")
    result = []
    # community.general aggregates systems as [resource metadata, properties].
    for entry in system.get("entries", []):
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise AutomationBlocked("The inventory module returned an unsupported system shape.")
        properties = entry[1]
        if not isinstance(properties, dict):
            raise AutomationBlocked("The inventory module returned invalid system properties.")

        def value(key):
            item = properties.get(key)
            return item[:300] if isinstance(item, str) and item else None

        fact = SystemFact(
            model=value("Model"),
            manufacturer=value("Manufacturer"),
            serial_number=value("SerialNumber"),
            power_state=value("PowerState"),
        )
        if not fact.model and not fact.serial_number:
            raise AutomationBlocked("The controller returned no usable system identity.")
        result.append(fact)
    if not result:
        raise AutomationBlocked("The controller returned no systems.")
    return result


def run_inventory(config) -> list[SystemFact]:
    # Runner is a worker-only dependency. The API never imports or invokes Ansible.
    import ansible_runner

    facts = {}

    def event_handler(event):
        data = event.get("event_data", {})
        if event.get("event") == "runner_on_ok" and data.get("task") == RESULT_TASK:
            facts.update(data.get("res", {}).get("ansible_stats", {}).get("data", {}))
        return False

    with TemporaryDirectory(prefix="inventory-") as directory:
        private = Path(directory)
        os.chmod(private, 0o700)
        env = private / "env"
        env.mkdir(mode=0o700)
        # JSON is valid Ansible vars input; credentials are never templated into
        # command text, command-line arguments, or the persistent event stream.
        variables = {
            "inventory_host": config.host,
            "inventory_username": config.username,
            "inventory_password": config.password,
            "inventory_verify_tls": config.verify_tls,
        }
        path = env / "extravars"
        path.write_text(json.dumps(variables), encoding="utf-8")
        os.chmod(path, 0o600)
        runner = ansible_runner.run(
            private_data_dir=directory,
            project_dir=str(PROJECT),
            playbook="playbooks/ilo_inventory.yml",
            inventory={"all": {"hosts": {"controller": {"ansible_connection": "local"}}}},
            event_handler=event_handler,
            quiet=True,
            settings={"job_timeout": 120, "suppress_ansible_output": True},
            envvars={
                "ANSIBLE_DISPLAY_ARGS_TO_STDOUT": "False",
                "ANSIBLE_LOG_PATH": os.devnull,
                "ANSIBLE_LOCAL_TEMP": str(private / "ansible-tmp"),
                "ANSIBLE_REMOTE_TEMP": str(private / "remote-tmp"),
            },
        )
        if runner.rc != 0 or runner.status != "successful":
            raise AutomationBlocked(
                "Ansible inventory failed. Check the device address, credentials, TLS trust, "
                "and Redfish support using the existing Access check."
            )
    return normalize_systems(facts)
