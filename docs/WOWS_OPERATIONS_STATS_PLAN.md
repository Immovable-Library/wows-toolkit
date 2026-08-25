# WoWS Operations Stats: Development Plan

> Status: planning
> Last updated: 2026-08-24

## 1. Goal

The current "Current Match" player tracker shows PVP stats from the existing
shipbuilds match-stats service:

- overall win rate
- per-ship win rate
- battles
- average damage
- PR / ship PR

We want to add Operations mode stats for the same player account ids.

The WG account lookup work is now in place and gives us `account_id` for each
player. The next step is to use that `account_id` to fetch Operations stats
from the WG API.

## 2. Current Architecture

### PVP stats path

- `crates/wows-toolkit/src/data/match_stats.rs`
  - `Region`
  - `PlayerStatsOut`
  - `MatchStatsClient`
  - shipbuilds `match_stats` API
- `crates/wows-toolkit/src/task/live_match_stats.rs`
  - scans a live or local replay roster
  - builds `LiveIdentities`
  - fetches PVP stats
- `crates/wows-toolkit/src/ui/player_tracker/mod.rs`
  - `MatchStatsState`
- `crates/wows-toolkit/src/ui/player_tracker/current_match.rs`
  - renders PVP stat cells
  - `row_stats()` selects Overall or Ship scope

### WG account lookup path

- `crates/wows-toolkit/src/data/wargaming.rs`
  - `WargamingClient`
  - `WargamingAccount`
  - `search_accounts(region, search)`
  - `find_exact_account(region, search)`
  - `find_exact_accounts(region, searches)`
- `crates/wows-toolkit/src/data/match_stats.rs`
  - `Region::wargaming_api_host()`
- `current_match.rs`
  - manual WG account lookup
  - auto roster WG lookup using `type=exact`

## 3. Proposed Design

### 3.1 Data model

Add a dedicated Operations stats type rather than overloading `PlayerStatsOut`.

Expected shape, pending actual API response:

```rust
pub struct WowsOperationsStats {
    pub account_id: AccountId,
    pub battles: Option<i64>,
    pub wins: Option<i64>,
    pub win_rate: Option<f64>,
    pub damage: Option<i64>,
    pub avg_damage: Option<i64>,
    // plus whatever fields the real WG API returns
}
```

Do not guess field names until the API is known. The plan is to parse the real
response and keep unknown fields tolerant.

### 3.2 Client

Either extend `WargamingClient` or add a sibling client:

```rust
pub struct WargamingOperationsClient {
    http: Arc<reqwest::blocking::Client>,
}
```

It must:

- accept `Region`
- accept one or many `account_id`s
- prefer a batch endpoint if available
- reuse the existing proxy configuration
- return a structured error type
- never block the UI thread; run from the background parser/network thread

### 3.3 Background flow

Current live stats flow:

```text
scan roster
  -> build LiveIdentities
  -> fetch PVP match stats
  -> MatchStatsState::Ready
```

Proposed flow:

```text
scan roster
  -> build LiveIdentities
  -> resolve WG account ids if missing
  -> fetch PVP match stats
  -> fetch Operations stats by account ids
  -> store both in the current match state
```

Operations fetch should be best-effort:

- a failed Operations call should not erase PVP results
- rate limiting should be respected
- stale matches must still be rejected via `started_at`

### 3.4 State

Do not duplicate the whole player tracker. Add a separate field such as:

```rust
pub(crate) operations_stats: OperationsStatsState
```

or change the existing `MatchStatsState::Ready` payload into:

```rust
pub struct CurrentMatchStats {
    pub pvp: HashMap<AccountId, PlayerStatsOut>,
    pub operations: HashMap<AccountId, WowsOperationsStats>,
}
```

The second option is cleaner because the UI reads both together and avoids two
state machines.

### 3.5 UI

Likely changes:

- add an Operations column or a second-line stat block per player
- add an `Operations` view/scope toggle if the API returns both account and
  ship scopes
- show `-` when the player has no Operations battles
- keep existing PVP Overall/Ship behavior unchanged

Suggested first pass:

```text
Class | Player | Ship | WR | PR | Battles | Avg DMG | Encounters | Actions
                                                      + Ops WR
                                                      + Ops Battles
                                                      + Ops Avg DMG
```

Or add an "Operations" toggle beside Overall/Ship. Wait for actual fields before
locking the layout.

## 4. Implementation Steps

1. Receive WG Operations API details.
   - endpoint URL
   - request format
   - response fields
   - batch support
   - rate limits

2. Add response model and error variants.

3. Add client method.

4. Wire the client into the existing background flow.

5. Extend `PlayerTracker` state.

6. Render Operations stats in Current Match.

7. Add fixtures and unit tests for:
   - response parsing
   - missing/empty Operations data
   - region selection
   - batch account-id query
   - stale-match rejection

8. Run:

```text
cargo test -p wows_toolkit
cargo check -p wows_toolkit
```

## 5. Open Questions

- What is the exact Operations stats endpoint?
- What request parameters does it accept?
- Does it support bulk account-id lookup?
- Are stats account-scoped, ship-scoped, or both?
- What fields are returned?
- What is the rate limit?
- How should a player with zero Operations battles be represented?

## 6. Record of Completed Changes

### WG account resolution

- Added `crates/wows-toolkit/src/data/wargaming.rs`.
- Added `WargamingClient`.
- Added single-name fuzzy search.
- Added exact-match selection.
- Added multi-name `type=exact` batch lookup.
- Added WG API host mapping for Asia/EU/NA.
- Reused existing `Region` model.

### Current Match debug tooling

- Existing `debug_replay_picker` loads a local replay as the current match.
- Added manual WG account lookup.
- Added auto roster WG account lookup.
- Auto lookup runs in a background thread.
- Region is inferred from the current match when possible, with a manual
  selector as fallback.

### Environment

- Installed Rust 1.97.1 and cargo.
- Added Visual Studio C++ workload and Windows SDK.
- Verified `cargo check -p wows_toolkit`.

### Operations stats fetch

- Added `WowsOperationsStats` (solo Operations shape) and
  `WargamingClient::fetch_operations_stats(region, account_ids)`.
- `account/info` parsing keys by account id and drops entries with no
  `oper_solo` block.
- Added unit tests for the response shape, the API error body, and the
  account-id joining helper.
- Added a debug-only "Query operations" probe in the Current Match sub-tab so
  the live API path can be exercised without being in a battle.
- Saved the WG API reference at `docs/WOWS_WG_API_REFERENCE.md`.

### Live display and sample collection

- Added `WargamingClient::fetch_ship_operations_stats(region, account_id)`
  backed by `wows/ships/stats/`, returning only ships with non-zero Operations
  battles. Verified the ship-level `oper_solo` shape mirrors the account shape
  (`xp`, `battles`, `wins`, `losses`, `survived_wins`, `survived_battles`,
  `wins_by_tasks`).
- Added derived metrics on `WowsOperationsStats`: `win_rate`,
  `five_star_rate` (five-star wins over all battles), and `avg_xp`.
- Wired Operations fetch into `resolve_and_fetch`: one batch `account/info`
  plus one `ships/stats` per human (Operations rosters have at most seven
  humans), running on the background parser thread.
- Added `OperationsStatsState` and `OperationsPlayerStats` to `PlayerTracker`,
  with a stale-match-guarded setter.
- Rendered account + current-ship Operations stats as the second detail line
  in the Current Match player cell, matching the ship column's two-line layout.
- Appended one JSON line per player to `ops_samples.jsonl` in the app data
  directory on each live match, recording account and current-ship stats plus
  `ts`, `arena_id`, `account_id`, and `ship_id` for later analysis.
- The appended row is a pre-battle snapshot of the historical stats shown in
  the Current Match player tracker, not a post-battle record. The current
  battle's outcome must not leak into the prediction input.
- The plan to extract sample collection into an independent process is
  recorded in `docs/WOWS_OPERATIONS_SAMPLE_COLLECTOR.md`; implementation is
  deferred.

### Post-battle result capture and Operations column widths

- Added `OperationsMatchResult` and `persist_operations_result` in
  `crates/wows-toolkit/src/data/session_stats.rs`. When a finished Operations
  replay is read by the session-stats path, every human's per-match result is
  appended to `ops_results.jsonl` alongside the pre-battle snapshot.
- The result row carries `ts`, `arena_id`, `account_id`, `ship_id`, `is_win`,
  `is_draw`, `damage`, `frags`, `raw_xp`, and `base_xp`. It is joined to the
  snapshot on `arena_id`, `account_id`, `ship_id`, and `ts` during analysis.
- The purpose is to rank teammates from the pre-battle snapshot, so the label
  is the individual per-match output (damage, frags, XP), not the recording
  player's own line. The replay does not record the per-match star count, so
  the label is limited to those individually observable figures.
- Widened the four Operations stat columns in
  `crates/wows-toolkit/src/ui/player_tracker/current_match.rs` so the joined
  `PVP/Operations` text no longer truncates.

## 7. Operations API Request Extract

From the provided `curl`:

```text
POST https://api.worldofwarships.eu/wows/account/info/
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

application_id=4abd85d2d22608f74b646410ef7e3a16
account_id=502514064,566060956
extra=statistics.oper_solo
fields=-statistics.pvp
```

Extracted facts:

- Endpoint: `wows/account/info/`
- Method: `POST`
- Region host: same existing `Region` mapping
  - EU: `https://api.worldofwarships.eu`
  - NA: `https://api.worldofwarships.com`
  - Asia: `https://api.worldofwarships.asia`
- `application_id`: fixed
- `account_id`: comma-separated batch
- `extra=statistics.oper_solo`: requests solo Operations statistics
- `fields=-statistics.pvp`: excludes normal PVP statistics

Confirmed response (retrieved 2026-08-24 from the EU host):

```json
{
  "status": "ok",
  "data": {
    "502514064": {
      "account_id": 502514064,
      "created_at": 1435293341,
      "updated_at": 1787511681,
      "logout_at": 1787468905,
      "nickname": "uocat",
      "last_battle_time": 1787317278,
      "leveling_points": 36006,
      "leveling_tier": 17,
      "private": null,
      "statistics": {
        "battles": 27093,
        "distance": 1248132,
        "oper_solo": {
          "xp": 258001,
          "battles": 111,
          "survived_wins": 66,
          "survived_battles": 71,
          "wins": 99,
          "losses": 12,
          "wins_by_tasks": { "2": 2, "3": 4, "4": 21, "5": 72 }
        }
      },
      "hidden_profile": false,
      "karma": null,
      "stats_updated_at": 1787511681
    }
  },
  "meta": { "count": 2, "hidden": null }
}
```

Response facts:

- `status` is `"ok"` on success, matching `account/list`.
- `data` is a JSON object keyed by `account_id` string, NOT an array. The
  parser must map `account_id -> entry` rather than decode a `Vec`.
- `meta.count` is the returned entry count. `meta.hidden` can be null.
- Each entry carries account metadata (`nickname`, `leveling_tier`,
  `last_battle_time`, `private`, `hidden_profile`, ...) plus `statistics`.
- `statistics.battles` is the account total. Operations battles are separate,
  inside `statistics.oper_solo`.
- `statistics.oper_solo` has exactly these fields in the observed response:
  `xp`, `battles`, `survived_wins`, `survived_battles`, `wins`, `losses`,
  `wins_by_tasks`.
- `wins_by_tasks` is an object mapping task difficulty (`"0"` .. `"5"`) to a
  win count. Treat it as `HashMap<String, u64>` and make it optional.
- There is NO damage, average damage, or PR in `oper_solo`. Operations stats
  are win/loss, survival, XP and per-task wins only. The earlier "avg damage"
  column idea does not apply; derive win rate from `wins / battles`.

Operations scope fields: `statistics.oper_div`, `statistics.oper_div_hard`,
and `statistics.oper_solo`. The two `oper_div` fields cover the pre-rework
Operations mode (team queue, map and difficulty picked manually); the current
Operations mode is reported only under `oper_solo`, so the toolkit queries
`oper_solo`.

Still needed before implementation:

- a confirmed error body shape (assumed to match `account/list`).

## 8. Rating Methodology (reference for the future Operations score)

The wows-numbers Personal Rating (PR) formula is the reference for turning the
raw Operations sample data into one comparable score. The PR formula is already
implemented for PVP in
`crates/wows-replay-insights/src/personal_rating.rs`; this section records which
parts transfer to Operations and which must be re-fitted from samples.

### 8.1 Reusable principles

1. Compare ratios, not absolute values. PR uses actual/expected per metric, so
   ships with different damage ceilings or XP pools become comparable. This is
   the same correction Operations needs for the low-tier vs high-tier XP pool
   difference.
2. Build expected values per ship. PR uses community per-ship expected values.
   Operations has no public equivalent, so expected XP and expected five-star
   rate must be fitted from the collected samples.
3. Weight metrics by individual controllability. PR orders damage over frags
   over win rate and gives win rate the smallest weight because it is a team
   result. Operations has seven players, so win rate and star rate are
   team-diluted and should be downweighted; average XP is the only individual
   output metric and should carry the highest weight.
4. Use a floor function and clamp at zero. PR maps a ratio through
   `max(0, (r - floor) / (1 - floor))`, so a metric below its floor contributes
   nothing. The Operations score needs its own floors.
5. Compress to a bounded scale. PR lands in 0-3000 so ratings are comparable,
   bandable, and colorable. The Operations score should pick a fixed range the
   same way.
6. Exclude non-skill factors. PR ignores plane kills because AA is automated.
   Survival in Operations looks like a playstyle side effect rather than a
   clean skill signal, so it should be low weight or excluded.

### 8.2 Observed sample confirmation

Three hand-labelled account snapshots confirm the ordering:

| metric      | high    | mid     | skilled |
|-------------|---------|---------|---------|
| avg XP      | 2209    | 1832    | 2432    |
| five-star % | 44.6    | 42.6    | 46.7    |
| avg stars   | 3.76    | 3.67    | 3.64    |
| win rate %  | 89.2    | 87.0    | 84.6    |
| survival %  | 57.7    | 78.3    | 48.9    |

Win rate barely separates the three players, while average XP separates the
most. Survival is inverted relative to XP and five-star rate, so it is not a
clean skill signal.

### 8.3 Proposed v1 skeleton

```text
rXP    = actualAvgXp / expectedAvgXp(ship or tier, premium-account basis)
rStars = actualFiveStarRate / expectedFiveStarRate(ship)
nXP    = max(0, (rXP    - a) / (1 - a))
nStars = max(0, (rStars - b) / (1 - b))
score  = W_xp * nXP + W_stars * nStars   # mapped to a fixed range like 0-3000
```

`a`, `b`, `W_xp`, and `W_stars` are fitted from labelled samples. The fitting
problem is easier than PR because the samples can carry hand labels
(supervised), so the weights and floors can be chosen to separate skill tiers
rather than hand-tuned.

### 8.4 Metric mapping from PR inputs

PR's three inputs map to Operations metrics as follows:

| PR input | PR weight | Operations counterpart | Notes |
|----------|-----------|------------------------|-------|
| `damage_dealt` | 700 | average XP (`xp / battles`) | XP is the only individual output metric; per-ship expected XP fixes the low-tier/high-tier pool gap |
| `frags` | 300 | five-star rate (`wins_by_tasks["5"] / battles`) | Operations-only quality signal; PR has no equivalent |
| `wins` | 150 | win rate | downweighted further; the seven-player team dilutes it and the ceiling is 85-90% |

Survival rate (`survived_battles / battles`) is an optional Operations-only
signal with no PR equivalent; sample analysis shows it is inverted relative to
XP and star rate, so keep it low-weight or excluded.

The frame (expected-value normalization, floor, weighted sum) transfers from
PR, but both the inputs and the expected table must be re-derived. There is no
public Operations expected table, so expected XP and expected five-star rate
are fitted from the collected samples.

### 8.5 Open calibration decisions

- Expected XP denominator: per-tier first while data is small, then per-ship
  once enough samples exist.
- Premium-account XP factor: the API XP already includes the 1.65 premium
  multiplier. Expected values must use the same basis or non-premium players
  are systematically under-scored.
- Star metric: `five_star_rate` uses five-star wins over all battles. A
  weighted average of the full `wins_by_tasks` map (0..5 stars) carries more
  signal than the binary five-star cutoff and may be a better `rStars`.
