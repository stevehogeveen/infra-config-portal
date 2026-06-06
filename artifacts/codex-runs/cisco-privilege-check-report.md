# Cisco Console Privilege Check Report

## Summary

- Checked at: `2026-06-05T20:53:08.848579+00:00`
- Provider mode: `local-lab-readwrite`
- Env file: `.env.local.real-lab` loaded by `app.core.config`
- Console adapter: `[REDACTED]`
- Baud: `9600`
- Initial prompt state: `exec`
- Final prompt state: `exec`
- Privileged exec confirmed: `False`

## Env Var Usage Confirmed

- Login username: `settings.cisco_test_username` from `CISCO_TEST_USERNAME`, fallback `ANSIBLE_CISCO_USERNAME`, fallback `LAB_USERNAME`.
- Login password: `settings.cisco_test_password` from `CISCO_TEST_PASSWORD`, fallback `ANSIBLE_CISCO_PASSWORD`, fallback `LAB_PASSWORD`.
- Enable password setting: `settings.cisco_enable_password` from `CISCO_ENABLE_PASSWORD`, fallback `ANSIBLE_CISCO_ENABLE_PASSWORD`.
- Enable escalation candidates now tried directly from `CISCO_ENABLE_PASSWORD`, `ANSIBLE_CISCO_ENABLE_PASSWORD`, `settings.cisco_enable_password`, then login-password fallback.
- Login username configured: `True`
- Login password configured: `True`
- `CISCO_ENABLE_PASSWORD` configured: `True`
- `ANSIBLE_CISCO_ENABLE_PASSWORD` configured: `True`
- Login and selected enable password values same: `True`

## Workflow Fix

- `app/backend/scripts/cisco_real_lab_workflow.py` now uses the login password for console login exchange.
- Prompt classification now recognizes a trailing `#` or `>` prompt even when earlier output includes `Password:`.
- Enable escalation now tries both `CISCO_ENABLE_PASSWORD` and `ANSIBLE_CISCO_ENABLE_PASSWORD` when present.
- Redaction now includes both raw enable-password aliases.

## Console Steps

- wake prompt result: exec
- sent enable
- sent enable password candidate from CISCO_ENABLE_PASSWORD/ANSIBLE_CISCO_ENABLE_PASSWORD/login-password-fallback

## Blockers

- Did not reach privileged exec # prompt.

## Warnings

- none

## Read-Only Command Evidence

- Skipped because privileged exec was not confirmed.
## Safety

- No configuration commands were sent.
- No raw console transcript was saved.
- Secrets, usernames, console path, and IP addresses are redacted in this report.
