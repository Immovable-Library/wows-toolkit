# Handoff: WOWS replay attribution engine

Snapshot date: 2026-09-05. Resume point for a fresh session. Read this, then the
design spec the skill points at, before acting.

## What this is

A replay-mining pipeline turning WOWS rep files into professional positioning /
aiming advice by attributing the why, not the surface result. Core rule: never
assert a single cause from a final damage number; run a multi-hypothesis
attribution engine and only report evidence-backed conclusions.

Surface symptom -> root cause is non-unique. Two real examples from one night:
- Tokyo Express (Georgia): low damage because teammates the player spotted ate
  the targets (team interaction / crowd-detect).
- Hermes (Georgia): low damage because turret dispersion RNG.

## The one mechanic correction that must not be lost

WOWS spotting credit: a target's spotting damage is credited to the SINGLE
own-team unit that uniquely detects it. If two or more own-team units sit inside
the target's detection ring at the same moment, that target contributes ZERO
spotting damage to every one of them.

Consequence: `scouting_damage` in the 0x22 battle report is the server-settled
NET after this rule. It is a lower bound on "I uniquely lit some damage", NOT a
count of targets lit, and NOT proof of who ate a given kill. A high net proves
solo-spot credit; a low net does not prove "you did not light" (you may have been
zeroed by crowd-detect). Do not re-derive per-target causation from the net.

## Implemented so far

### Skill layer (Python, outside the git repo)

Path: `C:/Users/asdfg/.codex/skills/wows-replay-parser`

- `scripts/spot_credit.py`: Tier 1 per-game "spotting-vs-conversion" profile.
  Reads `scouting_damage` / `damage` / `frags` + team composition only. Conservative,
  graded verdicts; does NOT claim per-target causation. Run:
  `python scripts/spot_credit.py --db replays.db --player uomouse --date 20260904`
- `SKILL.md`: encodes the spotting-rule invariant, Tier 1 usage, and a pointer to
  the event-level spec.
- `specs/2026-09-05-event-credit-attribution-engine.md`: design blueprint for the
  event-level multi-hypothesis engine (H1-H6, hit-rate expectation model,
  event-stream schema, "not-self-deceiving" rules, M1-M4 milestones). Read before M2.
- `reports/uomouse_spot.md`: Tier 1 output for 2026-09-04 (9 games). Honest verdict
  for Tokyo Express = "suspected crowd-detect (needs event-level)".
- `replays.db`: parsed 15.7.0.0 replays; today's 9 games are in it (source prefix
  `20260904`). Player account is `uomouse` (566060956).

### Repo layer (Rust, committed at bd2b9678)

- `AGENTS.md`: migrated version control to git; jj removed (jj is NOT installed here).
- `crates/replayshark/src/events_cmd.rs` + `crates/replayshark/src/main.rs`: new
  `replayshark events` subcommand. Drives a replay through
  `wows_battle_world::process::battle_report_for` with
  `ProcessOptions { shot_tracking: ShotTracking::Tracked, record_hit_history: true,
  record_salvo_history: true }`, writes JSONL: a `meta` roster (entity_id -> name,
  is_self), one `salvo` row per salvo, one `hit` row per resolved hit. Verified on
  the Tokyo Georgia replay: 1756 salvos, 1639 hits; self ship (Georgia) entity id
  705040. A hit row carries `hit.hit_type.collision` + `hit.hit_type.shell_hit`,
  `hit.position` (impact), `victim_pose` (pos + yaw), `owner_id`, `victim_entity_id`.
- Command: `cargo run -p replayshark -- -g D:/World_of_Warships events <replay> --out <jsonl>`.
  Note `-g` is a top-level arg and must come BEFORE `events`.
- Build check: `cargo check -p replayshark` passes.

## Environment facts

- Repo: `D:\codexProject\wows-toolkit`. Plain git repo (.git present, no .jj).
  Working tree clean at commit `bd2b9678`.
- Game dir for the CLI: `D:/World_of_Warships`. Replays:
  `D:\World_of_Warships\replays\15.7.0.0\`. Today's 9 files: source prefix `20260904_`.
- Skills live in `C:/Users/asdfg/.codex/skills/`.
- `grill-me` skill installed (from `feiskyer/codex-settings`). Triggers on
  `$grill-me` (or "追问 / 挑战方案 / 拷打设计"); asks ONE question at a time until
  consensus; maintains `CONTEXT.md` (glossary) + `docs/adr/` (ADR log).

## Key repo type/API facts for M2

- `wows_battle_world::report::BattleReport` exposes: `salvos() -> &[SalvoEvent]`,
  `hit_history() -> &[ResolvedShotHit]`, `presence()` (observation windows),
  `players()`, `self_player()`. Salvo/hit history require the ingest flags above.
- Decoder event payloads (wows-replays `DecodedPacketPayload`): `ArtilleryShots`,
  `ShotKills` (hit types), `TerminalBallisticsInfo`, `Position`, `SetAmmoForWeapon`,
  `DamageReceived` / `DamageStat`, `ShipDestroyed`, `DetectedByHydrophone`.
- Newtype inner-value accessors: `EntityId::raw()->u32`, `GameParamId::raw()->u64`,
  `ShotId::raw()->u32`, `GameClock.0 -> f32`. Player name is
  `player.initial_state().username()`, NOT `player.name()`.
- `wows-replay-insights::fire_chance` already consumes salvos + hit_history; reuse
  it as a foundation for aiming analysis instead of re-deriving it.

## Next milestones

- M2: hit-rate expectation model. Use wowsunpack ballistics / dispersion / sigma to
  compute expected hit probability at firing range, then compare actual vs expected
  to separate H2 (dispersion RNG) from H3 (aiming error / wrong ammo / bad angle).
  Discriminator: RNG => hit rate below expected but hit types / impact angle normal;
  aiming => high bounce / overmatch / superstructure hits.
- M3: multi-hypothesis engine H1-H6 in the Python skill, consuming the `events` JSONL.
- M4: detection / spotted-event parsing for per-target unique-spotter attribution
  (the only H1 gap; requires new packet work in wows-replays).

## Recommended next action

Before M2 code, grill the design: run `$grill-me` against the event-level spec
(H1-H6 thresholds + "not-self-deceiving" rules) and lock M2's direction, so we do
not build the hit-rate model then rework it. Then implement M2.
