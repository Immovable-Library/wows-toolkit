# AGENTS.md

Guidance for agents working in the wows-toolkit repository. These rules override default behavior and apply to every crate unless a crate-local AGENTS.md says otherwise.

## Repository

Cargo workspace, edition 2024, rust 1.97. Crates under `crates/`:

- `wows-toolkit` main desktop app (egui + eframe + glow)
- `wowsunpack` game data unpacking, models, game params
- `wows-replays` replay file parsing and packet decode
- `minimap-renderer` minimap draw command generation
- `replayshark` CLI replay analysis
- `wows-data-mgr` game data management
- `wt-collab-protocol`, `wt-collab-egui` shared collab protocol and UI
- `wt-web` WASM client
- `wt-translations` translations
- `wows-replay-insights` derived replay insights
- `wgcheck` WGCheck .gch report parsing

## Version control

- The repo is a git project. Use `git` as the authoritative interface.
- Never append `Co-Authored-By` or any AI attribution to commit messages.

## Prioritization

- Fix confirmed bugs before starting new feature work. A new milestone stays
  blocked until the bug backlog from the previous milestone is cleared, or the
  user explicitly defers it.

## Types and data modeling

- Prefer newtypes over raw primitives for domain values, even when the value arrives as a primitive. Wrap identifiers and any quantities that could be confused with each other (angles together with their unit, bitflags, durations, indices, weapon groups) in distinct newtypes so the type system rejects mixing them. Reuse existing newtypes (`wowsunpack` `TeamId`, `GameParamId`, `EntityId`, etc.) instead of storing their raw inner value.
- Model "absent" or "unlimited" with `Option` or an enum, never sentinel values like `-1`, `0`, or empty string.
- Bubble `Option` and `Result` up as far as practical. Resolve them at the boundary where there is enough context to handle them correctly.

## Defaults and missing data

- Scrutinize every `.unwrap_or`, `.unwrap_or_default`, `.unwrap_or_else`, and `Default` applied to parsed or possibly-missing data.
- Do not paper over malformed or absent input with a default unless that default is genuinely correct. When it is, document why at the call site. Otherwise propagate the error or the option.

## Errors

- Use strong `thiserror` enums with structured fields.
- Never match on an error's `Display` or `Debug` string to recover data. If meaningful data is only reachable by parsing a formatted string, the error type is wrong; add a field.
- Use `rootcause` to attach context as errors cross boundaries.

## Comments

- Comments explain non-obvious intent only. Keep them terse and DRY.
- No salesmanship or filler wording.
- No historical framing ("now X", "was Y, now Z"). Describe current behavior.
- No numbered step-recaps of the implementation. Short WHY lines only.

## Text and formatting

- ASCII only in code, comments, UI strings, and commit messages. No emdash, endash, ellipsis, arrows, or other unicode symbols.
- No separator or banner comments (`// ---`, `// ===`, long dashed/equals rules, section dividers). Structure code with modules, functions, and blank lines, not comment dividers.

## Compatibility

- Changes must work across old (0.6.x) and current game versions. Packet layout differences are version-gated; see `MODERN_PACKET_LAYOUT_MIN_VERSION` in `wows-replays` `packet2.rs`.

## Approved replay data pool

Replay and cache data for operations is governed by the approval pool in `C:/Users/asdfg/.codex/skills/wows-replay-cache/approval_pool.json`. New data entering the cache must pass the approval filter before any row is written; rejected arenas are skipped and must not be re-added. Analysis, spawn-map, and statistics pipelines must consume only approved arenas.

Version gates per map (build is the client build stored in `arena.build`):

- Killer Whale (`NavalBase`) and Narai (`Advance`): all versions accepted.
- Newport (`Naval_Defense`), Raptor Rescue (`Labyrinth`), Ultimate Frontier (`Atoll`), Hermes (`LePVE`), Aegis (`Ridge`), Cherry Blossom (`USS_CL`): build >= 11189791 (14.11.0).
- Arctic Convoy (`WW2_OPERATION_1`), Tokyo Express (`WW2_OPERATION_2`), Pacific Offensive (`WW2_OPERATION_3`): build >= 12116141 (15.2.0).
- Flagships scenario variants are never accepted.

Legacy scenario names map to their current families: `Attack_On_Base_Normal` -> `NavalBase`, `Defense` -> `Naval_Defense`, `OP_01_01_ATTACK_ON_CONVOY_1` -> `Ridge`, `OP_01_03_NORMAL` -> `Labyrinth`, `OP_02_02_NORMAL` -> `Atoll`.

Filtering logic lives in `C:/Users/asdfg/.codex/skills/wows-replay-cache/scripts/approval_lib.py` (`classify` / `approved_arenas`); `cleanup_approved.py --dry-run` / `--execute` applies the filter to the existing cache and replay folders. Update the JSON config, not this section, when the pool rules change.

## Review

- At the end of each milestone, run an adversarial code review with a fresh subagent before committing. For ECS work the reviewer must be framed as a bevy_ecs/ECS expert and instructed to challenge the design itself (component vs resource boundaries, query patterns, archetype/iteration-order determinism, entity lifecycle), not just surface code quality.

## Active major effort

Reimplementing `BattleController` (in `wows-replays`) on `bevy_ecs` as a new `wows-battle-world` crate. Design spec: `docs/superpowers/specs/2026-06-04-battle-world-ecs-design.md`.
