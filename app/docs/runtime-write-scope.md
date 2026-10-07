# Runtime Write Scope

The Studio top-bar scope pill reports effective runtime permission. Check firmware
offers **Allow firmware writes only** and **Return to read-only**. Each opens a
server-issued preview. Firmware-only requires the exact phrase from that preview;
read-only revocation does not require a phrase. Applying either changes permission,
not hardware. Installing firmware requires a separate exact-target review and approval.

The backend provides GET `/api/v1/runtime/write-scope` and POST `/preview`, `/apply`.
Reviews expire after five minutes, are bound to the local actor, configuration and
scope generation, and can be consumed only once. Changed configuration or a competing
scope change requires a fresh review. Preview and apply are audited.

Environment flags are the bootstrap/default, not an immutable ceiling. Until an
operator applies a scope, existing configuration is unchanged. Firmware-only permits
`ilo.firmware-update` and excludes other hardware actions, including storage, power
and factory reset. Mode and isolated-lab acknowledgments remain independent gates.
The UI cannot grant storage, power or mixed scopes in this first implementation.
Read-only and saved app configuration remain available; no environment file is edited.

Scope transitions and dispatch admission serialize through the database. Active or
uncertain guarded operations, legacy storage/power attempts, running workflow records,
and dispatch admissions are shown by name and prevent granting firmware-only. A proven
historical rejection or verified completion is not treated as an active operation.
Returning to read-only does not cancel an already admitted/in-flight write, erase its
evidence, or release an unresolved device lock.

An admission left by process death is not cleared by elapsed time. Failed legacy
commands can retain admissions too. There is deliberately no blind-clear endpoint;
these cases need evidence-based reconciliation before a new firmware grant. The
existing firmware unsent-attempt reconciliation remains a separate, review-bound flow.

The API uses the application's existing trusted-local `X-Local-User` convention.
This is actor attribution, not new login/authentication or a production security
boundary. Do not expose this local control plane to untrusted callers.

Migration `0008_runtime_write_scope` adds scope, review and admission tables without
changing saved profiles, media, credentials, historical operations or existing grants.
Startup's existing additive schema initialization also creates these tables. Downgrade
does not silently discard permission/audit history. All workers must run the updated
backend before using the new scope control; older workers do not enforce this authority.

Offline coverage lives in `backend/tests/test_runtime_write_scope.py` and
`frontend/tests/write-scope.spec.ts`. PostgreSQL race coverage requires the explicit
disposable-fixture opt-in, never the application's database. This implementation does
not establish a drive return-to-service method or extend the first iLO bridge adapter
to later firmware versions.
