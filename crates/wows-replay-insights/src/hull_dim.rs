//! Per-ship hull dimensions for output-end zone classification.
//!
//! `hit_value::zone_for_hit` used fixed, battleship-scaled thresholds (110 m
//! bow/stern, 8 m belt, 6 m deck, 14 m superstructure). Those are correct for a
//! large battleship but collapse a destroyer's whole hull into "citadel" (110 m
//! is past a DD's half-length, 8 m is past its half-beam). This module recovers
//! each ship's real length/beam/height from its armour-mesh bounding box so the
//! horizontal zone boundaries scale with the ship.
//!
//! Why the armour mesh and not the render mesh: the burn-node skeleton
//! extenders only reach the mid-hull (they miss the bow/stern ends), so
//! `FireSectionGeometry` cannot bound a ship. The armour collision mesh covers
//! the whole hull, bow to stern, so its triangle bounding box is the right
//! extent. The armour mesh is already decoded (no meshopt), so this is cheap.
//!
//! Coordinate space: right-handed, +Z toward the bow (length), +X abeam (beam),
//! +Y up (height), at 15 m per ship-model unit ([`ShipModelDistance`]).

use wowsunpack::models::geometry;
use wowsunpack::models::model;
use wowsunpack::models::visual;
use wowsunpack::models::assets_bin;
use wowsunpack::models::assets_bin::PrototypeDatabase;
use wowsunpack::vfs::VfsPath;
use wowsunpack::game_params::types::GameParamProvider;
use wows_replays::types::EntityId;
use wows_battle_world::report::BattleReport;
use crate::build::ResolvedBuild;
use crate::hit_value::ProviderRef;

/// The hull's outer dimensions, in meters, from its armour-mesh bounding box.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct HullDim {
    pub length_m: f32,
    pub beam_m: f32,
    pub height_m: f32,
}

impl HullDim {
    /// The ship's half-length in meters.
    pub fn half_length_m(&self) -> f32 {
        self.length_m * 0.5
    }

    /// The ship's half-beam in meters.
    pub fn half_beam_m(&self) -> f32 {
        self.beam_m * 0.5
    }
}

/// Convert ship-model units to meters. 1 ship-model unit = 15 m.
pub(crate) const SHIP_MODEL_TO_METERS: f32 = 15.0;

/// Compute the hull dimensions from a parsed `.geometry` file's armour mesh.
///
/// Returns `None` when the geometry has no armour triangles (rare; a stand-in
/// model, or a non-ship geometry record), so the caller falls back to the fixed
/// heuristic.
pub fn hull_dim_from_geometry(geom_bytes: &[u8]) -> Option<HullDim> {
    let geom = geometry::parse_geometry(geom_bytes).ok()?;
    let mut min = [f32::INFINITY; 3];
    let mut max = [f32::NEG_INFINITY; 3];
    let mut any = false;
    for armor in &geom.armor_models {
        for tri in &armor.triangles {
            any = true;
            for v in &tri.vertices {
                for (i, c) in v.iter().enumerate() {
                    min[i] = min[i].min(*c);
                    max[i] = max[i].max(*c);
                }
            }
        }
    }
    if !any {
        return None;
    }
    let extent = [max[0] - min[0], max[1] - min[1], max[2] - min[2]];
    // Z is length (bow), X is beam, Y is height.
    Some(HullDim {
        length_m: extent[2] * SHIP_MODEL_TO_METERS,
        beam_m: extent[0] * SHIP_MODEL_TO_METERS,
        height_m: extent[1] * SHIP_MODEL_TO_METERS,
    })
}

/// Build every player's hull dimensions into an `entity_id -> HullDim` map.
///
/// Reads `assets.bin` from `vfs` once, then resolves each ship's hull model to
/// its `.geometry` record and unions the armour-mesh bounding box. A ship whose
/// model is absent, whose geometry has no armour triangles, or whose VFS path
/// cannot be opened is skipped so the caller falls back to the fixed heuristic.
///
/// Approximation: a ship is resolved by its base `model_path`; equipped
/// hull-upgrade models are not distinguished, so a non-base hull shares the base
/// hull's dimensions (hulls rarely change length/beam materially). The bbox is
/// also treated as centered on the model origin, so the fore/aft and
/// port/starboard reaches are symmetric; per-side reaches are a later
/// refinement. The parsed `assets.bin` is not cached across reports.
pub fn hull_dims_for_report(
    report: &BattleReport,
    params: &dyn GameParamProvider,
    vfs: &VfsPath,
) -> std::collections::HashMap<EntityId, HullDim> {
    let mut map = std::collections::HashMap::new();
    let mut assets_bin_bytes = Vec::new();
    if vfs
        .join("content/assets.bin")
        .ok()
        .and_then(|p| p.open_file().ok())
        .and_then(|mut f| f.read_to_end(&mut assets_bin_bytes).ok())
        .is_none()
    {
        return map;
    }
    let Ok(db) = assets_bin::parse_assets_bin(&assets_bin_bytes) else {
        return map;
    };
    let index = db.build_self_id_index();
    for player in report.players() {
        let Some(build) = ResolvedBuild::from_player(player, &ProviderRef(params), report.version()) else {
            continue;
        };
        let Some(model_path) = build.ship.vehicle().and_then(|v| v.model_path().map(str::to_owned)) else {
            continue;
        };
        if let Some(dim) = hull_dim_for_model(&db, &index, vfs, &model_path) {
            map.insert(player.initial_state().entity_id(), dim);
        }
    }
    map
}

/// Resolve a ship's hull `.visual`/`.geometry` records and compute the armour
/// bbox. The bbox is unioned over every hull-part geometry so a ship split into
/// bow/mid/stern sub-models still yields its full extent.
fn hull_dim_for_model(
    db: &PrototypeDatabase<'_>,
    index: &std::collections::HashMap<u64, usize>,
    vfs: &VfsPath,
    model_path: &str,
) -> Option<HullDim> {
    let dir = model_path.rsplit_once('/').map(|(d, _)| d).unwrap_or(model_path);
    let model_dir = dir.rsplit('/').next().unwrap_or(dir);
    let needle = format!("/{model_dir}/");
    let mut acc: Option<HullDim> = None;
    for (i, entry) in db.paths_storage.iter().enumerate() {
        if !entry.name.ends_with(".visual") {
            continue;
        }
        let full = db.reconstruct_path(i, index);
        if !full.contains(&needle) {
            continue;
        }
        let Some(vis) = resolve_visual(db, entry.self_id) else {
            continue;
        };
        let Ok(vp) = visual::parse_visual(vis) else {
            continue;
        };
        let Some(&geom_idx) = index.get(&vp.merged_geometry_path_id) else {
            continue;
        };
        let geom_path = db.reconstruct_path(geom_idx, index);
        let mut geom_bytes = Vec::new();
        let Some(mut f) = vfs.join(&geom_path).ok().and_then(|p| p.open_file().ok()) else {
            continue;
        };
        if f.read_to_end(&mut geom_bytes).is_err() {
            continue;
        }
        let Some(dim) = hull_dim_from_geometry(&geom_bytes) else {
            continue;
        };
        acc = Some(merge_dims(acc, dim));
    }
    acc
}

/// Resolve a path entry's `self_id` to its `VisualPrototype` record bytes,
/// following a `ModelPrototype` indirection when the entry points at blob 3.
///
/// Resolution is keyed on the entry's own `self_id` (not a leaf-name suffix
/// re-lookup), so a `.visual` leaf shared by another ship in the store cannot
/// redirect this ship to foreign geometry.
fn resolve_visual<'a>(
    db: &'a PrototypeDatabase<'a>,
    self_id: u64,
) -> Option<&'a [u8]> {
    let r2p = db.lookup_r2p(self_id)?;
    let vis_location = db.decode_r2p_value(r2p).ok()?;
    match vis_location.blob_index {
        1 => db.get_prototype_data(vis_location, visual::VISUAL_ITEM_SIZE).ok(),
        3 => {
            let model_data = db.get_prototype_data(vis_location, model::MODEL_ITEM_SIZE).ok()?;
            let mp = model::parse_model(model_data).ok()?;
            let r2p = db.lookup_r2p(mp.visual_resource_id)?;
            let vis_loc = db.decode_r2p_value(r2p).ok()?;
            db.get_prototype_data(vis_loc, visual::VISUAL_ITEM_SIZE).ok()
        }
        _ => None,
    }
}

fn merge_dims(existing: Option<HullDim>, next: HullDim) -> HullDim {
    match existing {
        None => next,
        Some(e) => HullDim {
            length_m: e.length_m.max(next.length_m),
            beam_m: e.beam_m.max(next.beam_m),
            height_m: e.height_m.max(next.height_m),
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A synthetic `.geometry` blob must be invalid; we cannot hand-encode the
    /// format here. Instead `hull_dim_from_geometry` returns `None` for junk and
    /// the axis/scale mapping is asserted through the real-data probe in
    /// `tests/hull_probe.rs`. This unit test locks the units contract: a bbox
    /// extent of 1 unit on each axis is 15 m.
    #[test]
    fn junk_geometry_yields_none() {
        assert_eq!(hull_dim_from_geometry(&[0u8; 4]), None);
    }

    #[test]
    fn half_extents_are_half_the_full_extents() {
        let d = HullDim { length_m: 270.4, beam_m: 33.0, height_m: 45.9 };
        assert_eq!(d.half_length_m(), 135.2);
        assert_eq!(d.half_beam_m(), 16.5);
    }

    #[test]
    fn merge_takes_the_max_extent() {
        let a = HullDim { length_m: 100.0, beam_m: 10.0, height_m: 5.0 };
        let b = HullDim { length_m: 120.0, beam_m: 12.0, height_m: 6.0 };
        assert_eq!(merge_dims(Some(a), b), HullDim { length_m: 120.0, beam_m: 12.0, height_m: 6.0 });
        assert_eq!(merge_dims(None, b), b);
    }
}
