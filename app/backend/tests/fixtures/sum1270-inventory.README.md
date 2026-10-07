# SUM Repository Report Provenance

Generated 2026-09-29 using the bundled SUM 12.7.0 from the locally supplied
P95170_001 Gen10 SPP 2026.05 ISO. A temporary baseline held only the bundled
firmware-ilo5-3.19-1.1.x86_64.rpm, deliberately without signature sidecars.

Invocation used the vendor bash launcher with `--s --inventory_report --dryrun`,
an explicit temporary `--use_location`, and a temporary `--reportdir` inside a
disposable Docker container with `--network none`. No target or credentials were
supplied. SUM generated repository XML, returned code 3 and shut down its engine.

The fixture replaces the temporary container path and report date with fixed
values; the component fields and report structure are the observed output.
This demonstrates a signature warning, not a valid authenticated baseline.
It is not a firmware/target/dependency report or evidence of an installed version.
The inventory's `reboot_required=No` must not erase the separately established
iLO reset requirement in an execution plan.
