# vCenter Install Apply Report

- Checked at: `2026-06-14T18:13:10.404551+00:00`
- Status: `completed`
- Provider mode: `local-lab-readwrite`
- Apply enabled: `True`
- vcsa-deploy attempted: `True`
- vcsa-deploy result: `completed`
- vcsa-deploy return code: `0`

## Current State
- VCSA ISO: `artifacts/Media/VMware-VCSA-all-8.0.3-24853646.iso`
- vcsa-deploy: `/tmp/vcsa-iso/vcsa-cli-installer/lin64/vcsa-deploy`
- ESXi management: `192.168.1.203`
- NetApp datastore: `netapp_nfs_ds01`

## Target State
- vCenter: `192.168.1.206`
- Deployment target: `192.168.1.203`
- Datastore: `netapp_nfs_ds01`
- Network / portgroup: `VM Network`

## Apply Gates
- `PROVIDER_MODE=local-lab-readwrite`
- `VCENTER_INSTALL_APPLY=true`
- `VCENTER_INSTALL_CONFIRM="DEPLOY VCENTER"`
- `VCENTER_INSTALL_ALLOW_DEPLOY=true`

## Gate State
- provider_mode: `local-lab-readwrite`
- local_lab_readwrite: `True`
- readiness_ready: `True`
- preview_ready: `True`
- install_apply: `True`
- install_confirm: `True`
- install_allow_deploy: `True`

## Command
- `/tmp/vcsa-iso/vcsa-cli-installer/lin64/vcsa-deploy install --accept-eula --acknowledge-ceip --no-ssl-certificate-verification <generated-vcsa-spec.json>`

## vcsa-deploy stdout summary
```text
    Task: Install
required RPMs for the appliance.(SUCCEEDED 100/100)       - Task has completed
successfully.         Task: Run firstboot scripts.(RUNNING 92/100)    - Starting
VMware Content Library Service...
VCSA Deployment is still running
==========VCSA Deployment Progress Report==========         Task: Install
required RPMs for the appliance.(SUCCEEDED 100/100)       - Task has completed
successfully.         Task: Run firstboot scripts.(RUNNING 92/100)    - Starting
VMware Content Library Service...
VCSA Deployment is still running
==========VCSA Deployment Progress Report==========         Task: Install
required RPMs for the appliance.(SUCCEEDED 100/100)       - Task has completed
successfully.         Task: Run firstboot scripts.(RUNNING 98/100)    - Starting
VMware Performance Charts...
VCSA Deployment is still running
==========VCSA Deployment Progress Report==========         Task: Install
required RPMs for the appliance.(SUCCEEDED 100/100)       - Task has completed
successfully.         Task: Run firstboot scripts.(SUCCEEDED 100/100) - Task has
completed successfully.
VCSA Deployment is still running
==========VCSA Deployment Progress Report==========         Task: Install
required RPMs for the appliance.(SUCCEEDED 100/100)       - Task has completed
successfully.         Task: Run firstboot scripts.(SUCCEEDED 100/100) - Task has
completed successfully.
VCSA Deployment is still running
==========VCSA Deployment Progress Report==========         Task: Install
required RPMs for the appliance.(SUCCEEDED 100/100)       - Task has completed
successfully.         Task: Run firstboot scripts.(SUCCEEDED 100/100) - Task has
completed successfully.
VCSA Deployment is still running
==========VCSA Deployment Progress Report==========         Task: Install
required RPMs for the appliance.(SUCCEEDED 100/100)       - Task has completed
successfully.         Task: Run firstboot scripts.(SUCCEEDED 100/100) - Task has
completed successfully.
VCSA Deployment is still running
==========VCSA Deployment Progress Report==========         Task: Install
required RPMs for the appliance.(SUCCEEDED 100/100)       - Task has completed
successfully.         Task: Run firstboot scripts.(SUCCEEDED 100/100) - Task has
completed successfully.
VCSA Deployment is still running
==========VCSA Deployment Progress Report==========         Task: Install
required RPMs for the appliance.(SUCCEEDED 100/100)       - Task has completed
successfully.         Task: Run firstboot scripts.(SUCCEEDED 100/100) - Task has
completed successfully.
VCSA Deployment is still running
==========VCSA Deployment Progress Report==========         Task: Install
required RPMs for the appliance.(SUCCEEDED 100/100)       - Task has completed
successfully.         Task: Run firstboot scripts.(SUCCEEDED 100/100) - Task has
completed successfully.
Successfully completed VCSA deployment.  VCSA Deployment Start Time:
2026-06-14T18:21:49.954Z VCSA Deployment End Time: 2026-06-14T18:39:34.197Z
 [SUCCEEDED] Successfully executed Task 'MonitorDeploymentTask: Monitoring
Deployment' in TaskFlow 'vcsa-deploy-olib8d4x' at 18:43:00
Monitoring VCSA Deploy task completed
== [START] Start executing Task: Join active domain if necessary at 18:43:00 ==
Domain join task not applicable, skipping task
 [SUCCEEDED] Successfully executed Task 'Running deployment: Domain Join' in
TaskFlow 'vcsa-deploy-olib8d4x' at 18:43:00
 [START] Start executing Task: Provide the login information about new
appliance. at 18:43:00
    Appliance Name: lab-vcenter
    System Name: localhost
    System IP: 192.168.1.206
    Log in as: Administrator@vsphere.local
 [SUCCEEDED] Successfully executed Task 'ApplianceLoginSummaryTask: Provide
appliance login information.' in TaskFlow 'vcsa-deploy-olib8d4x' at 18:43:00
=================================== 18:43:00 ===================================
Result and Log File Information...
WorkFlow log directory:
/tmp/vcsaCliInstaller-2026-06-14-18-13-mz6rzy02/workflow_1781460798181

```

## vcsa-deploy stderr summary
```text
THUMBPRINT DEPRECATION WARNING: The thumbprint field is going to be deprecated
in a future release. Plan to switch to use certificates instead.  This change is
a part of the global initiative to use full certificates instead of thumbprints
for establishing a secure connection.

```

## Blockers
- None

## Warnings
- vcsa-deploy is the only deployment executor for this workflow; secrets are passed through a temporary local spec and not written to artifacts.

## Safety
- Secrets are redacted in this report.
- The unredacted VCSA spec is written only to a temporary 0600 file for vcsa-deploy and is removed after the command exits.
