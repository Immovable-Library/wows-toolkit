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
