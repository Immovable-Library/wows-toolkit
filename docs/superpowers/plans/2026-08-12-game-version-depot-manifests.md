# Game Version Depot Manifests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `wows-data-mgr` parse and download the client, content, and localization depot manifests recorded in `game_versions.toml`.

**Architecture:** Model depot and manifest identifiers as newtypes grouped into `DepotManifest`, with custom deserialization for optional flat TOML field pairs. Build a list of download requests independently from process execution so depot selection is directly testable, then execute each pinned request sequentially into the same build directory.

**Tech Stack:** Rust 1.92, edition 2024, Serde, TOML, rootcause, clap, DepotDownloader

## Global Constraints

- Preserve the flat `game_versions.toml` schema.
- Require the client depot pair; represent omitted content and localization pairs with `Option`.
- Reject half-present optional depot pairs as malformed input.
- Use ASCII only in code, comments, UI strings, and commit messages.
- Use `jj`, with one focused commit per logical milestone and no AI attribution.
- Preserve unrelated working-copy changes.
- Treat `dump-renderer-data --game-dir` as a source override that may accompany `--latest`, `--version`, or `--build`.

---

### Task 1: Multi-depot manifest model

**Files:**
- Modify: `crates/wows-data-mgr/src/manifest.rs`

**Interfaces:**
- Produces: `DepotId(u32)`, `ManifestId(String)`, `DepotManifest { depot_id, manifest_id }`
- Produces: `GameVersionEntry { version, client, content, localization }`
- Preserves: `GameVersionManifest::latest_build`, `find_by_version`, and `get`

- [ ] **Step 1: Write failing deserialization tests**

Add tests using literal TOML fixtures. Assert that a full entry produces all three exact `DepotManifest` values, that an entry containing only the client pair produces `None` for the other depots, and that `content_depot_id` without `content_manifest_id` returns an error. Update the existing lookup fixture constructors to use the desired new API so compilation also identifies every stale field.

```rust
#[test]
fn parses_split_depot_manifests() {
    let manifest: GameVersionManifest = toml::from_str(
        r#"
        [versions.13015711]
        version = "15.7.0"
        client_depot_id = 552993
        client_manifest_id = "client"
        content_depot_id = 552991
        content_manifest_id = "content"
        localization_depot_id = 552994
        localization_manifest_id = "localization"
        "#,
    )
    .unwrap();

    let entry = manifest.get(13015711).unwrap();
    assert_eq!(entry.client, DepotManifest::new(DepotId(552993), ManifestId("client".into())));
    assert_eq!(entry.content, Some(DepotManifest::new(DepotId(552991), ManifestId("content".into()))));
    assert_eq!(entry.localization, Some(DepotManifest::new(DepotId(552994), ManifestId("localization".into()))));
}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test -p wows-data-mgr manifest::test --lib`

Expected: compilation fails because the new depot types and fields do not exist.

- [ ] **Step 3: Implement typed depot manifests and flat Serde mapping**

Derive `Debug`, `Clone`, `PartialEq`, `Eq`, `Serialize`, and `Deserialize` for the identifier newtypes. Give `DepotManifest` a `new` constructor. Deserialize `GameVersionEntry` through a private flat helper with required client fields and optional content/localization fields. Convert each optional pair with a helper returning a structured deserialization error when exactly one member is present. Implement matching serialization so round trips preserve the flat schema.

Do not default missing required fields, and do not use sentinel identifiers.

- [ ] **Step 4: Run focused and integration manifest tests**

Run: `cargo test -p wows-data-mgr manifest::test --lib`

Expected: all manifest tests pass.

Run: `cargo run --release -p wows-data-mgr -- list`

Expected: the real `game_versions.toml` parses; compilation may still identify stale CLI display fields to be handled in Task 2.

- [ ] **Step 5: Request adversarial review and commit**

Dispatch a fresh reviewer to challenge missing-data semantics, Serde round trips, newtype boundaries, and whether malformed pairs can be silently accepted. Resolve Critical and Important findings, rerun the focused tests, then commit only `manifest.rs`:

```powershell
jj commit 'crates/wows-data-mgr/src/manifest.rs' -m 'fix(data-mgr): model split depot manifests'
```

### Task 2: Multi-depot download and CLI display

**Files:**
- Modify: `crates/wows-data-mgr/src/download.rs`
- Modify: `crates/wows-data-mgr/src/main.rs`

**Interfaces:**
- Consumes: `DepotManifest`, `GameVersionEntry::client`, `content`, and `localization`
- Produces: private `download_requests(entry: Option<&GameVersionEntry>) -> Vec<Option<&DepotManifest>>`
- Preserves: `download_build(build, entry, data_dir, repo_root, username_override) -> Result<(), Report>`

- [ ] **Step 1: Write failing depot selection tests**

Test the pure request-selection helper with real `GameVersionEntry` values. Assert literal ordered results for a full pinned entry (`client`, `content`, `localization`), a client-only historical entry (`client`), and an unpinned download (`None`). This catches omitted depots, wrong order, and accidental fallback to a latest-branch request.

```rust
#[test]
fn pinned_download_selects_every_available_depot() {
    let entry = entry_with_all_depots();
    assert_eq!(
        download_requests(Some(&entry)),
        vec![Some(&entry.client), entry.content.as_ref(), entry.localization.as_ref()]
    );
}

#[test]
fn public_download_has_one_unpinned_request() {
    assert_eq!(download_requests(None), vec![None]);
}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test -p wows-data-mgr download::test --lib`

Expected: compilation fails because `download_requests` does not exist and the download code still accesses removed fields.

- [ ] **Step 3: Implement sequential per-depot downloads**

Make `download_requests` return available pinned depots in client, content, localization order, or one `None` request for the public branch. Keep directory and file-list setup outside the loop. For each request, create a fresh `Command`, add `-app`, add matching `-depot` and `-manifest` arguments when pinned, then add the shared output, file list, username, and password arguments. Print the matching pair before execution. Stop on the first unsuccessful status and include its depot identity in the error when available.

Always attempt temporary file-list removal after the loop or after an execution failure without replacing the primary error.

- [ ] **Step 4: Update CLI list display**

Replace `entry.manifest_id` in the `list` table with `entry.content.as_ref().unwrap_or(&entry.client).manifest_id`. This fallback is correct because the table needs one representative downloadable game-data manifest and historical entries may lack content.

- [ ] **Step 5: Run focused tests and compile the executable**

Run: `cargo test -p wows-data-mgr download::test --lib`

Expected: all download selection tests pass.

Run: `cargo check -p wows-data-mgr --all-targets`

Expected: exit 0 with no stale single-depot field accesses.

- [ ] **Step 6: Reproduce the original command through the parse boundary**

Run: `cargo run --release -p wows-data-mgr -- list`

Expected: exit 0 after listing versions from the real split-depot manifest.

Do not run the original `dump-renderer-data --latest` command as verification because it performs authenticated network downloads and writes outside the repository. The shared manifest load path and release binary are exercised by `list`.

- [ ] **Step 7: Request adversarial review and commit**

Dispatch a fresh reviewer to challenge command construction, optional-depot behavior, cleanup on failure, error context, and CLI fallback semantics. Resolve Critical and Important findings and rerun Task 2 verification. Commit only the two implementation files:

```powershell
jj commit 'crates/wows-data-mgr/src/download.rs' 'crates/wows-data-mgr/src/main.rs' -m 'fix(data-mgr): download split game depots'
```

### Task 3: Final verification

**Files:**
- Modify: `crates/wows-data-mgr/src/main.rs`

**Interfaces:**
- Consumes the complete implementation from Tasks 1 and 2.
- Produces verification evidence only.

- [ ] **Step 1: Write failing CLI compatibility tests**

Use `Cli::try_parse_from` with literal argument arrays and assert that
`dump-renderer-data` accepts `--game-dir G:\\game` together with each of
`--latest`, `--version 15.7`, and `--build 13015711`. These tests catch any
Clap conflict reintroduced between the source override and selectors.

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test -p wows-data-mgr game_dir --bin wows-data-mgr`

Expected: the latest and version cases fail because Clap rejects the argument combination.

- [ ] **Step 3: Remove selector conflicts from `game_dir`**

Keep `game_dir: Option<PathBuf>` and its existing execution behavior, but
remove its `conflicts_with_all` attribute. Update the help text to say it
overrides the game data source and may be combined with any selector.

- [ ] **Step 4: Run focused CLI tests**

Run: `cargo test -p wows-data-mgr game_dir --bin wows-data-mgr`

Expected: all three selector combinations pass.

- [ ] **Step 5: Request adversarial review and commit**

Dispatch a fresh reviewer to check Clap behavior and confirm the source
override still bypasses registry and download lookup for every selector.
Resolve Critical and Important findings, rerun the focused tests, then commit
only the related `main.rs` change together with any Task 2 edits already
scheduled for that file.

- [ ] **Step 6: Format and inspect scope**

Run: `cargo fmt --all -- --check`

Expected: exit 0. If formatting is needed, run `cargo fmt --all`, inspect that unrelated user changes were not altered unexpectedly, and commit only formatting belonging to this milestone.

Run: `jj diff --stat`

Expected: unrelated pre-existing changes remain in the working copy and the milestone commits contain only their named files.

- [ ] **Step 7: Run the crate test suite**

Run: `cargo test -p wows-data-mgr --all-targets`

Expected: exit 0 with zero failed tests.

- [ ] **Step 8: Run the release parse smoke test**

Run: `cargo run --release -p wows-data-mgr -- list`

Expected: exit 0 and output lists the entries from `game_versions.toml`.

- [ ] **Step 9: Final adversarial review**

Dispatch a fresh reviewer over both milestone commits and the design spec. Ask them to identify requirement gaps, accidental changes to user work, weak tests, or violations of repository modeling and missing-data rules. Resolve all Critical and Important findings, then rerun every command in this task before reporting completion.
