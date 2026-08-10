//! Loading, judging, and installing the `constants.json` files that decode a
//! replay's server-provided battle results.

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

#[cfg(test)]
mod tests {
    use super::ConstantsFit;
    use super::constants_fit;
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
}
