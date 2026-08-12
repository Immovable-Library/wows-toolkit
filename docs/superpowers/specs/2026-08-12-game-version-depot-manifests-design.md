# Game Version Depot Manifests

## Problem

`game_versions.toml` records separate Steam manifests for the client, content,
and localization depots. `GameVersionEntry` still expects one `depot_id` and
one `manifest_id`, so deserialization fails before `wows-data-mgr` can run.

## Data model

Add `DepotId` and `ManifestId` newtypes and a `DepotManifest` value containing
one of each. `GameVersionEntry` contains:

- `version: String`
- `client: DepotManifest`
- `content: Option<DepotManifest>`
- `localization: Option<DepotManifest>`

Custom Serde field mapping preserves the flat manifest format:
`client_depot_id`, `client_manifest_id`, `content_depot_id`,
`content_manifest_id`, `localization_depot_id`, and
`localization_manifest_id`.

The client pair is required because every recorded version supplies it.
Content and localization pairs are optional because historical entries omit
one or both. A half-present optional pair is malformed input and must produce
a parse error rather than silently dropping the supplied value.

## Download behavior

For a pinned build, invoke DepotDownloader once for each available depot and
write all results into the same build directory. Each invocation receives the
matching depot and manifest IDs. The shared selective file list limits each
download to relevant files.

For the latest public branch, preserve the existing unpinned invocation.

If any pinned depot download fails, return the error and do not proceed to
later depots. Temporary file-list cleanup remains best effort.

## CLI output

Pinned downloads report each depot and manifest pair that will be downloaded.
The versions listing displays the content manifest when present. If content is
absent, it displays the client manifest so historical entries remain useful.

## Local game directory selection

`dump-renderer-data --game-dir` is a source override, not a build selector.
It may be combined with `--latest`, `--version`, or `--build`. The selected
build and version are resolved normally from `game_versions.toml`, while data
is read directly from the supplied directory without registry lookup or a
download.

## Tests

Add manifest tests that prove:

- the current flat three-depot schema deserializes;
- omitted content and localization pairs deserialize as `None`;
- a half-present optional pair is rejected;
- version lookup behavior remains unchanged with the new model.
- `--game-dir` parses successfully with each build selector.

Add download command construction tests so pinned builds produce one command
per available depot with matching IDs, while unpinned builds retain one public
branch command.
