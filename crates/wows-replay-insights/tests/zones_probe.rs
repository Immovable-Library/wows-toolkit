//! Probe: how do `.splash` SplashBoxes map to `HitLocation` zones, and do they
//! cover the hull? Ignored: needs an install. Run with
//! `WOWS_DIR=D:/World_of_Warships`.

use std::path::PathBuf;

use wowsunpack::export::ship::ShipAssets;
use wowsunpack::export::ship::ShipExportOptions;
use wowsunpack::game_params::provider::GameMetadataProvider;
use wowsunpack::game_params::types::GameParamProvider;
use wowsunpack::models::geometry;
use wowsunpack::vfs::VfsPath;

fn game_dir() -> PathBuf {
    std::env::var_os("WOWS_DIR").map(PathBuf::from).unwrap_or_else(|| PathBuf::from(r"D:\World_of_Warships"))
}

fn game_vfs() -> VfsPath {
    wowsunpack::game_data::build_game_vfs(&game_dir()).expect("build game vfs")
}

#[test]
#[ignore = "requires a World of Warships install"]
fn probe_splash_zones() {
    let dir = game_dir();
    if !dir.exists() {
        eprintln!("skipping: no WoWS install at {}", dir.display());
        return;
    }
    let vfs = game_vfs();
    let provider = GameMetadataProvider::from_vfs(&vfs).expect("provider");
    let assets = ShipAssets::from_vfs_with_metadata(&vfs, std::sync::Arc::new(provider)).expect("assets");

    for ship in ["PASB018_Iowa_1944", "PFSD110_Kleber"] {
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

        if let Some(hl) = model.hit_locations() {
            eprintln!("{ship} hit_locations ({}):", hl.len());
            let mut keys: Vec<_> = hl.keys().collect();
            keys.sort();
            for k in keys {
                let h = &hl[k];
                eprintln!("  {k}: thickness={}maxhp={} splash={:?}", h.thickness(), h.max_hp(), h.splash_boxes());
            }
        }

        if let Some(splash_bytes) = model.hull_splash_bytes() {
            match geometry::parse_splash_file(splash_bytes) {
                Ok(boxes) => {
                    eprintln!("{ship} splash boxes ({}):", boxes.len());
                    for b in &boxes {
                        eprintln!("  {} min={:?} max={:?}", b.name, b.min, b.max);
                    }
                    assert!(!boxes.is_empty(), "{ship}: no splash boxes");
                    let missing = boxes.iter().filter(|b| {
                        model
                            .hit_locations()
                            .is_some_and(|hl| !hl.values().any(|loc| loc.splash_boxes().contains(&b.name)))
                    }).count();
                    assert!(
                        missing < boxes.len(),
                        "{ship}: every splash box is unmapped to a hit-location zone"
                    );
                }
                Err(e) => eprintln!("{ship}: splash parse failed: {e}"),
            }
        } else {
            eprintln!("{ship}: no hull splash bytes");
        }
    }
}
