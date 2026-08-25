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
- AGENTS.md - repository instructions read by Codex
