# Station 11 trend quality — short acceptance summary

Base: `cbd5901cff789237f109582e8a7b214ad3df4a74`. Windows local CLI,
2026-11-05, Simple-Scada 2.6.15.0.

Continued the already prepared trend-timer copy without reimport or rebuild.
Static review of saved Script_49 and 19 isolated synthetic contract cases passed:
map/version and heartbeat-age gates, per-tag quality predicates, source mask,
raw bounds, one-time scaling, separate internal targets, valid/invalid/recovery,
stale/fresh, confirmed zero, and independent rows. No source/command assignment
was found. Script_49 is configured as a 1-second timer; this was not a runtime
cadence measurement.

Client displayed the existing three-row group, shared 0–16 bar pressure scale,
separate 0–50 Hz scale, cursor values, and successful 1/6/24 hour range changes.
The diagnostic page showed map version 32 and a progressing PLC heartbeat.
Existing archive traces were visible. PV archive mode was “on change” with zero
deadband and the project-default interval.

This is partial acceptance. Per-tag live GOOD quality was not captured directly,
and invalid/stale transitions were not run through a native archive. The test
does not establish how the native viewer stores or draws gaps. The 0.0 Hz trend
value is not independent physical VFD measurement. No Apply, PLC/VFD command,
OPC write, database change, or SCADA10 modification was made.

The reusable synthetic/static checker is
[`validate_station11_trend_quality_01.py`](../../tools/validate_station11_trend_quality_01.py).
