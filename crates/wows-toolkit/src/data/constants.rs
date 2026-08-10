//! Loading, judging, and installing the `constants.json` files that decode a
//! replay's server-provided battle results.

use std::path::Path;
use std::path::PathBuf;

use serde_json::Value;
use wowsunpack::data::Version;

/// Whether a set of replay constants was produced for the build it is being
/// used with. Results decoded through mismatched constants read the wrong
/// indices, so they are never persisted (see `replay_index::map_rows`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConstantsFit {
    Exact,
    Mismatched,
}

/// Judge `constants` against the build it is about to decode.
///
/// `VERSION.BUILD` is the authoritative answer when present. Files old enough
/// to omit it are judged on `VERSION.VERSION` against the build's own
/// `major.minor`, which is the most a version-only file can prove. Anything
/// that proves neither is `Mismatched`: an unverifiable file is exactly the
/// case this type exists to keep out of the database.
pub fn constants_fit(constants: &Value, build: u32, version: Option<Version>) -> ConstantsFit {
    let version_block = constants.get("VERSION");

    if let Some(file_build) = version_block.and_then(|v| v.get("BUILD")).and_then(Value::as_u64) {
        return if file_build == u64::from(build) { ConstantsFit::Exact } else { ConstantsFit::Mismatched };
    }

    let (Some(file_version), Some(version)) =
        (version_block.and_then(|v| v.get("VERSION")).and_then(Value::as_str), version)
    else {
        return ConstantsFit::Mismatched;
    };

    if file_version == format!("{}.{}", version.major, version.minor) {
        ConstantsFit::Exact
    } else {
        ConstantsFit::Mismatched
    }
}

/// A `constants.json` that has been read and identified.
#[derive(Debug, Clone)]
pub struct ParsedConstants {
    /// `VERSION.BUILD`: the build this file was dumped for.
    pub build: u32,
    /// `VERSION.VERSION`, the game version as `"15.2"`, when the file carries it.
    pub version: Option<String>,
    pub data: Value,
}

/// Where an imported file landed.
#[derive(Debug, Clone)]
pub struct InstalledConstants {
    pub build: u32,
    pub version: Option<String>,
    pub storage_path: PathBuf,
    /// The per-build dump copy, when the builds index knows that build.
    pub dump_path: Option<PathBuf>,
}

#[derive(Debug, thiserror::Error)]
pub enum ImportError {
    #[error("failed to read {}: {source}", path.display())]
    Read {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },
    #[error("file is not valid JSON: {source}")]
    Parse {
        #[source]
        source: serde_json::Error,
    },
    #[error("file has no VERSION.BUILD field; is it a constants.json?")]
    MissingBuild,
    #[error("failed to write {}: {source}", path.display())]
    Write {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },
    #[error("no application storage directory is available")]
    NoStorageDir,
}

/// Read a user-picked `constants.json` and take the build it belongs to from
/// its own `VERSION.BUILD`.
///
/// A file that does not say which build it is for is rejected rather than
/// assumed to match the loaded build: installing constants under the wrong
/// build number is the failure this import exists to fix.
pub fn read_constants_file(path: &Path) -> Result<ParsedConstants, ImportError> {
    let bytes = std::fs::read(path).map_err(|source| ImportError::Read { path: path.to_path_buf(), source })?;
    let data: Value = serde_json::from_slice(&bytes).map_err(|source| ImportError::Parse { source })?;

    let version_block = data.get("VERSION");
    let build = version_block
        .and_then(|v| v.get("BUILD"))
        .and_then(Value::as_u64)
        .and_then(|build| u32::try_from(build).ok())
        .ok_or(ImportError::MissingBuild)?;
    let version = version_block.and_then(|v| v.get("VERSION")).and_then(Value::as_str).map(str::to_owned);

    Ok(ParsedConstants { build, version, data })
}

/// Install `parsed` at every path a build reads constants from: the versioned
/// storage cache, and the build's dump directory when one exists.
///
/// The dump copy is overwritten unconditionally. `BuildData::from_dump` prefers
/// the dump-local file, so leaving a stale one in place would make the import a
/// no-op for any build that has been dumped.
pub fn install_constants(
    parsed: &ParsedConstants,
    storage_dir: Option<&Path>,
    dump_base: Option<&Path>,
) -> Result<InstalledConstants, ImportError> {
    let storage_dir = storage_dir.ok_or(ImportError::NoStorageDir)?;
    let storage_path = storage_dir.join(format!("constants_{}.json", parsed.build));
    let bytes = serde_json::to_vec(&parsed.data).map_err(|source| ImportError::Parse { source })?;
    std::fs::write(&storage_path, &bytes)
        .map_err(|source| ImportError::Write { path: storage_path.clone(), source })?;

    let dump_path = dump_base.and_then(|base| {
        let index = wows_data_mgr::builds::BuildsIndex::load(&base.join("builds.toml"));
        index.find_by_build(parsed.build).map(|entry| base.join(&entry.dir).join("constants.json"))
    });

    if let Some(path) = &dump_path {
        let pretty = serde_json::to_vec_pretty(&parsed.data).map_err(|source| ImportError::Parse { source })?;
        std::fs::write(path, &pretty).map_err(|source| ImportError::Write { path: path.clone(), source })?;
    }

    Ok(InstalledConstants { build: parsed.build, version: parsed.version.clone(), storage_path, dump_path })
}

#[cfg(test)]
mod tests {
    use super::ConstantsFit;
    use super::ImportError;
    use super::constants_fit;
    use super::install_constants;
    use super::read_constants_file;
    use serde_json::json;
    use wowsunpack::data::Version;

    fn version(major: u32, minor: u32) -> Version {
        Version { major, minor, patch: 0, build: std::num::NonZeroU32::new(12116141) }
    }

    #[test]
    fn a_matching_build_number_fits() {
        let constants = json!({ "VERSION": { "VERSION": "15.2", "BUILD": 12116141 } });
        assert_eq!(constants_fit(&constants, 12116141, Some(version(15, 2))), ConstantsFit::Exact);
    }

    #[test]
    fn a_different_build_number_does_not_fit() {
        let constants = json!({ "VERSION": { "VERSION": "15.2", "BUILD": 12116141 } });
        assert_eq!(constants_fit(&constants, 11965230, Some(version(15, 1))), ConstantsFit::Mismatched);
    }

    #[test]
    fn the_build_number_wins_over_a_matching_game_version() {
        // Same patch, different build (e.g. the China client): the file was
        // dumped for another build and its indices cannot be trusted here.
        let constants = json!({ "VERSION": { "VERSION": "15.2", "BUILD": 12116141 } });
        assert_eq!(constants_fit(&constants, 12116999, Some(version(15, 2))), ConstantsFit::Mismatched);
    }

    #[test]
    fn without_a_build_number_the_game_version_decides() {
        let constants = json!({ "VERSION": { "VERSION": "0.10.7" } });
        assert_eq!(constants_fit(&constants, 3747819, Some(version(0, 10))), ConstantsFit::Mismatched);

        let constants = json!({ "VERSION": { "VERSION": "15.2" } });
        assert_eq!(constants_fit(&constants, 12116141, Some(version(15, 2))), ConstantsFit::Exact);
        assert_eq!(constants_fit(&constants, 12116141, Some(version(15, 1))), ConstantsFit::Mismatched);
    }

    #[test]
    fn an_unknown_game_version_cannot_confirm_a_fit() {
        let constants = json!({ "VERSION": { "VERSION": "15.2" } });
        assert_eq!(constants_fit(&constants, 12116141, None), ConstantsFit::Mismatched);
    }

    #[test]
    fn constants_without_a_version_block_never_fit() {
        assert_eq!(constants_fit(&json!({}), 12116141, Some(version(15, 2))), ConstantsFit::Mismatched);
    }

    fn write_json(path: &std::path::Path, value: &serde_json::Value) {
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, serde_json::to_vec(value).unwrap()).unwrap();
    }

    fn sample_constants() -> serde_json::Value {
        json!({ "VERSION": { "VERSION": "15.2", "BUILD": 12116141 }, "SHIP_TYPES": {} })
    }

    /// A dump base with `builds.toml` naming one build directory, matching what
    /// `wows_data_mgr::builds::BuildsIndex::load` expects.
    fn dump_base_with_build(root: &std::path::Path, build: u32, dir: &str) -> std::path::PathBuf {
        let base = root.join("dumps");
        std::fs::create_dir_all(base.join(dir)).unwrap();
        std::fs::write(
            base.join("builds.toml"),
            format!(
                "[[builds]]\nbuild = {build}\ndir = \"{dir}\"\nversion = \"15.2.0\"\ndumped_at = \"2026-08-10T00:00:00Z\"\n"
            ),
        )
        .unwrap();
        base
    }

    #[test]
    fn reading_a_file_takes_its_build_and_version() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("constants.json");
        write_json(&path, &sample_constants());

        let parsed = read_constants_file(&path).expect("reads");
        assert_eq!(parsed.build, 12116141);
        assert_eq!(parsed.version.as_deref(), Some("15.2"));
    }

    #[test]
    fn a_file_without_a_build_number_is_rejected() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("constants.json");
        write_json(&path, &json!({ "VERSION": { "VERSION": "15.2" } }));

        assert!(matches!(read_constants_file(&path), Err(ImportError::MissingBuild)));
    }

    #[test]
    fn a_file_that_is_not_json_is_rejected() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("constants.json");
        std::fs::write(&path, b"not json at all").unwrap();

        assert!(matches!(read_constants_file(&path), Err(ImportError::Parse { .. })));
    }

    #[test]
    fn a_missing_file_reports_its_path() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("nope.json");

        match read_constants_file(&path) {
            Err(ImportError::Read { path: reported, .. }) => assert_eq!(reported, path),
            other => panic!("expected a read error, got {other:?}"),
        }
    }

    #[test]
    fn installing_writes_the_storage_copy_and_the_dump_copy() {
        let tmp = tempfile::tempdir().unwrap();
        let storage = tmp.path().join("storage");
        std::fs::create_dir_all(&storage).unwrap();
        let dump_base = dump_base_with_build(tmp.path(), 12116141, "15.2.0_12116141");
        let source = tmp.path().join("picked.json");
        write_json(&source, &sample_constants());
        let parsed = read_constants_file(&source).unwrap();

        let installed = install_constants(&parsed, Some(&storage), Some(&dump_base)).expect("installs");

        assert_eq!(installed.build, 12116141);
        assert_eq!(installed.storage_path, storage.join("constants_12116141.json"));
        assert_eq!(installed.dump_path, Some(dump_base.join("15.2.0_12116141").join("constants.json")));
        for path in [installed.storage_path.clone(), installed.dump_path.clone().unwrap()] {
            let written: serde_json::Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
            assert_eq!(written, sample_constants());
        }
    }

    #[test]
    fn installing_overwrites_an_existing_dump_copy() {
        let tmp = tempfile::tempdir().unwrap();
        let storage = tmp.path().join("storage");
        std::fs::create_dir_all(&storage).unwrap();
        let dump_base = dump_base_with_build(tmp.path(), 12116141, "15.2.0_12116141");
        let stale = dump_base.join("15.2.0_12116141").join("constants.json");
        write_json(&stale, &json!({ "VERSION": { "VERSION": "15.0", "BUILD": 11965230 } }));
        let source = tmp.path().join("picked.json");
        write_json(&source, &sample_constants());
        let parsed = read_constants_file(&source).unwrap();

        install_constants(&parsed, Some(&storage), Some(&dump_base)).expect("installs");

        let written: serde_json::Value = serde_json::from_slice(&std::fs::read(&stale).unwrap()).unwrap();
        assert_eq!(written, sample_constants());
    }

    #[test]
    fn installing_for_a_build_with_no_dump_writes_storage_only() {
        let tmp = tempfile::tempdir().unwrap();
        let storage = tmp.path().join("storage");
        std::fs::create_dir_all(&storage).unwrap();
        let dump_base = dump_base_with_build(tmp.path(), 11965230, "15.1.0_11965230");
        let source = tmp.path().join("picked.json");
        write_json(&source, &sample_constants());
        let parsed = read_constants_file(&source).unwrap();

        let installed = install_constants(&parsed, Some(&storage), Some(&dump_base)).expect("installs");

        assert_eq!(installed.dump_path, None);
        assert!(installed.storage_path.exists());
        assert!(!dump_base.join("15.1.0_11965230").join("constants.json").exists());
    }

    #[test]
    fn installing_without_a_storage_dir_fails() {
        let tmp = tempfile::tempdir().unwrap();
        let source = tmp.path().join("picked.json");
        write_json(&source, &sample_constants());
        let parsed = read_constants_file(&source).unwrap();

        assert!(matches!(install_constants(&parsed, None, None), Err(ImportError::NoStorageDir)));
    }
}
