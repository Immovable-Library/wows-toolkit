# WoWS Operations Sample Collector: Standalone Process Design

> Status: design only, not implemented
> Last updated: 2026-08-24

## 1. Purpose

Collect Operations-mode samples that can be analyzed later without rebuilding
or running the full `wows-toolkit` desktop app. The first use case is ranking
teammates at match start: use each player's historical Operations performance,
already shown in the Current Match player tracker, to tell apart teammates who
will carry from teammates who will need a carry.

This document records the decision to extract collection into an independent
process and defines the boundary between that process and the existing app.
Implementation is deferred.

## 2. Core decision: pre-battle snapshot only

The sample is a **pre-battle snapshot**, not a post-battle record.

Concretely, the snapshot is the historical server-side data displayed in the
Current Match player tracker:

- account-wide `statistics.oper_solo`
- current-ship `statistics.oper_solo` for the ship the player is about to use

This is a pre-analysis problem: the goal is to predict the current battle from
historical performance, so the snapshot must not contain the current battle's
outcome or any post-battle derived result.

The existing `persist_operations_samples` path already writes exactly this
pre-battle data: it fetches the WG API after the roster is available, and the
WG API does not include the not-yet-finished match. The standalone collector
must preserve that same timing and semantics.

### 2.1 What is out of scope for the first collector

- Do not append post-battle replay-derived performance to the pre-battle row.
- Do not compute or store a rating yet. Store raw server data plus the small
  set of match identifiers.
- Do not join a future battle-result label into the pre-battle snapshot. A
  later label pass may add it, but it must be a separate phase and must not
  change the definition of the pre-battle snapshot.

## 3. Current coupling

The current sample path lives inside the desktop app:

- `crates/wows-toolkit/src/data/wargaming.rs`
  - WG account-list, account-info, and ship-stats client.
  - `WowsOperationsStats` and the derived `win_rate`,
    `five_star_rate`, and `avg_xp` methods.
  - `Region::wargaming_api_host` mapping.
- `crates/wows-toolkit/src/task/live_match_stats.rs`
  - `resolve_and_fetch` reads a live or completed replay roster.
  - `fetch_operations_stats_for` fetches account and current-ship stats.
  - `persist_operations_samples` appends one JSON line per human to
    `ops_samples.jsonl`.
- `crates/wows-toolkit/src/data/session_stats.rs`
  - `persist_operations_result` appends every human's per-match result to
    `ops_results.jsonl` once a finished Operations replay is read.
- `crates/wows-toolkit/src/ui/player_tracker/current_match.rs`
  - renders the same Operations stats in Current Match.
- `crates/wows-toolkit/src/data/match_stats.rs`
  - `Region`, whose `wargaming_api_host` is reused by the WG client.

The sample struct is currently private to `live_match_stats.rs`:

```rust
struct OperationsSample {
    ts: i64,
    arena_id: i64,
    account_id: i64,
    ship_id: u64,
    account: WowsOperationsStats,
    ship: Option<WowsOperationsStats>,
}
```

## 4. Target architecture

### 4.1 Extract the WG API layer

Move the WG API types and client out of the GUI crate into a small workspace
crate such as `wows-wargaming`:

- `WargamingAccount`
- `WowsOperationsStats`
- `WargamingApiError`
- `WargamingClient`
- the host mapping

The extracted crate must depend only on:

- `serde` / `serde_json`
- `reqwest` (or the existing hyper stack) with blocking or async behind a
  feature, matching the current callers
- `thiserror`
- `rootcause` where needed
- `wows_replays` only for `AccountId` and `GameParamId` newtypes, or replace
  those with the extracted crate's own newtypes if avoiding the dependency is
  worthwhile

It must not depend on `egui`, `eframe`, `PlayerTracker`, or any `wows-toolkit`
UI module.

### 4.2 Move `Region` out of the stats service module

`Region` is a small domain type currently attached to `match_stats.rs`. The
standalone collector needs it without pulling in the shipbuilds client.
Options:

- move `Region` into `wows-core` or the extracted `wows-wargaming` crate;
- keep `Region` where it is and add a separate collector-only enum, accepting
  the small duplication.

Prefer moving it once the WG crate exists, then have `match_stats.rs` import
it.

### 4.3 Add a standalone binary crate

Add a workspace member, for example `wows-ops-collector`, as a small CLI:

```text
wows-ops-collector
    --region eu|na|asia
    --replay <path>            # complete replay, or
    --arena-info <path>        # tempArenaInfo.json
    --stream <path>            # temp.wowsreplay
    --build <number>
    --output <path>            # JSONL file
```

The binary:

1. reads a roster with the same `scan_arena_state` path used by the app;
2. filters to humans and maps `realm` to a region;
3. fetches account-wide `oper_solo` for the roster in one batch;
4. fetches current-ship `oper_solo` per human, best effort;
5. writes one JSONL row per human with the pre-battle snapshot;
6. never blocks the UI because there is no UI; it is a foreground or
   one-shot CLI process.

### 4.4 Optional watch mode

For unattended collection, the binary can optionally watch the live replay
directory and run whenever `tempArenaInfo.json` plus `temp.wowsreplay` describe
a new match. Keep it best effort and idempotent:

- deduplicate by `arena_id` and `ts`;
- retry short reads with the same tolerance as `LiveRosterSource::InProgress`;
- append-only output so a restart does not truncate existing samples.

Watch mode is a later enhancement, not part of the first implementation.

## 5. Sample schema

Preserve the current JSONL shape as version 1, and make it explicit:

```json
{
  "schema_version": 1,
  "captured_at": 1787511681,
  "match_started_at": 1787511681,
  "region": "eu",
  "arena_id": 123456,
  "account_id": 502514064,
  "ship_id": 3760142032,
  "account": {
    "xp": 258001,
    "battles": 111,
    "survived_wins": 66,
    "survived_battles": 71,
    "wins": 99,
    "losses": 12,
    "wins_by_tasks": { "2": 2, "3": 4, "4": 21, "5": 72 }
  },
  "ship": {
    "xp": 17576,
    "battles": 8,
    "survived_wins": 3,
    "survived_battles": 4,
    "wins": 6,
    "losses": 2,
    "wins_by_tasks": { "4": 1, "5": 5 }
  }
}
```

`account` and `ship` are raw `oper_solo` blocks. Do not flatten derived
metrics into the stored sample; derive them later so the raw data remains
re-analyzable.

If the existing app and the standalone collector both write to the same file,
they must agree on this schema. Keeping `schema_version` makes that contract
checkable.

## 6. Distribution forms

Two forms are possible; standalone CLI is the recommended first delivery.

### 6.1 Standalone executable

- small, easy to share;
- no GUI or game-data browser required beyond what roster scanning needs;
- can be driven manually or by a wrapper script;
- suitable for collecting data from other players.

This is the lowest-risk extraction because it reuses `wows-replays` and
`wowsunpack` but does not carry `eframe` or `egui`.

### 6.2 Mod or in-process hook

- runs inside the existing app or as a separate process reading the same
  storage directory;
- more convenient for the current user, but harder to distribute and
  maintain;
- not required for the first pre-battle sample pipeline.

Keep the extracted WG crate shared by both forms so the desktop path and the
standalone path cannot drift.

## 7. Non-goals for the first pass

- no rating calculation;
- no automatic model fitting;
- no post-battle label capture;
- no GUI configuration screen;
- no bundled game-data download. The collector should accept the same game
  data/build inputs the app already uses, or document where to point it.

## 8. Open questions

- Which `Region`/newtype home is cleanest without creating a large
  dependency graph?
- Does the standalone binary need the same proxy configuration as the app?
- Should it reuse the app data directory by default, or always require an
  explicit `--output`?
- Is a single `arena_id` plus `match_started_at` enough for dedup, or should
  the client add a player-independent match id?
- For end-user distribution, how should the collector discover the game
  installation and live replay directory on Windows, Linux, and macOS?

## 9. Relationship to the operations plan

The account lookup, Operations fetch, live display, and current JSONL append
are tracked in `docs/WOWS_OPERATIONS_STATS_PLAN.md`. This document is the
deferred extraction plan for the sample-writing part only.
