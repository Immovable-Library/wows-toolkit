# Wargaming WoWS Public API Reference

Official developer portal:

- WoWS API reference index:
  https://developers.wargaming.net/reference/all/wows/
- `wows/account/list`:
  https://developers.wargaming.net/reference/all/wows/account/list/
- `wows/account/info`:
  https://developers.wargaming.net/reference/all/wows/account/info/

The portal pages are JavaScript-rendered, so the authoritative field shapes
below were captured from live requests.

Application id used by the toolkit (public, not a secret):

```text
4abd85d2d22608f74b646410ef7e3a16
```

Region hosts:

| Region | Host |
| --- | --- |
| EU | `https://api.worldofwarships.eu` |
| NA | `https://api.worldofwarships.com` |
| Asia | `https://api.worldofwarships.asia` |

## account/list

Resolves a player name to account ids.

```text
GET https://<host>/wows/account/list/
    ?application_id=...
    &search=<name>

POST https://<host>/wows/account/list/
    application_id=...
    &search=<comma,separated,names>
    &type=exact
```

Response:

```json
{
  "status": "ok",
  "meta": { "count": 1 },
  "data": [
    { "account_id": 503278143, "nickname": "skmon" }
  ]
}
```

The search is fuzzy by default. With `type=exact` and comma-separated names it
returns only exact matches, one entry per name that resolves.

## account/info

Account metadata and statistics. The toolkit uses it for solo Operations stats.

```text
POST https://<host>/wows/account/info/
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

application_id=...
&account_id=<id1>,<id2>,...
&extra=statistics.oper_solo
&fields=-statistics.pvp
```

Response:

```json
{
  "status": "ok",
  "meta": { "count": 1, "hidden": null },
  "data": {
    "502514064": {
      "account_id": 502514064,
      "nickname": "uocat",
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
      }
    }
  }
}
```

`data` is keyed by account id string, not a list.

`statistics.oper_solo` fields:

- `xp`
- `battles`
- `survived_wins`
- `survived_battles`
- `wins`
- `losses`
- `wins_by_tasks` (object keyed `"0"` through `"5"`)

No damage, average damage, or PR is exposed for Operations. Win rate is
derived from `wins / battles`.

There are three Operations scope fields: `statistics.oper_div`,
`statistics.oper_div_hard`, and `statistics.oper_solo`. The two `oper_div`
fields cover the pre-rework Operations mode (team queue, map and difficulty
picked manually); the current Operations mode is reported only under
`oper_solo`, so the toolkit queries `oper_solo`.

## account/info statistics scopes

The `statistics` object carries every battle-mode scope. The root `battles`
and `distance` are account-wide totals. The PvP scope (`statistics.pvp`) is
returned by default; every other scope must be listed in `extra`.

```text
statistics.battles
statistics.distance
statistics.pvp            (default)
statistics.pvp_solo       (extra)
statistics.pvp_div2       (extra)
statistics.pvp_div3       (extra)
statistics.rank_solo      (extra)
statistics.rank_div2      (extra)
statistics.rank_div3      (extra)
statistics.oper_solo      (extra)
statistics.oper_div       (extra)
statistics.oper_div_hard  (extra)
statistics.pve            (extra)
statistics.pve_solo       (extra)
statistics.pve_div2       (extra)
statistics.pve_div3       (extra)
statistics.clan           (extra)
statistics.club           (extra)
```

`extra` values use the dot form (`statistics.oper_solo`) for account/info,
but `ships/stats` takes the bare scope name (`oper_solo`) instead. See the
`ships/stats` section.

### Extra field catalog

The complete `extra` enumeration for `account/info`, as documented on the
developer portal:

```text
private.grouped_contacts
private.port
statistics.clan
statistics.club
statistics.oper_div
statistics.oper_div_hard
statistics.oper_solo
statistics.pve
statistics.pve_div2
statistics.pve_div3
statistics.pve_solo
statistics.pvp_div2
statistics.pvp_div3
statistics.pvp_solo
statistics.rank_div2
statistics.rank_div3
statistics.rank_solo
```

The `pve*`, `clan`, and `club` scopes share the full PvP field shape
(including `damage_dealt` and `frags`, which `oper_*` lacks).

`pve` / `pve_solo` / `pve_div2` / `pve_div3` are Co-op battles, not
Operations. They are distinct from `oper_*`: a Co-op loss does not appear in
`oper_*` losses and vice versa. The near-100% Co-op win rate is the giveaway;
Operations carry real losses. Do not use `pve.damage_dealt` as an Operations
damage signal.

`clan` is Clan Battles and `club` is Club Battles, both full-shape scopes.

`statistics.oper_*` exposes no `damage_dealt`, `frags`, `planes_killed`,
`damage_scouting`, or per-weapon sub-objects. Requesting those paths returns
`INVALID_FIELDS`, confirming the Operations scope is limited to XP, win/loss,
survival, and `wins_by_tasks`.

`extra=private.grouped_contacts` returns the grouped-contacts list under
`private`; `extra=private.port` returns the account's port. Both land under the
`private` key, which is only populated for the requesting account's own data
(OAuth-authenticated). Public lookups of other accounts return `private: null`,
so these two extras are not useful for the teammate-roster use case.

### statistics.pvp fields

The PvP scope carries everything the wows-numbers Personal Rating formula
needs. Core fields:

```text
battles, wins, losses, draws
frags, damage_dealt, xp
survived_wins, survived_battles
```

Secondary totals:

```text
planes_killed
capture_points, dropped_capture_points
control_captured_points, control_dropped_points
team_capture_points, team_dropped_capture_points
damage_scouting, art_agro, torpedo_agro, ships_spotted
damage_to_buildings, suppressions_count
battles_since_510, battles_since_512
```

Record maxima (`max_*`), each usually paired with a `max_*_ship_id`:

```text
max_frags_battle, max_xp, max_damage_dealt
max_planes_killed, max_ships_spotted
max_damage_scouting, max_total_agro
max_suppressions_count, max_damage_dealt_to_buildings
```

Per-weapon sub-objects:

```text
main_battery    { frags, max_frags_battle, max_frags_ship_id, shots, hits }
torpedoes       { frags, max_frags_battle, max_frags_ship_id, shots, hits }
second_battery  { frags, max_frags_battle, max_frags_ship_id, shots, hits }
aircraft        { frags, max_frags_battle, max_frags_ship_id }
ramming         { frags, max_frags_battle, max_frags_ship_id }
```

The same field set is shared by `pvp_solo`, `pvp_div2`, `pvp_div3`,
`rank_solo`, `rank_div2`, and `rank_div3`.

`battles_since_510` and `battles_since_512` are historical version markers
(battles since game versions 0.5.10 and 0.5.12), not a rolling recent-window
count.

## ships/stats

Returns every ship the account owns, including zero-battle ships, keyed by
account id.

```text
GET/POST https://<host>/wows/ships/stats/
    application_id=...
    &account_id=<id>
    &fields=<comma,separated,paths>
    &extra=<bare,scope,name>
```

Per-entry fields:

```text
ship_id
last_battle_time
distance
battles
```

`extra` accepts the bare scope names (no `statistics.` prefix and no `pvp`
entry; `pvp` is default):

```text
pvp_solo, pvp_div2, pvp_div3
rank_solo, rank_div2, rank_div3
oper_solo
```

Each scope under a ship carries the same field shape as the corresponding
account/info scope, including the per-weapon sub-objects. This is the source
of per-ship actual values for the Personal Rating calculation (battles, wins,
damage_dealt, frags), matched against wows-numbers expected values by
`ship_id`.

`extra=pvp` is rejected with `INVALID_EXTRA`; request `pvp.*` fields without
listing `pvp` in `extra`.

## clans/accountinfo

Resolves the clan membership for account ids.

```text
GET https://<host>/wows/clans/accountinfo/
    ?application_id=...
    &account_id=<id1>,<id2>,...
```

Response data is keyed by account id:

```json
{
  "502514064": {
    "account_id": 502514064,
    "account_name": "uocat",
    "joined_at": 1479977291,
    "role": "commander",
    "clan_id": 500137813
  }
}
```

`role` is one of `commander`, `officer`, `private`, `recruitment_officer`,
or similar clan ranks.

## clans/info

Clan details for one or more clan ids.

```text
GET https://<host>/wows/clans/info/
    ?application_id=...
    &clan_id=<id1>,<id2>,...
```

Fields include `name`, `tag`, `members_count`, `created_at`, `leader_id`,
`leader_name`, `creator_id`, `creator_name`, `description`, and the full
`members_ids` list.

## account/achievements

Earned battle achievements and in-progress achievements.

```text
GET https://<host>/wows/account/achievements/
    ?application_id=...
    &account_id=<id>
```

Response data is keyed by account id with two objects:

```text
battle    { "<achievement_code>": <count>, ... }
progress  { "<achievement_code>": <progress_value>, ... }
```

`battle` holds 200+ earned achievement counters; `progress` holds numeric
progress toward unfinished achievements. Achievement codes are game-internal
strings such as `PCH120_PVE_HON_HIT_TORP`.

## Personal Rating expected values (non-WG)

The wows-numbers Personal Rating formula needs per-ship expected values,
served from a separate source (not a Wargaming host):

```text
https://api.wows-numbers.com/personal/rating/expected/json/
```

Response:

```json
{
  "time": 1787533765,
  "data": {
    "3309254640": {
      "average_damage_dealt": 102910.89855072464,
      "average_frags": 0.8655072463768114,
      "win_rate": 50.64021739130436
    },
    "3248404240": []
  }
}
```

`data` is keyed by `ship_id`. A ship with no samples yet is an empty array.
The three expected fields map to the `ships/stats` actual values `damage_dealt`,
`frags`, and `wins`, divided by `battles`, which is exactly the PR formula
input.
