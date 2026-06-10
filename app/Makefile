PYTHON ?= python3
BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV := $(BACKEND_DIR)/.venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python
REPO_ROOT := $(abspath ..)
PROVIDER_MODE ?= local-lab-readwrite
PROVIDER_SMOKE_PROVIDERS ?=
BACKEND_PORT ?= 8001
FRONTEND_PORT ?= 5173

.PHONY: backend-venv backend-run backend-test frontend-install frontend-run up down start stop restart status check codex-audit codex-task codex-next codex-resume test dev lint provider-smoke provider-smoke-ilo-readonly provider-smoke-ilo-local-lab provider-inventory-ilo-local-lab provider-lab-live-status provider-lab-refresh-live-state provider-lab-build-verification-live provider-lab-ilo-reachability provider-lab-ilo-authentication provider-lab-ilo-inventory provider-lab-ilo-readiness provider-lab-firmware-inventory provider-lab-firmware-cisco-inventory provider-lab-cisco-firmware-cisco-inventory provider-lab-firmware-compliance provider-lab-firmware-compliance-scope-cisco provider-lab-firmware-compliance-scope-hpe provider-lab-firmware-compliance-scope-full provider-lab-firmware-waiver-check provider-lab-hpe-storage-discovery provider-lab-hpe-raid-discovery provider-lab-hpe-raid-plan provider-lab-hpe-raid-debug provider-lab-hpe-raid-pending provider-lab-server-reset-for-raid provider-lab-hpe-raid-validate-after-reset provider-lab-esxi-install-readiness provider-lab-esxi-media-url provider-lab-esxi-insert-virtual-media provider-lab-esxi-eject-virtual-media provider-lab-esxi-one-time-boot provider-lab-esxi-reset-installer-boot provider-lab-esxi-detect-installer provider-lab-cisco-console-ethernet-readiness provider-lab-cisco-console-recovery provider-lab-cisco-privilege-check provider-lab-cisco-vlan10-bootstrap-fix provider-lab-cisco-vlan10-bootstrap-apply provider-lab-full-rebuild-summary provider-lab-full-rebuild provider-lab-build-verification provider-lab-validation provider-lab-vcenter-netapp-readiness provider-lab-vcenter-netapp-datastore-plan provider-lab-toolchain-check provider-lab-hpe-raid-apply provider-lab-serial-console-discovery provider-lab-netapp-console-autodiscovery provider-lab-netapp-console-discovery provider-lab-netapp-console-read-state provider-lab-netapp-console-login-state provider-lab-netapp-live-state provider-lab-netapp-validate-setup provider-lab-netapp-nfs-vcenter-readiness netapp-real-readiness
.PHONY: provider-lab-netapp-setup-baseline provider-lab-netapp-setup-plan provider-lab-netapp-setup-preview provider-lab-netapp-setup-apply provider-lab-netapp-post-setup-validation provider-lab-netapp-ontap-upgrade-inventory provider-lab-netapp-ontap-upgrade-plan provider-lab-netapp-ontap-upgrade-validate provider-lab-netapp-ontap-upgrade-apply

backend-venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r $(BACKEND_DIR)/requirements.txt

backend-run:
	cd $(BACKEND_DIR) && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port $(BACKEND_PORT)

backend-test:
	cd $(BACKEND_DIR) && PROVIDER_MODE=mock .venv/bin/pytest -q

frontend-install:
	cd $(FRONTEND_DIR) && npm install

frontend-run:
	cd $(FRONTEND_DIR) && npm run dev -- --host 127.0.0.1 --port $(FRONTEND_PORT)

up:
	docker compose up --build

down:
	docker compose down

start:
	$(REPO_ROOT)/runit start

stop:
	$(REPO_ROOT)/runit stop

restart:
	$(REPO_ROOT)/runit restart

status check:
	$(REPO_ROOT)/runit status

codex-audit codex-task codex-next codex-resume test dev lint:
	@echo "Error: Run this from $(REPO_ROOT), not $(CURDIR)." >&2
	@exit 2

.PHONY: backend-smoke smoke
backend-smoke:
	cd backend && PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_smoke_vm_lifecycle.py

smoke: backend-smoke

provider-smoke:
	cd backend && PROVIDER_MODE="$(PROVIDER_MODE)" PROVIDER_SMOKE_PROVIDERS="$(PROVIDER_SMOKE_PROVIDERS)" PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/provider_smoke.py

provider-lab-live-status:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/provider_lab_live_status.py

provider-lab-refresh-live-state: provider-lab-live-status

provider-lab-build-verification-live: provider-lab-build-verification

provider-smoke-ilo-readonly:
	$(MAKE) provider-smoke PROVIDER_MODE=local-readonly PROVIDER_SMOKE_PROVIDERS=ilo-redfish

provider-smoke-ilo-local-lab:
	$(MAKE) provider-smoke PROVIDER_MODE=local-lab-readwrite PROVIDER_SMOKE_PROVIDERS=ilo-redfish

provider-inventory-ilo-local-lab: provider-smoke-ilo-local-lab

provider-lab-ilo-reachability:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/ilo_real_reachability.py

provider-lab-ilo-authentication:
	$(MAKE) provider-smoke PROVIDER_MODE=local-lab-readwrite PROVIDER_SMOKE_PROVIDERS=ilo-redfish

provider-lab-ilo-inventory:
	$(MAKE) provider-smoke PROVIDER_MODE=local-lab-readwrite PROVIDER_SMOKE_PROVIDERS=ilo-redfish

provider-lab-ilo-readiness:
	$(MAKE) provider-smoke PROVIDER_MODE=local-lab-readwrite PROVIDER_SMOKE_PROVIDERS=ilo-redfish

provider-lab-firmware-inventory:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/firmware_compliance.py inventory

provider-lab-firmware-cisco-inventory:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/firmware_compliance.py cisco-inventory

provider-lab-cisco-firmware-cisco-inventory: provider-lab-firmware-cisco-inventory

provider-lab-firmware-compliance:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/firmware_compliance.py compliance

provider-lab-firmware-compliance-scope-cisco:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/firmware_compliance.py compliance --scope cisco

provider-lab-firmware-compliance-scope-hpe:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/firmware_compliance.py compliance --scope hpe

provider-lab-firmware-compliance-scope-full:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/firmware_compliance.py compliance --scope full

provider-lab-firmware-waiver-check:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/firmware_compliance.py waiver-check

provider-lab-hpe-storage-discovery:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/hpe_raid_workflow.py discovery

provider-lab-hpe-raid-discovery:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/hpe_raid_workflow.py discovery

provider-lab-hpe-raid-plan:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/hpe_raid_workflow.py plan --default-esxi-intent

provider-lab-hpe-raid-debug:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/hpe_raid_workflow.py debug

provider-lab-hpe-raid-pending:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/hpe_raid_workflow.py pending

provider-lab-server-reset-for-raid:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. HPE_RAID_ALLOW_RESET="$${HPE_RAID_ALLOW_RESET:-}" HPE_RAID_RESET_CONFIRM="$${HPE_RAID_RESET_CONFIRM:-}" LAB_ALLOW_POWER_ACTIONS="$${LAB_ALLOW_POWER_ACTIONS:-}" $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/hpe_raid_workflow.py reset

provider-lab-hpe-raid-validate-after-reset:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. HPE_RAID_VALIDATE_WAIT_SECONDS="$${HPE_RAID_VALIDATE_WAIT_SECONDS:-900}" HPE_RAID_VALIDATE_POLL_SECONDS="$${HPE_RAID_VALIDATE_POLL_SECONDS:-20}" $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/hpe_raid_workflow.py validate-after-reset

provider-lab-esxi-install-readiness:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/esxi_install_workflow.py

provider-lab-esxi-media-url:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/esxi_boot_workflow.py media-url

provider-lab-esxi-insert-virtual-media:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/esxi_boot_workflow.py insert-virtual-media

provider-lab-esxi-eject-virtual-media:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/esxi_boot_workflow.py eject-virtual-media

provider-lab-esxi-one-time-boot:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/esxi_boot_workflow.py one-time-boot

provider-lab-esxi-reset-installer-boot:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. ESXI_INSTALL_BOOT_WAIT_SECONDS="$${ESXI_INSTALL_BOOT_WAIT_SECONDS:-900}" ESXI_INSTALL_BOOT_POLL_SECONDS="$${ESXI_INSTALL_BOOT_POLL_SECONDS:-20}" $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/esxi_boot_workflow.py reset-installer-boot

provider-lab-esxi-detect-installer:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/esxi_boot_workflow.py detect-installer

provider-lab-cisco-console-ethernet-readiness:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/cisco_console_ethernet_readiness.py

provider-lab-cisco-console-recovery:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/cisco_real_lab_workflow.py

provider-lab-cisco-privilege-check:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/cisco_real_lab_workflow.py

provider-lab-cisco-vlan10-bootstrap-fix:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/cisco_real_lab_workflow.py

provider-lab-cisco-vlan10-bootstrap-apply:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/cisco_real_lab_workflow.py --apply

provider-lab-full-rebuild-summary:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/full_device_rebuild_summary.py

provider-lab-full-rebuild:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/full_device_rebuild_workflow.py

provider-lab-build-verification:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/build_verification.py

provider-lab-validation:
	cd backend && PROVIDER_MODE="$(PROVIDER_MODE)" PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/lab_validation.py

provider-lab-vcenter-netapp-readiness:
	cd backend && PROVIDER_MODE=local-readonly PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/vcenter_netapp_readiness.py readiness

provider-lab-vcenter-netapp-datastore-plan:
	cd backend && PROVIDER_MODE=local-readonly PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/vcenter_netapp_readiness.py datastore-plan

provider-lab-toolchain-check:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/toolchain_availability.py

provider-lab-hpe-raid-apply:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. HPE_RAID_ALLOW_DESTRUCTIVE="$${HPE_RAID_ALLOW_DESTRUCTIVE:-}" HPE_RAID_APPLY_CONFIRM="$${HPE_RAID_APPLY_CONFIRM:-}" $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/hpe_raid_workflow.py apply

provider-lab-serial-console-discovery:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/serial_console_discovery.py

provider-lab-netapp-console-autodiscovery:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_real_lab_workflow.py console-autodiscovery

provider-lab-netapp-console-discovery:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_real_lab_workflow.py console-autodiscovery

provider-lab-netapp-console-read-state:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_real_lab_workflow.py console-read-state

provider-lab-netapp-console-login-state:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_real_lab_workflow.py console-login-state

provider-lab-netapp-live-state:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_real_lab_workflow.py live-state

provider-lab-netapp-validate-setup:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_real_lab_workflow.py validate-setup

provider-lab-netapp-nfs-vcenter-readiness:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_real_lab_workflow.py nfs-vcenter-readiness

provider-lab-netapp-setup-baseline:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_setup_workflow.py baseline

provider-lab-netapp-setup-plan:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_setup_workflow.py plan

provider-lab-netapp-setup-preview:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_setup_workflow.py preview

provider-lab-netapp-setup-apply:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. NETAPP_SETUP_APPLY="$${NETAPP_SETUP_APPLY:-}" NETAPP_SETUP_CONFIRM="$${NETAPP_SETUP_CONFIRM:-}" NETAPP_SETUP_ALLOW_CLUSTER_CREATE="$${NETAPP_SETUP_ALLOW_CLUSTER_CREATE:-}" $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_setup_workflow.py apply

provider-lab-netapp-post-setup-validation:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_setup_workflow.py post-setup-validation

provider-lab-netapp-ontap-upgrade-inventory:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_ontap_upgrade_workflow.py inventory

provider-lab-netapp-ontap-upgrade-plan:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_ontap_upgrade_workflow.py plan

provider-lab-netapp-ontap-upgrade-validate:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_ontap_upgrade_workflow.py validate

provider-lab-netapp-ontap-upgrade-apply:
	cd backend && PROVIDER_MODE=local-lab-readwrite PYTHONPATH=. NETAPP_ONTAP_UPGRADE_APPLY="$${NETAPP_ONTAP_UPGRADE_APPLY:-}" NETAPP_ONTAP_UPGRADE_CONFIRM="$${NETAPP_ONTAP_UPGRADE_CONFIRM:-}" NETAPP_ONTAP_UPGRADE_VALIDATION_WAIVER="$${NETAPP_ONTAP_UPGRADE_VALIDATION_WAIVER:-}" NETAPP_ONTAP_UPGRADE_WAIVER_CONFIRM="$${NETAPP_ONTAP_UPGRADE_WAIVER_CONFIRM:-}" $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_ontap_upgrade_workflow.py apply

netapp-real-readiness:
	cd backend && PROVIDER_MODE="$(PROVIDER_MODE)" PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/netapp_real_run_readiness.py
