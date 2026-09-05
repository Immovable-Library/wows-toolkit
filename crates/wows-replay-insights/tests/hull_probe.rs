//! Real-data regression: the ship's armour-mesh bounding box must span the full
//! hull and give sensible length/beam once converted at 15 m/unit. Ignored:
//! needs an install. Run with `WOWS_DIR=D:/World_of_Warships`.
//!
//! This is the ground truth behind `hull_dim::hull_dim_from_geometry`: the
//! armour mesh is the whole hull (bow to stern), unlike the burn-node skeleton
//! extenders which only reach the mid-hull.

use std::path::PathBuf;

use wows_replay_insights::hull_dim;
use wowsunpack::export::ship::ShipAssets;
use wowsunpack::export::ship::ShipExportOptions;
use wowsunpack::game_params::provider::GameMetadataProvider;
use wowsunpack::game_params::types::GameParamProvider;
use wowsunpack::vfs::VfsPath;

fn game_dir() -> PathBuf {
    std::env::var_os("WOWS_DIR").map(PathBuf::from).unwrap_or_else(|| PathBuf::from(r"D:\World_of_Warships"))
}

fn game_vfs() -> VfsPath {
    wowsunpack::game_data::build_game_vfs(&game_dir()).expect("build game vfs")
}

#[test]
#[ignore = "requires a World of Warships install"]
fn probe_hull_bbox() {
    let dir = game_dir();
    if !dir.exists() {
        eprintln!("skipping: no WoWS install at {}", dir.display());
        return;
    }
    let vfs = game_vfs();
    let provider = GameMetadataProvider::from_vfs(&vfs).expect("provider");
    let assets = ShipAssets::from_vfs_with_metadata(&vfs, std::sync::Arc::new(provider)).expect("assets");

    let mut resolved = 0usize;
    for (ship, exp_len, exp_beam) in
        [("PASB018_Iowa_1944", 262.1, 32.97), ("PFSD110_Kleber", 141.0, 13.2)]
    {
        let Some(param) = assets.metadata().params().iter().find(|p| p.name() == ship) else {
            eprintln!("{ship}: not in GameParams; skipped");
            continue;
        };
        let Some(vehicle) = param.vehicle() else {
            eprintln!("{ship}: no vehicle; skipped");
            continue;
        };
        let model = match assets.load_ship_from_vehicle(vehicle, &ShipExportOptions::default()) {
            Ok(ctx) => ctx,
            Err(e) => {
                eprintln!("{ship}: load failed: {e}");
                continue;
            }
        };

        let mut dim: Option<hull_dim::HullDim> = None;
        let mut geom_count = 0usize;
        for bytes in model.hull_geom_bytes() {
            let Some(d) = hull_dim::hull_dim_from_geometry(bytes) else {
                continue;
            };
            geom_count += 1;
            dim = Some(match dim {
                None => d,
                Some(e) => hull_dim::HullDim {
                    length_m: e.length_m.max(d.length_m),
                    beam_m: e.beam_m.max(d.beam_m),
                    height_m: e.height_m.max(d.height_m),
                },
            });
        }
        let Some(dim) = dim else {
            eprintln!("{ship}: no armour geometry resolved; skipped");
            continue;
        };
        resolved += 1;
        eprintln!(
            "{ship}: length={:.1}m beam={:.1}m height={:.1}m (geom parts={geom_count})",
            dim.length_m, dim.beam_m, dim.height_m
        );
        assert!(
            (dim.length_m - exp_len).abs() < exp_len * 0.06,
            "{ship}: armour-mesh length {:.1}m too far from published {exp_len}m",
            dim.length_m
        );
        assert!(
            (dim.beam_m - exp_beam).abs() < exp_beam * 0.20,
            "{ship}: armour-mesh beam {:.1}m too far from published {exp_beam}m",
            dim.beam_m
        );
        assert!(dim.height_m > 8.0, "{ship}: implausibly short hull, height {:.1}m", dim.height_m);
    }
    assert!(resolved > 0, "no recognizable ship resolved: every ship name was missing or had no armour geometry");
}
