# oh-my-claudecode-async

Fork of [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) v4.13.1 with `"async": true` added to UI-blocking hooks to fix terminal keyboard timing freeze.

## Why this fork exists

Upstream `oh-my-claudecode` ships a large number of hooks on events that fire during interactive input (`UserPromptSubmit`, `SessionStart`, `PreToolUse`, `PostToolUse`, `Stop`, `SessionEnd`). Because they run synchronously, the terminal stalls — keystrokes arrive late or are dropped.

This fork flips `"async": true` on those hooks so they run in the background and no longer block the input loop.

## What changed vs upstream

Only `hooks/hooks.json` is modified. Scripts, agents, skills, and `dist/` are copied verbatim from upstream.

| Hook event | async applied | note |
|---|---|---|
| UserPromptSubmit | all (2/2) | main cause of keystroke lag |
| SessionStart (`*`) | all (3/3) | startup freeze |
| SessionStart (`init`, `maintenance`) | — | intentionally sync: setup output is meant to block |
| PreToolUse | all (1/1) | |
| PostToolUse | all (3/3) | |
| PostToolUseFailure | all (1/1) | |
| SubagentStart | all (1/1) | |
| SubagentStop | 1/2 | `verify-deliverables` left sync |
| Stop | all (3/3) | |
| SessionEnd | all (2/2) | |
| PermissionRequest | — | must block to be effective |
| PreCompact | — | must block to be effective |

## Upstream

- Source: https://github.com/Yeachan-Heo/oh-my-claudecode
- License: MIT, Copyright (c) 2025 Yeachan Heo — see `LICENSE.UPSTREAM`
- This fork is also MIT-licensed per the original terms.

## Tests/benchmarks excluded

`dist/__tests__/` was dropped to reduce size. The runtime-required subsets of `dist/` and all `scripts/` are kept.
