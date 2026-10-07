# Blocker guidance

Backend responses retain `blockers: string[]` and add `blocker_details` with
`code`, original `text`, `fix_kind`, `fix`, and `action`. This is display guidance,
not authorization, hardware evidence, or a change to admission rules.

Surfaces: capability `ilo_update_health`, guarded firmware/drive-return preview
and status, write-scope preview, and whole-SPP plan projection. The whole-SPP
projection is a backend contract, not a production installation endpoint.

`fix_kind` is `app`, `physical`, `wait`, or `vendor`. Actions are allowlisted:
`read_again`, `prepare_again`, `narrow_scope_firmware`, `open_connection`,
`select_package`, `check_status`, or `none`. The UI must retain plain blocker
strings when details are absent and must only offer actions it implements.
Reading or preparing requires an explicit user action; rendering guidance never
starts a hardware call or clears an unresolved submission.

Known messages map to stable codes in `services/blocker_guidance.py`. Unknown
messages remain visible with `review_required` and neutral guidance. New vendor
messages need an explicit mapping and test, not a guessed repair.

iLO confirmation is `INSTALL ILO <reviewed version>`. The review still binds
the exact target, package, and operation; reset and continuous-power warnings
remain in the review message. Shorter typing does not weaken server validation.

Offline coverage includes mapping/fallback, malformed Updateable values,
short confirmation and warning placement, response surfaces, unchanged blockers,
and rejection of apply attempts that bypass a blocked review. Run targeted
pytest suites with mock providers, an isolated database, and networking disabled.
