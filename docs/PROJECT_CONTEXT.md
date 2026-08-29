# Project Context

Handoff notes for working with this repository on a fresh machine. Read this
before making changes. It records conventions and current state that are not
obvious from the code alone.

## What this repository is

wows-toolkit is a Rust workspace (edition 2024, rust 1.97) for reading,
parsing, rendering, and analyzing World of Warships game data, replay files,
and resource packages. Main crates live under `crates/`; see
`docs/ARCHITECTURE.md` for a detailed overview. This checkout is a fork:

- Upstream: https://github.com/landaire/wows-toolkit
- Fork: https://github.com/Immovable-Library/wows-toolkit

## Branch conventions

- `main` is a pristine mirror of upstream `main`. It is updated only by the
  scheduled sync workflow; never commit or push local work to it.
- `sync-workflow` is the fork's default branch. It holds only
  `.github/workflows/sync-upstream.yml`, which fast-forwards upstream `main`
  into the fork's `main` twice a day (03:17 and 15:17 UTC) and can be run
  manually from the Actions tab. Do not run `gh repo sync` on this fork: it
  syncs the default branch, which would disturb `sync-workflow`.
- `codex/local-changes` is the working branch with all local modifications.
  Clone with `git clone -b codex/local-changes ...`. Open pull requests from
  this branch against upstream `main`.

## Local changes carried on codex/local-changes

Two commits on top of upstream:

1. `9fb6e451` Add live Operations player stats via the Wargaming API
   - WargamingClient for the public WG API (account/list, account/info,
     ships/stats, solo Operations statistics)
   - background task that reads a live battle's roster and fetches each
     player's Operations stats
   - Current Match player tracker Operations columns (Ops WR, PR/5-star
     rate, Battles/Ops, Dmg/Ops XP) with en/zh strings
   - per-player Operations results persisted from finished replays to
     ops_results.jsonl
   - build.ps1 Windows cargo wrapper; architecture and WG API docs
2. `afebfee3` Add Operations sample analysis script and API references
   - scripts/analyze_ops_samples.py joins pre-battle oper_solo snapshots to
     per-match results and measures prediction quality
   - docs/WOWS_OPERATIONS_ANALYSIS.md initial findings
   - WG API statistics-scope reference and Vortex API Postman reference

## Operations XP model analysis (2026-08-27)

The XP allocation model is a within-game share regression:
`share(exp) ~ eff_total + scouting_damage + ship_class_dummies`.

Key findings across 2060 replay games (Q6 damage-type rechecked 2026-08-30
on the 2025+ merged 1943-game / 13600-row set: 455 personal + 1488 scraped
replays, with the `_avia` duplicate-damage bug fixed; HHI rechecked on the
earlier 2068-game / 14476-row set):

- **Ship class K values (multiplicative model, vs CA=1.00, 2025+ corpus):**
  raw-eff: DD=0.83, BB=0.96, CV=0.64, SS=1.45. Re-priced by damage-type
  coefficients (see `output/k_recompute_damage_types.json`): DD=0.77,
  BB=0.99, CV=0.70, SS=1.27. Damage-type composition explains ~41% of SS's
  premium, ~19% of CV's penalty, and nearly all of BB's small penalty; DD's
  penalty is a genuine residual, not composition.
- **Damage type (Q6-A):** Ship torpedoes have the highest XP coefficient
  (~0.0169), then ram (~0.0144), aerial torpedoes (~0.0138), main battery
  (~0.0137), fire (~0.0134), secondary (~0.0110), rockets (~0.0109), skip
  bombs (~0.0108), dive bombs (~0.0091), flood (~0.0041), plane/AA damage
  (~0.0002). Fire is not discounted vs main battery; flood is. Aerial
  torpedoes earn ~18% less than ship torpedoes but ~52% more than dive
  bombs. Rockets and skip bombs are not significantly different from dive
  bombs.
- **Secondary battery (Q6-A2):** Secondary damage earns ~0.0110 XP-share per
  ship-equivalent vs 0.0137 for main battery (~20% lower, HC0 t=-16.0).
  Secondary is 33% of BB ship-eff, so the discount mainly affects BB; the
  split improves the damage-type model R2 by +0.018. The community rumor is
  directionally supported, but the discount is mild.
- **Plane/AA damage:** ~2.1% of raw ship-eff earns essentially no XP
  (~0.0002, not significant); it should be excluded from the efficiency
  metric going forward.
- **Damage concentration / HHI (Q6-B):** DD's damage is MORE concentrated
  (HHI 0.206 vs CA 0.141), and concentrated damage is penalized (-0.089
  coefficient). This explains ~47% of DD's K penalty. SS's HHI is highest
  (0.286), masking its true WG bonus.
- **Reinforcement damage (Q6-C):** Community claim "reinforcement damage
  gives no XP" is false. sec_failed has zero effect on XP allocation after
  controlling for game-level eff. See `docs/reinforcement-damage-analysis.md`.
- **Other factors (Items 7-10):** Achievements, plane kills, building damage,
  and objective ribbons have negligible explanatory power (R² gain < 0.5%).
- **Remaining unknowns:** ~53% of DD's K penalty and ~50% of CV's K penalty
  remain unexplained by damage type, concentration, or other tested factors.

See `docs/Q6_CLASS_K_ANALYSIS.md` for full analysis.

## Community-sourced battle results (new data source)

`wows-scoreboard-extract/battle_results/` stores end-of-battle screenshots
and descriptions from community contributors. Each entry has:
- `screenshots/` - raw scoreboard images
- `descriptions/` - Markdown files with context (scenario, stars, AFK status)
  and extracted player tables (name, tier, ship, kills, XP)

This data source complements replay analysis by providing actual post-bonus
XP values, AFK flags, and tier/class distributions not available in replays.
Too few samples to use yet (3 as of 2026-08-27); integration planned when
sample count reaches 20+.

## Routine development flow

```
git clone -b codex/local-changes https://github.com/Immovable-Library/wows-toolkit.git
git fetch fork main
git merge fork/main          # pull in the latest upstream mirror
git push fork codex/local-changes
```

When ready to contribute upstream, open a PR from `codex/local-changes` to
`landaire:main`. Do not rewrite the history of `codex/local-changes` with
rebase or force-push once it contains merges.

## Machine-specific notes

- The repository is jj-colocated per AGENTS.md, but this environment uses
  plain git; jj is not installed. Git is fine for day-to-day work.
- `build.ps1` hardcodes local paths (Visual Studio 18 vcvars64 and the
  rsproxy.cn rustup mirror). Compiling is not required for idea validation:
  read `docs/`, search the code, and discuss plans without building.

## Documentation index

- docs/ARCHITECTURE.md - architecture and stack notes
- docs/WOWS_OPERATIONS_SAMPLE_COLLECTOR.md - standalone collector design
- docs/WOWS_OPERATIONS_STATS_PLAN.md - Operations rating plan
- docs/WOWS_OPERATIONS_ANALYSIS.md - sample analysis findings
- docs/WOWS_WG_API_REFERENCE.md - Wargaming public API reference
- docs/vortex_api_postman_reference.md - Vortex client API reference
- docs/Q6_CLASS_K_ANALYSIS.md - Q6: ship class K decomposition (2026-08-27)
- docs/reinforcement-damage-analysis.md - reinforcement damage analysis
- AGENTS.md - repository instructions read by Codex
