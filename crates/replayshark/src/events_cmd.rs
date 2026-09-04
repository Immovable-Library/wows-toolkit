//! `events` command: export a per-match event stream as JSONL.
//!
//! Drives each replay through `battle_report_for` with salvo and hit history
//! recording enabled, then writes one JSON object per line: a `meta` roster
//! (entity id -> player) and one `salvo` row per battery salvo, plus a `hit`
//! row per resolved projectile hit. Downstream analysis (aiming, dispersion,
//! target selection) consumes these rows. Positions and damage attribution are
//! surfaced by later milestones; this command deliberately stops at what the
//! report exposes today.

use std::fs::File;
use std::io::Write;
use std::path::PathBuf;

use rootcause::prelude::*;
use rootcause::Result;
use serde_json::json;
use wows_battle_world::ids::ShotTracking;
use wows_battle_world::process::battle_report_for;
use wows_battle_world::process::ProcessOptions;
use wows_battle_world::report::BattleReport;
use wows_replays::context::GameDataContext;
use wows_replays::ReplayFile;

/// Expand any directory arguments into their `.wowsreplay` files, preserving
/// argument order and skipping non-replay siblings.
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

pub fn run(ctx: &dyn GameDataContext, inputs: Vec<PathBuf>, out: Option<PathBuf>) -> Result<()> {
    let replays = expand_inputs(&inputs)?;
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
        };
        let report = match battle_report_for(&replay_file, ctx, options) {
            Ok(report) => report,
            Err(e) => return Err(report!("process {}: {e}", path.display())),
        };
        write_event_stream(&report, &mut sink).map_err(|e| report!("write {}: {e}", path.display()))?;
    }
    Ok(())
}

/// Write the `BattleReport` as newline-delimited JSON: one `meta` line with the
/// roster, then a line per salvo, then a line per resolved hit.
fn write_event_stream(report: &BattleReport, w: &mut dyn Write) -> rootcause::Result<()> {
    let self_entity = report.self_player().initial_state().entity_id().raw();
    let roster = report
        .players()
        .iter()
        .map(|p| {
            let state = p.initial_state();
            let entity = state.entity_id().raw();
            json!({ "entity_id": entity, "name": state.username(), "is_self": entity == self_entity })
        })
        .collect::<Vec<_>>();
    writeln!(w, "{}", json!({ "type": "meta", "players": roster })).map_err(|e| report!("write meta: {e}"))?;

    for salvo in report.salvos() {
        let row = json!({
            "type": "salvo",
            "clock": salvo.clock.0,
            "owner": salvo.owner_id.raw(),
            "params_id": salvo.params_id.raw(),
            "salvo_id": salvo.salvo_id,
            "first_shot": salvo.first_shot.map(|id| id.raw()),
            "shots": salvo.shots,
        });
        writeln!(w, "{}", row).map_err(|e| report!("write salvo: {e}"))?;
    }

    for hit in report.hit_history() {
        let detail = serde_json::to_value(hit).map_err(|e| report!("serialize hit: {e}"))?;
        writeln!(w, "{}", json!({ "type": "hit", "data": detail })).map_err(|e| report!("write hit: {e}"))?;
    }
    Ok(())
}
