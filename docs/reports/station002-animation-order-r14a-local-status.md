# Animation-order r14a — local source-checked HMI

10.11.2026. A separate SKM candidate was generated from the exact user r13. The prepared builder and checker passed: only the two Variable settings tables changed, moving BootAck W R2553 after all read-only inputs; source and all other UI/C bytes are preserved. Candidate: 1,273,731 bytes, SHA256 `b56648e47a41cdd4eef981060da7a20a0a12cb062f6af9a4c1cf9faf69523323`.

Native SKTool Compile and generated aliases are still pending. The current session exposes no project window; no live retest or equipment action occurred. Operator next step: SKTool File → Open this candidate → Compile. Do not treat the ABI hypothesis as accepted until aliases and P3-only live result are confirmed. PLC unchanged.
