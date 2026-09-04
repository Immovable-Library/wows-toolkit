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
use wows_replay_insights::fire_chance::geometry::angle_on_bow;
use wows_replay_insights::fire_chance::geometry::belt_strike_angle;
use wowsunpack::game_types::Vec3;
use wowsunpack::game_params::types::AmmoType;
use wowsunpack::game_params::types::GameParamProvider;
use wowsunpack::game_params::types::ShellInfo;

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
        let provider = ctx
            .metadata_provider(&report.version())
            .map_err(|e| report!("metadata provider {}: {e}", path.display()))?;
        write_event_stream(&report, provider.as_ref(), &mut sink).map_err(|e| report!("write {}: {e}", path.display()))?;
    }
    Ok(())
}

/// Write the `BattleReport` as newline-delimited JSON: one `meta` line with the
/// roster, then a line per salvo, then a line per resolved hit.
fn write_event_stream(report: &BattleReport, provider: &dyn GameParamProvider, w: &mut dyn Write) -> rootcause::Result<()> {
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
        let shell = hit
            .salvo
            .as_ref()
            .and_then(|salvo| provider.game_param_by_id(salvo.params_id))
            .map(|param| {
                let name = param.name().to_owned();
                param.projectile().map(|projectile| projectile.to_shell_info(name))
            })
            .flatten();
        let shell_obj = shell.as_ref().map(shell_to_json);
        let terminal_strike_deg = hit
            .hit
            .terminal_ballistics
            .as_ref()
            .map(|terminal| terminal.material_angle.to_degrees());
        let shot = hit
            .salvo
            .as_ref()
            .and_then(|salvo| salvo.shots.iter().find(|shot| shot.shot_id == hit.hit.shot_id));
        let (belt_strike_deg, angle_on_bow_deg) = match (shot, hit.victim_pose) {
            (Some(shot), Some(pose)) => {
                let impact = hit.hit.position.0;
                let origin = shot.origin.0;
                let incoming = Vec3::new(impact.x - origin.x, impact.y - origin.y, impact.z - origin.z);
                let belt = belt_strike_angle(incoming, pose.yaw, pose.pitch, pose.roll);
                let aob = angle_on_bow(origin, impact, pose.yaw, pose.pitch, pose.roll);
                (Some(belt), Some(aob))
            }
            _ => (None, None),
        };
        let strike_angle_deg = terminal_strike_deg.or(belt_strike_deg);
        let collision = hit.hit.hit_type.collision.known().map(|c| c.name()).unwrap_or("UNKNOWN");
        let shell_hit = hit.hit.hit_type.shell_hit.known().map(|s| s.name()).unwrap_or("UNKNOWN");
        writeln!(
            w,
            "{}",
            json!({
                "type": "hit",
                "data": detail,
                "shell": shell_obj,
                "strike_angle_deg": strike_angle_deg,
                "belt_strike_angle_deg": belt_strike_deg,
                "angle_on_bow_deg": angle_on_bow_deg,
                "collision": collision,
                "shell_hit": shell_hit,
            })
        )
        .map_err(|e| report!("write hit: {e}"))?;
    }
    Ok(())
}

fn shell_to_json(shell: &ShellInfo) -> serde_json::Value {
    let ammo_type = match &shell.ammo_type {
        AmmoType::AP => "AP",
        AmmoType::HE => "HE",
        AmmoType::SAP => "SAP",
        AmmoType::Unknown(other) => {
            // Escape unknown names: they are data, never interpolated.
            return json!({ "name": shell.name, "ammo_type": "Unknown", "unknown": other });
        }
    };
    json!({
        "name": shell.name,
        "ammo_type": ammo_type,
        "caliber_mm": shell.caliber.value(),
        "alpha_damage": shell.alpha_damage,
        "muzzle_velocity": shell.muzzle_velocity,
        "mass_kg": shell.mass_kg,
        "krupp": shell.krupp,
        "he_pen_mm": shell.he_pen_mm,
        "sap_pen_mm": shell.sap_pen_mm,
        "ricochet_angle": shell.ricochet_angle,
        "always_ricochet_angle": shell.always_ricochet_angle,
        "normalization": shell.normalization,
        "fuse_time": shell.fuse_time,
        "fuse_threshold": shell.fuse_threshold,
        "burn_prob": shell.burn_prob,
        "air_drag": shell.air_drag,
        "cap": shell.cap,
    })
}
