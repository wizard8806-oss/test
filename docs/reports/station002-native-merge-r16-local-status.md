# Station002 native merge r16 — local candidates prepared

Date: 2026-11-11. Full r16 candidate built from the exact native-saved code-pages base and full r15f alarm donor. Full candidate: 1,479,661 bytes, SHA256 `84797b73846e5266894812e4bcd7bd7aa8a977baa962934b8eea479aa58420e6`. An alarms-only fallback was also prepared: 1,479,689 bytes, SHA256 `9e45309a2595462a705e2654f4c82a98b85425fef9c57c6559b8ec7a07ba886b`. Six pinned helpers matched manifest; Python stdlib build/check passed for both. PLC unchanged.

Native Open/SaveAs/Compile/Simulator remain pending: SKTool 7.1 processes have no main window in this session. Operator should open the full candidate first; only if it fails should the alarms-only fallback be opened. No hardware actions occurred.
