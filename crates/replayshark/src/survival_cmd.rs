//! `survival` command: S1 survival profile for the recording player, as JSONL
//! (default) or a human-readable text report (`--text`).

use std::fs::File;
use std::io::Write;
use std::path::PathBuf;

use rootcause::prelude::*;
use rootcause::Result;
use wows_battle_world::ids::ShotTracking;
use wows_battle_world::process::battle_report_for;
use wows_battle_world::process::ProcessOptions;
use wows_replay_insights::hit_value;
use wows_replay_insights::survival;
use wows_replays::context::GameDataContext;
use wows_replays::ReplayFile;

/// Install the runtime ship-name table (id -> Chinese) from a JSON map.
fn load_ship_names(path: Option<&std::path::Path>) -> Result<()> {
    let Some(path) = path else { return Ok(()) };
    let text = std::fs::read_to_string(path).map_err(|e| report!("read {}: {e}", path.display()))?;
    let map: std::collections::HashMap<String, String> =
        serde_json::from_str(&text).map_err(|e| report!("parse {}: {e}", path.display()))?;
    hit_value::set_ship_names(map);
    Ok(())
}

/// Expand directory arguments into their `.wowsreplay` files.
fn expand_inputs(inputs: &[PathBuf]) -> Result<Vec<PathBuf>> {
    let mut out = Vec::new();
    for input in inputs {
        if input.is_dir() {
            for entry in walkdir::WalkDir::new(input) {
                let entry = entry.map_err(|e| report!("walk {}: {e}", input.display()))?;
                let path = entry.path();
                if path.is_file() && path.extension().is_some_and(|ext| ext == "wowsreplay") {
                    out.push(path.to_path_buf());
                }
            }
        } else {
            out.push(input.clone());
        }
    }
    Ok(out)
}

pub fn run(
    ctx: &dyn GameDataContext,
    inputs: Vec<PathBuf>,
    out: Option<PathBuf>,
    ship_names: Option<PathBuf>,
    text: bool,
    dims: Vec<survival::SurvivalDimension>,
) -> Result<()> {
    let replays = expand_inputs(&inputs)?;
    load_ship_names(ship_names.as_deref())?;
    let mut sink: Box<dyn Write> = match &out {
        Some(path) => Box::new(File::create(path).map_err(|e| report!("create {}: {e}", path.display()))?),
        None => Box::new(std::io::stdout()),
    };

    for path in &replays {
        let replay_file =
            ReplayFile::from_file(path).map_err(|e| report!("read replay {}: {e:?}", path.display()))?;
        let options = ProcessOptions {
            shot_tracking: ShotTracking::Tracked,
            record_hit_history: true,
            record_salvo_history: true,
            record_position_history: true,
            record_health_history: true,
        };
        let report = match battle_report_for(&replay_file, ctx, options) {
            Ok(report) => report,
            Err(e) => return Err(report!("process {}: {e}", path.display())),
        };
        let provider = ctx
            .metadata_provider(&report.version())
            .map_err(|e| report!("metadata provider {}: {e}", path.display()))?;
        if text {
            let text = survival::render(&report, provider.as_ref());
            write!(sink, "{text}").map_err(|e| report!("write report: {e}"))?;
        } else {
            let report = survival::assess_report(&report, provider.as_ref(), &dims);
            let row = serde_json::to_string(&report).map_err(|e| report!("serialize report: {e}"))?;
            writeln!(sink, "{row}").map_err(|e| report!("write report: {e}"))?;
        }
    }
    Ok(())
}
