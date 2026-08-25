# Vortex API request reference (Postman)

Vortex is the World of Warships game-client internal API, separate from the
Wargaming public developer API. All calls below are unauthenticated GET
requests. No custom headers are required; the responses are plain JSON.

## Hosts by server

| Server | Vortex host |
| --- | --- |
| EU | `https://vortex.worldofwarships.eu` |
| NA | `https://vortex.worldofwarships.com` |
| Asia | `https://vortex.worldofwarships.asia` |
| RU (Lesta) | `https://vortex.korabli.su` |
| PT test | `https://vortex.worldofwarships.pt` |

## Endpoint 1: player search

```text
GET https://vortex.worldofwarships.eu/api/accounts/search/autocomplete/{name}/
```

`{name}` is a URL-encoded player name.

Response:

```json
{
  "status": "ok",
  "data": [
    { "spa_id": 502514064, "name": "uocat", "hidden": false },
    { "spa_id": 579813326, "name": "uocat_prpr", "hidden": false }
  ]
}
```

`spa_id` is the account id used by the other endpoints.

## Endpoint 2: account statistics

```text
GET https://vortex.worldofwarships.eu/api/accounts/{account_id}/
```

Response is keyed by account id:

```json
{
  "status": "ok",
  "data": {
    "502514064": {
      "statistics": {
        "pvp": { "...": 0 },
        "pve": { "...": 0 },
        "pvp_solo": { "...": 0 },
        "pvp_div2": { "...": 0 },
        "pvp_div3": { "...": 0 },
        "rank_solo": { "...": 0 },
        "rank_div2": { "...": 0 },
        "rank_div3": { "...": 0 },
        "rank_old_solo": { "...": 0 },
        "rank_old_div2": { "...": 0 },
        "rank_old_div3": { "...": 0 },
        "rank_info": { "...": 0 },
        "seasons": { "...": 0 },
        "basic": { "...": 0 },
        "mastery_sign": "Sign_M"
      },
      "name": "uocat",
      "created_at": 1329749081.0,
      "activated_at": 1329749114.0,
      "visibility_settings": false,
      "dog_tag": { "...": 0 }
    }
  }
}
```

There is no `oper` / `oper_solo` key in `statistics`; Operations are not
exposed by vortex.

Each battle-scope object (`pvp`, `pve`, `pvp_solo`, ...) shares one field
shape. Notable fields versus the Wargaming public API:

```text
original_exp          base XP, excludes premium-account multiplier
premium_exp           XP including the premium-account multiplier
exp                   total XP (includes additional modifiers)
damage_dealt          total damage
frags                 total kills
wins / losses
survived              battles survived
win_and_survived      battles won and survived
damage_dealt_to_buildings
frags_by_main / frags_by_tpd / frags_by_ram / frags_by_planes /
frags_by_dbomb / frags_by_atba
hits_by_main / shots_by_main      (and per-weapon pairs)
battles_count          total battles
battles_count_512 / battles_count_510 / battles_count_078 /
battles_count_0910 / battles_count_0711
max_frags / max_damage_dealt / max_exp / max_premium_exp
scouting_damage / ships_spotted / art_agro / tpd_agro
capture_points / dropped_capture_points
control_captured_points / control_dropped_points
team_control_captured_points / team_control_dropped_points
```

## Endpoint 3: per-ship statistics

```text
GET https://vortex.worldofwarships.eu/api/accounts/{account_id}/ships/{battle_type}/
```

`{battle_type}` values that return HTTP 200:

```text
pvp
pvp_solo
pvp_div2
pvp_div3
rank_solo
rank_div2
rank_div3
pve
```

Values that return HTTP 404 (not supported):

```text
oper
oper_solo
pve_solo
pve_div2
pve_div3
clan
club
```

Response is keyed by account id, then by ship id:

```json
{
  "status": "ok",
  "data": {
    "502514064": {
      "statistics": {
        "3765352144": {
          "pve": { "...": 0 },
          "mastery_sign": "Sign_M"
        }
      },
      "name": "uocat",
      "created_at": 1329749081.0,
      "activated_at": 1329749114.0,
      "visibility_settings": false
    }
  }
}
```

Each ship entry has the requested battle-type scope plus `mastery_sign`.
Ships with no battles in that scope carry an empty object.

## Notes

- No authentication or custom headers are needed for these public endpoints.
- The search endpoint returns `spa_id`, which equals the `account_id` used by
  the account and ships endpoints.
- `original_exp` is the clean base-XP signal: it excludes the 1.65
  premium-account multiplier, unlike the Wargaming public API where the
  Operations `xp` field is premium-inclusive.
- Operations (the rework scenario mode) is not exposed by vortex at all.
