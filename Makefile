.PHONY: check-repo-root codex-audit codex-task codex-next codex-resume test dev lint provider-smoke provider-smoke-ilo-readonly provider-smoke-ilo-local-lab provider-inventory-ilo-local-lab provider-lab-live-status provider-lab-refresh-live-state provider-lab-build-verification-live provider-lab-ilo-reachability provider-lab-ilo-authentication provider-lab-ilo-inventory provider-lab-ilo-readiness provider-lab-firmware-inventory provider-lab-firmware-cisco-inventory provider-lab-cisco-firmware-cisco-inventory provider-lab-firmware-compliance provider-lab-firmware-compliance-scope-cisco provider-lab-firmware-compliance-scope-hpe provider-lab-firmware-compliance-scope-full provider-lab-firmware-waiver-check provider-lab-hpe-storage-discovery provider-lab-hpe-raid-discovery provider-lab-hpe-raid-plan provider-lab-hpe-raid-apply provider-lab-hpe-raid-validate-after-reset provider-lab-esxi-install-readiness provider-lab-esxi-media-url provider-lab-esxi-insert-virtual-media provider-lab-esxi-eject-virtual-media provider-lab-esxi-one-time-boot provider-lab-esxi-reset-installer-boot provider-lab-esxi-detect-installer provider-lab-esxi-recover-management provider-lab-esxi-post-recovery-validation provider-lab-esxi-netapp-datastore-preview provider-lab-esxi-netapp-datastore-apply provider-lab-esxi-netapp-datastore-validate provider-lab-esxi-vm-deploy-preview provider-lab-esxi-vm-deploy-apply provider-lab-esxi-vm-deploy-validate provider-lab-cisco-console-ethernet-readiness provider-lab-cisco-console-recovery provider-lab-cisco-privilege-check provider-lab-cisco-vlan10-bootstrap-fix provider-lab-cisco-vlan10-bootstrap-apply provider-lab-full-rebuild-summary provider-lab-full-rebuild provider-lab-build-verification provider-lab-validation provider-lab-vcenter-netapp-readiness provider-lab-vcenter-netapp-datastore-plan provider-lab-vcenter-install-readiness provider-lab-vcenter-install-plan provider-lab-toolchain-check provider-lab-serial-console-discovery provider-lab-netapp-console-autodiscovery provider-lab-netapp-console-discovery provider-lab-netapp-console-read-state provider-lab-netapp-console-login-state provider-lab-netapp-live-state provider-lab-netapp-validate-setup provider-lab-netapp-address-plan provider-lab-netapp-nfs-vcenter-readiness netapp-real-readiness app-start app-stop app-restart app-status app-check
.PHONY: provider-lab-netapp-setup-baseline provider-lab-netapp-setup-plan provider-lab-netapp-setup-preview provider-lab-netapp-setup-apply provider-lab-netapp-post-setup-validation provider-lab-netapp-address-preview provider-lab-netapp-address-apply provider-lab-netapp-address-validate provider-lab-netapp-ha-node-diagnose provider-lab-netapp-factory-reset-preview provider-lab-netapp-factory-reset-apply provider-lab-netapp-factory-reset-validate provider-lab-netapp-nfs-setup-preview provider-lab-netapp-nfs-setup-apply provider-lab-netapp-nfs-setup-validate provider-lab-netapp-ontap-upgrade-inventory provider-lab-netapp-ontap-upgrade-plan provider-lab-netapp-ontap-upgrade-validate provider-lab-netapp-ontap-upgrade-apply

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
TASK ?= .codex/tasks/001-backend-vm-request-lifecycle.md
CODEX_SANDBOX_MODE ?= workspace-write
CODEX_APPROVAL_POLICY ?= never
PROVIDER_MODE ?= local-lab-readwrite

export CODEX_SANDBOX_MODE
export CODEX_APPROVAL_POLICY

check-repo-root:
	$(REPO_ROOT)/scripts/check-repo-root.sh

codex-audit: check-repo-root
	$(REPO_ROOT)/scripts/codex-audit.sh

codex-task: check-repo-root
	$(REPO_ROOT)/scripts/codex-task.sh "$(TASK)"

codex-next: check-repo-root
	$(REPO_ROOT)/scripts/codex-next.sh

codex-resume: check-repo-root
	$(REPO_ROOT)/scripts/codex-resume-last.sh

test: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app backend-test PROVIDER_MODE=mock
	cd $(REPO_ROOT)/app/frontend && PROVIDER_MODE=mock npm run build

dev: check-repo-root
	$(REPO_ROOT)/runit restart

app-start: check-repo-root
	$(REPO_ROOT)/runit start

app-stop: check-repo-root
	$(REPO_ROOT)/runit stop

app-restart: check-repo-root
	$(REPO_ROOT)/runit restart

app-status app-check: check-repo-root
	$(REPO_ROOT)/runit status

lint: check-repo-root
	PROVIDER_MODE=mock bash -n $(REPO_ROOT)/runit
	PROVIDER_MODE=mock bash -n $(REPO_ROOT)/scripts/*.sh
	PROVIDER_MODE=mock python3 -c "import pathlib, tomllib; tomllib.loads(pathlib.Path('$(REPO_ROOT)/.codex/config.toml').read_text())"
	@if [ -x $(REPO_ROOT)/app/backend/.venv/bin/ruff ]; then \
		PROVIDER_MODE=mock $(REPO_ROOT)/app/backend/.venv/bin/ruff check $(REPO_ROOT)/app/backend; \
	else \
		echo "Backend lint: ruff is configured but not installed in app/backend/.venv; skipping."; \
	fi
	cd $(REPO_ROOT)/app/frontend && PROVIDER_MODE=mock npm run build

.PHONY: backend-smoke smoke
backend-smoke:
	$(REPO_ROOT)/scripts/check-repo-root.sh
	$(MAKE) -C $(REPO_ROOT)/app backend-smoke PROVIDER_MODE=mock

smoke: backend-smoke

provider-smoke: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-smoke PROVIDER_MODE="$(PROVIDER_MODE)"

provider-lab-live-status: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-live-status

provider-lab-refresh-live-state: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-refresh-live-state

provider-lab-build-verification-live: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-build-verification-live

provider-smoke-ilo-readonly: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-smoke PROVIDER_MODE=local-readonly PROVIDER_SMOKE_PROVIDERS=ilo-redfish

provider-smoke-ilo-local-lab: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-smoke PROVIDER_MODE=local-lab-readwrite PROVIDER_SMOKE_PROVIDERS=ilo-redfish

provider-inventory-ilo-local-lab: provider-smoke-ilo-local-lab

provider-lab-ilo-reachability: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-ilo-reachability

provider-lab-ilo-authentication: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-ilo-authentication

provider-lab-ilo-inventory: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-ilo-inventory

provider-lab-ilo-readiness: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-ilo-readiness

provider-lab-firmware-inventory: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-firmware-inventory

provider-lab-firmware-cisco-inventory: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-firmware-cisco-inventory

provider-lab-cisco-firmware-cisco-inventory: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-cisco-firmware-cisco-inventory

provider-lab-firmware-compliance: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-firmware-compliance

provider-lab-firmware-compliance-scope-cisco: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-firmware-compliance-scope-cisco

provider-lab-firmware-compliance-scope-hpe: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-firmware-compliance-scope-hpe

provider-lab-firmware-compliance-scope-full: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-firmware-compliance-scope-full

provider-lab-firmware-waiver-check: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-firmware-waiver-check

provider-lab-hpe-storage-discovery: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-hpe-storage-discovery

provider-lab-hpe-raid-discovery: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-hpe-raid-discovery

provider-lab-hpe-raid-plan: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-hpe-raid-plan

provider-lab-hpe-raid-apply: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-hpe-raid-apply

provider-lab-hpe-raid-validate-after-reset: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-hpe-raid-validate-after-reset

provider-lab-esxi-install-readiness: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-install-readiness

provider-lab-esxi-media-url: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-media-url

provider-lab-esxi-insert-virtual-media: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-insert-virtual-media

provider-lab-esxi-eject-virtual-media: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-eject-virtual-media

provider-lab-esxi-one-time-boot: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-one-time-boot

provider-lab-esxi-reset-installer-boot: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-reset-installer-boot

provider-lab-esxi-detect-installer: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-detect-installer

provider-lab-esxi-recover-management: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-recover-management

provider-lab-esxi-post-recovery-validation: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-post-recovery-validation

provider-lab-esxi-netapp-datastore-preview: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-netapp-datastore-preview

provider-lab-esxi-netapp-datastore-apply: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-netapp-datastore-apply

provider-lab-esxi-netapp-datastore-validate: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-netapp-datastore-validate

provider-lab-esxi-vm-deploy-preview: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-vm-deploy-preview

provider-lab-esxi-vm-deploy-apply: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-vm-deploy-apply

provider-lab-esxi-vm-deploy-validate: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-esxi-vm-deploy-validate

provider-lab-cisco-console-ethernet-readiness: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-cisco-console-ethernet-readiness

provider-lab-cisco-console-recovery: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-cisco-console-recovery

provider-lab-cisco-privilege-check: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-cisco-privilege-check

provider-lab-cisco-vlan10-bootstrap-fix: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-cisco-vlan10-bootstrap-fix

provider-lab-cisco-vlan10-bootstrap-apply: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-cisco-vlan10-bootstrap-apply

provider-lab-full-rebuild-summary: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-full-rebuild-summary

provider-lab-full-rebuild: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-full-rebuild

provider-lab-build-verification: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-build-verification

provider-lab-validation: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-validation

provider-lab-vcenter-netapp-readiness: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-vcenter-netapp-readiness

provider-lab-vcenter-netapp-datastore-plan: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-vcenter-netapp-datastore-plan

provider-lab-vcenter-install-readiness: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-vcenter-install-readiness

provider-lab-vcenter-install-plan: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-vcenter-install-plan

provider-lab-toolchain-check: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-toolchain-check

provider-lab-serial-console-discovery: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-serial-console-discovery

provider-lab-netapp-console-autodiscovery: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-console-autodiscovery

provider-lab-netapp-console-discovery: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-console-discovery

provider-lab-netapp-console-read-state: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-console-read-state

provider-lab-netapp-console-login-state: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-console-login-state

provider-lab-netapp-live-state: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-live-state

provider-lab-netapp-validate-setup: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-validate-setup

provider-lab-netapp-nfs-vcenter-readiness: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-nfs-vcenter-readiness

provider-lab-netapp-setup-baseline: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-setup-baseline

provider-lab-netapp-setup-plan: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-setup-plan

provider-lab-netapp-setup-preview: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-setup-preview

provider-lab-netapp-setup-apply: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-setup-apply

provider-lab-netapp-post-setup-validation: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-post-setup-validation

provider-lab-netapp-address-plan: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-address-plan

provider-lab-netapp-address-preview: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-address-preview

provider-lab-netapp-address-apply: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-address-apply

provider-lab-netapp-address-validate: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-address-validate

provider-lab-netapp-ha-node-diagnose: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-ha-node-diagnose

provider-lab-netapp-factory-reset-preview: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-factory-reset-preview

provider-lab-netapp-factory-reset-apply: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-factory-reset-apply

provider-lab-netapp-factory-reset-validate: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-factory-reset-validate

provider-lab-netapp-nfs-setup-preview: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-nfs-setup-preview

provider-lab-netapp-nfs-setup-apply: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-nfs-setup-apply

provider-lab-netapp-nfs-setup-validate: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-nfs-setup-validate

provider-lab-netapp-ontap-upgrade-inventory: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-ontap-upgrade-inventory

provider-lab-netapp-ontap-upgrade-plan: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-ontap-upgrade-plan

provider-lab-netapp-ontap-upgrade-validate: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-ontap-upgrade-validate

provider-lab-netapp-ontap-upgrade-apply: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-lab-netapp-ontap-upgrade-apply

netapp-real-readiness: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app netapp-real-readiness PROVIDER_MODE="$(PROVIDER_MODE)"
