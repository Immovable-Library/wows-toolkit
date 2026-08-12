use std::collections::BTreeMap;
use std::path::Path;

use rootcause::prelude::*;
use serde::Deserialize;
use serde::Deserializer;
use serde::Serialize;
use serde::Serializer;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DepotId(pub u32);

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ManifestId(pub String);

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DepotManifest {
    pub depot_id: DepotId,
    pub manifest_id: ManifestId,
}

impl DepotManifest {
    pub fn new(depot_id: DepotId, manifest_id: ManifestId) -> Self {
        Self { depot_id, manifest_id }
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct GameVersionManifest {
    #[serde(default)]
    pub versions: BTreeMap<String, GameVersionEntry>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GameVersionEntry {
    pub version: String,
    pub client: DepotManifest,
    pub content: Option<DepotManifest>,
    pub localization: Option<DepotManifest>,
}

#[derive(Serialize, Deserialize)]
struct FlatGameVersionEntry {
    version: String,
    client_depot_id: DepotId,
    client_manifest_id: ManifestId,
    #[serde(skip_serializing_if = "Option::is_none")]
    content_depot_id: Option<DepotId>,
    #[serde(skip_serializing_if = "Option::is_none")]
    content_manifest_id: Option<ManifestId>,
    #[serde(skip_serializing_if = "Option::is_none")]
    localization_depot_id: Option<DepotId>,
    #[serde(skip_serializing_if = "Option::is_none")]
    localization_manifest_id: Option<ManifestId>,
}

impl<'de> Deserialize<'de> for GameVersionEntry {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let flat = FlatGameVersionEntry::deserialize(deserializer)?;
        let content = depot_manifest_from_pair(flat.content_depot_id, flat.content_manifest_id, "content")?;
        let localization =
            depot_manifest_from_pair(flat.localization_depot_id, flat.localization_manifest_id, "localization")?;

        Ok(Self {
            version: flat.version,
            client: DepotManifest::new(flat.client_depot_id, flat.client_manifest_id),
            content,
            localization,
        })
    }
}

impl Serialize for GameVersionEntry {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let (content_depot_id, content_manifest_id) = match &self.content {
            Some(manifest) => (Some(manifest.depot_id.clone()), Some(manifest.manifest_id.clone())),
            None => (None, None),
        };
        let (localization_depot_id, localization_manifest_id) = match &self.localization {
            Some(manifest) => (Some(manifest.depot_id.clone()), Some(manifest.manifest_id.clone())),
            None => (None, None),
        };

        FlatGameVersionEntry {
            version: self.version.clone(),
            client_depot_id: self.client.depot_id.clone(),
            client_manifest_id: self.client.manifest_id.clone(),
            content_depot_id,
            content_manifest_id,
            localization_depot_id,
            localization_manifest_id,
        }
        .serialize(serializer)
    }
}

fn depot_manifest_from_pair<E>(
    depot_id: Option<DepotId>,
    manifest_id: Option<ManifestId>,
    depot_name: &str,
) -> Result<Option<DepotManifest>, E>
where
    E: serde::de::Error,
{
    match (depot_id, manifest_id) {
        (Some(depot_id), Some(manifest_id)) => Ok(Some(DepotManifest::new(depot_id, manifest_id))),
        (None, None) => Ok(None),
        (Some(_), None) => Err(E::custom(format!("{depot_name}_manifest_id is required"))),
        (None, Some(_)) => Err(E::custom(format!("{depot_name}_depot_id is required"))),
    }
}

impl GameVersionManifest {
    /// Returns the highest build number in the manifest.
    pub fn latest_build(&self) -> Option<u32> {
        self.versions.keys().filter_map(|k| k.parse::<u32>().ok()).max()
    }

    /// Look up a build number by version string (supports shorthand like "15.1").
    /// When multiple builds match, returns the highest.
    pub fn find_by_version(&self, query: &str) -> Option<u32> {
        let mut matched: Vec<u32> = self
            .versions
            .iter()
            .filter(|(_, entry)| version_matches(&entry.version, query))
            .filter_map(|(k, _)| k.parse::<u32>().ok())
            .collect();
        matched.sort();
        matched.last().copied()
    }

    /// Get a manifest entry by build number.
    pub fn get(&self, build: u32) -> Option<&GameVersionEntry> {
        self.versions.get(&build.to_string())
    }
}

/// Check if a full version string matches a possibly-shorthand query.
/// "15.1.0" matches "15.1", "15.1.0", and "15".
pub fn version_matches(full: &str, query: &str) -> bool {
    let full_parts: Vec<&str> = full.split('.').collect();
    let query_parts: Vec<&str> = query.split('.').collect();

    if query_parts.len() > full_parts.len() {
        return false;
    }

    full_parts.iter().zip(query_parts.iter()).all(|(f, q)| f == q)
}

pub fn load_manifest(path: &Path) -> Result<GameVersionManifest, Report> {
    if !path.exists() {
        return Ok(GameVersionManifest { versions: BTreeMap::new() });
    }
    let content = std::fs::read_to_string(path).attach_with(|| format!("Failed to read {}", path.display()))?;
    let manifest: GameVersionManifest =
        toml::from_str(&content).map_err(|e| rootcause::report!("Failed to parse {}: {e}", path.display()))?;
    Ok(manifest)
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn version_matches_exact() {
        assert!(version_matches("15.1.0", "15.1.0"));
    }

    #[test]
    fn version_matches_shorthand_two() {
        assert!(version_matches("15.1.0", "15.1"));
    }

    #[test]
    fn version_matches_shorthand_one() {
        assert!(version_matches("15.1.0", "15"));
    }

    #[test]
    fn version_no_match() {
        assert!(!version_matches("15.1.0", "14.1"));
    }

    #[test]
    fn version_query_longer() {
        assert!(!version_matches("15.1", "15.1.0"));
    }

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

    #[test]
    fn parses_client_only_depot_manifest() {
        let manifest: GameVersionManifest = toml::from_str(
            r#"
            [versions.13015711]
            version = "15.7.0"
            client_depot_id = 552993
            client_manifest_id = "client"
            "#,
        )
        .unwrap();

        let entry = manifest.get(13015711).unwrap();
        assert_eq!(entry.client, DepotManifest::new(DepotId(552993), ManifestId("client".into())));
        assert_eq!(entry.content, None);
        assert_eq!(entry.localization, None);
    }

    #[test]
    fn rejects_incomplete_content_depot_manifest() {
        let error = toml::from_str::<GameVersionManifest>(
            r#"
            [versions.13015711]
            version = "15.7.0"
            client_depot_id = 552993
            client_manifest_id = "client"
            content_depot_id = 552991
            "#,
        )
        .unwrap_err();

        assert!(error.to_string().contains("content"));
    }

    #[test]
    fn serializes_split_depot_manifests_to_flat_schema() {
        let mut versions = BTreeMap::new();
        versions.insert(
            "13015711".to_string(),
            GameVersionEntry {
                version: "15.7.0".to_string(),
                client: DepotManifest::new(DepotId(552993), ManifestId("client".to_string())),
                content: Some(DepotManifest::new(DepotId(552991), ManifestId("content".to_string()))),
                localization: Some(DepotManifest::new(DepotId(552994), ManifestId("localization".to_string()))),
            },
        );

        let serialized = toml::to_string(&GameVersionManifest { versions }).unwrap();

        assert!(serialized.contains("client_depot_id = 552993"));
        assert!(serialized.contains("client_manifest_id = \"client\""));
        assert!(serialized.contains("content_depot_id = 552991"));
        assert!(serialized.contains("content_manifest_id = \"content\""));
        assert!(serialized.contains("localization_depot_id = 552994"));
        assert!(serialized.contains("localization_manifest_id = \"localization\""));
        assert!(!serialized.contains("[versions.13015711.client]"));
    }

    #[test]
    fn find_by_version_picks_highest() {
        let mut versions = BTreeMap::new();
        versions.insert(
            "11791718".to_string(),
            GameVersionEntry {
                version: "15.0.0".to_string(),
                client: DepotManifest::new(DepotId(552991), ManifestId("aaa".to_string())),
                content: None,
                localization: None,
            },
        );
        versions.insert(
            "11965230".to_string(),
            GameVersionEntry {
                version: "15.1.0".to_string(),
                client: DepotManifest::new(DepotId(552991), ManifestId("bbb".to_string())),
                content: None,
                localization: None,
            },
        );
        let manifest = GameVersionManifest { versions };

        assert_eq!(manifest.find_by_version("15"), Some(11965230));
        assert_eq!(manifest.find_by_version("15.1"), Some(11965230));
        assert_eq!(manifest.find_by_version("15.0"), Some(11791718));
        assert_eq!(manifest.find_by_version("14"), None);
    }
}
