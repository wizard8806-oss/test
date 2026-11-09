# Station002 native fault r14 — offline status

10.11.2026. The pinned PLC builder reproduced the expected separate PDW candidate: 201327 bytes, SHA256 `718a004b098f32493829db4cd42475eb842669a157511c90066883e5d9ea84cf`. Local validator passed 258 component scenarios; this is not WinProLadder F8 or native PLC simulation.

The exact user r13 HMI was preserved. A separate HMI workcopy exists but is still byte-identical to its source and is **not** a completed r14. Fault page/journal changes, native aliases, HMI Compile/Offline Simulator, and logo load/saver settings remain unverified. WinProLadder has no running process and SKTool has no accessible top-level window in the current session. The referenced logo JPEG is missing at the path embedded in the project. No equipment actions were performed.

Full native files and detailed reports remain local.
