# Station002 — remaining-open diagnostic controls prepared

Date: 2026-11-10. Two Open-only controls were built from the exact full CONTROL source. Both matched pinned size/SHA: OLD_LOGO (1,461,381 bytes, SHA256 `c6ef59b8593f169db00a7f7b66f05f9578310a2c7ea2dcc7f993dbe335839e9b`) removes only the logo relink; PAGES_AND_MACRO_ONLY (1,461,431 bytes, SHA256 `119155c0b1f4ed1e8cbcb69162722955d7773e61df7a254bf1fe0895f28fd00f`) also restores three original widgets. All five pinned helpers matched manifest; source unchanged. These are diagnostics, not production files.

Native Open remains pending because running SKTool 7.1 processes have no main window in this session. Operator should open OLD_LOGO first only. On PASS, save a separate native copy and do not open the second probe. On FAIL, record the exact error and then open PAGES_AND_MACRO_ONLY. No Compile, Simulator, PLC or equipment action was performed.
