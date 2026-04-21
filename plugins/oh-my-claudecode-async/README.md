# oh-my-claudecode-async

Fork of [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) v4.13.1 with `"async": true` applied to the **SessionStart hook only**, to fix the Windows Claude Code v2.1.30+ keyboard freeze regression.

## Why this fork exists

Claude Code v2.1.30 introduced a regression on Windows where any `SessionStart` hook that errors or stalls causes the entire CLI to freeze — keystrokes aren't registered, `Ctrl+C` and `Escape` stop working. The Claude Code issues tracking this are still open:

- anthropics/claude-code #22906 — v2.1.30 Windows keyboard input broken
- anthropics/claude-code #22934 — v2.1.30 regression: CLI freezes when SessionStart hook errors (Windows)

OMC's upstream `hooks/hooks.json` runs all SessionStart hooks synchronously, so on Windows any hook that fails or hangs takes the whole terminal with it.

The well-known workaround — documented in https://for-habit.tistory.com/152 and in the Superpowers/GSD plugin issue trackers — is adding `"async": true` to the SessionStart hook. With async, the hook runs in the background and the CLI keeps going even if the hook errors.

## What changed vs upstream

Only `hooks/hooks.json` is modified, and only the `SessionStart` event's `*` matcher:

```
SessionStart (matcher: "*"):
  - session-start.mjs          → async: true
  - project-memory-session.mjs → async: true
  - wiki-session-start.mjs     → async: true
```

Everything else (UserPromptSubmit, PreToolUse, PostToolUse, Stop, SessionEnd, PermissionRequest, PreCompact, SubagentStart, SubagentStop, SessionStart `init`/`maintenance` matchers) is identical to upstream so OMC's enforcement and verification hooks retain their original synchronous semantics.

## Upstream

- Source: https://github.com/Yeachan-Heo/oh-my-claudecode
- License: MIT, Copyright (c) 2025 Yeachan Heo — see `LICENSE.UPSTREAM`
- This fork is also MIT-licensed per the original terms.

## Install

```
/plugin marketplace update my-marketplace
/plugin install oh-my-claudecode-async@my-marketplace
/plugin remove oh-my-claudecode   # if previously installed — hooks would run twice
```

## Tests/benchmarks excluded

`dist/__tests__/` was dropped from the fork to reduce size. The runtime-required subsets of `dist/` and all `scripts/` are kept.
