//! M2: single-shot hit-value assessment.
//!
//! For each main-battery shell the recording player landed, rebuild the "why":
//! what shell type was fired (AP/HE/SAP, only two per ship), what the game
//! reported it did, the target's angle to the shot, and whether the ship's
//! other shell type would have landed more damage at its best-aim zone.
//!
//! The penetration verdicts use the community wows_shell model (see
//! `wowsunpack::ballistics`) and are an approximation, never a client-exact value.

use std::collections::HashMap;
use std::collections::HashSet;
use std::sync::OnceLock;

use wows_battle_world::report::BattleReport;
use wows_replays::analyzer::battle_controller::state::ResolvedShotHit;
use wows_replays::types::EntityId;
use wowsunpack::ballistics::ShellParams;
use wowsunpack::ballistics::solve_for_range;
use wowsunpack::game_params::types::AmmoType;
use wowsunpack::game_params::types::GameParamProvider;
use wowsunpack::game_params::types::Meters;
use wowsunpack::game_params::types::Param;
use wowsunpack::game_params::types::ShellInfo;
use wowsunpack::game_params::types::Species;
use wowsunpack::game_params::ttx::armor_materials::collision_material_name;
use wowsunpack::game_params::ttx::components::ArtilleryGunStats;
use wowsunpack::game_types::Vec3;
use wowsunpack::Rc;

use crate::build::ResolvedBuild;
use crate::fire_chance::geometry::angle_on_bow;
use crate::fire_chance::geometry::belt_strike_angle;
use crate::fire_chance::geometry::world_offset_to_body;
use crate::hull_dim::HullData;
use crate::hull_dim::exact_zone_for_hit;

/// Runtime-loaded local Chinese ship-name table, keyed by numeric ship id.
/// `set_ship_names` installs it once from the skill's `ship_names.json`; the
/// embedded `exact_zh`/`latin_zh` tables are the fallback when it is absent.
static SHIP_NAMES: OnceLock<HashMap<String, String>> = OnceLock::new();

/// Install the local ship-name table (id -> Chinese name). First call wins.
pub fn set_ship_names(map: HashMap<String, String>) {
    let _ = SHIP_NAMES.set(map);
}

/// The verdict for one resolved hit.
#[cfg_attr(feature = "serde", derive(serde::Serialize))]
#[derive(Clone, Debug)]
pub struct HitAssessment {
    pub victim_entity_id: EntityId,
    pub victim_ship: String,
    pub victim_class: String,
    pub zone: String,
    pub ammo_used: String,
    pub ammo_other: String,
    pub alpha_damage: f32,
    pub strike_angle_deg: f32,
    pub angle_on_bow_deg: f32,
    pub hit_type: String,
    pub pen_verdict: String,
    pub swap_text: String,
    /// Whether the struck zone is already saturated (damage absorbed).
    pub saturated: bool,
    /// Damage already absorbed by the struck zone before this hit.
    pub zone_damage_so_far: f32,
    /// The ship's main-battery reload in seconds, for the ammo-switch-window note.
    pub reload_s: Option<f32>,
    /// Aim-off target along the victim's course (positive = over-led, negative
    /// = under-led), in meters. Approximate: couples with shell dispersion.
    pub lead_error_m: Option<f32>,
    /// Aim-off the victim's course line (lateral), in meters.
    pub lead_off_axis_m: Option<f32>,
    /// The originating salvo id (server side), for per-volley grouping.
    pub salvo_id: u32,
    /// The salvo's first shell shot id (its discriminator, per the SalvoEvent
    /// contract) that together with `salvo_id` uniquely identifies a volley.
    pub first_shot: Option<u32>,
    /// Game clock of the hit.
    pub clock: f32,
    /// Estimated damage this shell applied to its zone.
    pub estimated_damage: f32,
    /// Human hit-effect name (ribbon): 过穿/未击穿/核心/跳弹/命中.
    pub ribbon: String,
    /// Why this effect occurred (target angle, zone thickness, ammo choice).
    pub reason: String,
}

/// Result of the single-shot output assessment, including how many
/// self-fired-on-enemy hits could not be assessed (no victim, no shell, not a
/// main-battery shell, missing pose/origin, or an unrecognized shell-hit type).
/// A non-zero `excluded` with empty `assessments` means "no usable data", not
/// "the player landed nothing".
#[derive(Clone, Debug)]
pub struct AssessOutcome {
    pub assessments: Vec<HitAssessment>,
    pub excluded: u32,
}

/// A concise per-target lesson, aggregated from the per-hit assessments.
#[cfg_attr(feature = "serde", derive(serde::Serialize))]
#[derive(Clone, Debug)]
pub struct VictimLesson {
    pub victim_entity_id: EntityId,
    pub victim_ship: String,
    pub victim_class: String,
    /// Number of landed hits on this victim. Shot-accounting per victim (the
    /// count of shells aimed at it) is not derivable from the hit history, so
    /// this is the landed-hit count, kept for report compatibility.
    pub shells_fired: u32,
    pub hits: u32,
    pub overpen: u32,
    pub bounce: u32,
    pub no_pen: u32,
    pub citadel: u32,
    pub switch_calls: u32,
    pub keep_calls: u32,
    pub saturated_hits: u32,
    pub avg_lead_error_m: Option<f32>,
    pub advice: String,
}

/// Aggregate the per-hit assessments into a per-target lesson.
pub fn summarize(
    report: &BattleReport,
    params: &dyn GameParamProvider,
    hull: Option<&HashMap<EntityId, HullData>>,
) -> Vec<VictimLesson> {
    use std::collections::BTreeMap;
    // Group by entity id so two ships that share a display name and class
    // (common in PvE fleets) do not merge into one lesson.
    let mut groups: BTreeMap<EntityId, Vec<&HitAssessment>> = BTreeMap::new();
    let all = assess(report, params, hull).assessments;
    for hit in &all {
        groups
            .entry(hit.victim_entity_id)
            .or_default()
            .push(hit);
    }

    groups
        .into_iter()
        .map(|(victim_entity_id, hits)| {
            let victim_ship = hits.first().map(|h| h.victim_ship.clone()).unwrap_or_default();
            let victim_class = hits.first().map(|h| h.victim_class.clone()).unwrap_or_default();
            let shells_fired = hits.len() as u32;
            let overpen = hits.iter().filter(|h| h.hit_type.contains("OVERPEN")).count() as u32;
            let bounce = hits.iter().filter(|h| h.hit_type.contains("RICOCHET")).count() as u32;
            let no_pen = hits.iter().filter(|h| h.hit_type.contains("NOPENETRATION")).count() as u32;
            let citadel = hits.iter().filter(|h| h.hit_type.contains("MAJORHIT")).count() as u32;
            let switch_calls = hits.iter().filter(|h| h.swap_text.starts_with("switch")).count() as u32;
            let keep_calls = hits.iter().filter(|h| h.swap_text.starts_with("keep")).count() as u32;
            let saturated_hits = hits.iter().filter(|h| h.saturated).count() as u32;
            let leads: Vec<f32> = hits.iter().filter_map(|h| h.lead_error_m).collect();
            let avg_lead = if leads.is_empty() {
                None
            } else {
                Some(leads.iter().sum::<f32>() / leads.len() as f32)
            };
            let advice = build_lesson(
                &victim_class,
                shells_fired,
                &hits,
                overpen,
                bounce,
                no_pen,
                citadel,
                saturated_hits,
                avg_lead,
            );
            VictimLesson {
                victim_entity_id,
                victim_ship,
                victim_class,
                shells_fired,
                hits: hits.len() as u32,
                overpen,
                bounce,
                no_pen,
                citadel,
                switch_calls,
                keep_calls,
                saturated_hits,
                avg_lead_error_m: avg_lead,
                advice,
            }
        })
        .collect()
}

fn build_lesson(
    victim_class: &str,
    shells_fired: u32,
    hits: &[&HitAssessment],
    overpen: u32,
    bounce: u32,
    no_pen: u32,
    citadel: u32,
    saturated_hits: u32,
    avg_lead: Option<f32>,
) -> String {
    let is_thin = matches!(victim_class, "destroyer" | "carrier");
    let mut parts: Vec<String> = Vec::new();
    if overpen >= 2 && is_thin {
        let used_ammo = hits.first().map(|h| h.ammo_used.as_str()).unwrap_or("?");
        let other_ammo = hits.first().map(|h| h.ammo_other.as_str()).unwrap_or("?");
        if used_ammo == "AP" && other_ammo == "HE" {
            parts.push(format!("{overpen}发 AP 过穿薄甲目标（DD/航母），应切 HE（视切弹窗口）"));
        } else if used_ammo == "AP" {
            parts.push(format!("{overpen}发 AP 过穿薄甲目标（DD/航母），无 HE 可切，改打厚区"));
        } else {
            parts.push(format!("{overpen}发过穿薄甲目标（DD/航母）"));
        }
    }
    if bounce >= 2 {
        parts.push(format!("{bounce}发跳弹，目标角度/穿深问题，考虑 HE 或等露侧"));
    }
    if no_pen >= 2 && !is_thin {
        parts.push(format!("{no_pen}发未击穿，穿深/角度不足，HE 溅射更稳"));
    }
    if citadel >= 1 {
        parts.push(format!("{citadel}发核心命中，效果良好"));
    }
    if saturated_hits >= 1 {
        parts.push(format!("{saturated_hits}发打在已饱和分区，边际伤害低，换区域瞄准"));
    }
    if let Some(lead) = avg_lead {
        if lead.abs() > 30.0 {
            let dir = if lead > 0.0 { "过" } else { "欠" };
            parts.push(format!("提前量整体偏{dir}约 {:.0}m（目标航向）", lead.abs()));
        }
    }
    if parts.is_empty() {
        parts.push("无明显瞄准/弹药问题".to_owned());
    }
    let _ = (shells_fired, hits);
    parts.join("；")
}

/// A quantified, per-volley evaluation.
#[cfg_attr(feature = "serde", derive(serde::Serialize))]
#[derive(Clone, Debug)]
pub struct VolleyScore {
    pub clock: f32,
    pub salvo_id: u32,
    /// The salvo's first shell shot id; together with `salvo_id` it uniquely
    /// identifies a volley, so a reused salvo id does not merge distinct volleys.
    pub first_shot: Option<u32>,
    pub shells_fired: u32,
    pub shells_hit: u32,
    pub ammo: String,
    pub targets: Vec<String>,
    pub damage_dealt: f32,
    pub score: u32,
    pub verdict: String,
    /// Per-hit detail (target, zone, ribbon, reason) for this volley.
    pub hits: Vec<VolleyHitDetail>,
}

/// One shell's resolved result within a volley.
#[cfg_attr(feature = "serde", derive(serde::Serialize))]
#[derive(Clone, Debug)]
pub struct VolleyHitDetail {
    pub target: String,
    pub zone: String,
    pub ammo: String,
    pub ribbon: String,
    pub reason: String,
    pub damage: f32,
    pub lead_error_m: Option<f32>,
}

/// Evaluate each of the recording player's volleys, with a 0-100 value score.
///
/// The score is the realized damage versus each shell's full-penetration
/// potential (`alpha * 1/3`); citadel hits exceed it and cap at 100, misses,
/// overpens and no-pens drag it down.
pub fn analyze_volleys(
    report: &BattleReport,
    params: &dyn GameParamProvider,
    hull: Option<&HashMap<EntityId, HullData>>,
) -> Vec<VolleyScore> {
    use std::collections::BTreeMap;
    use std::collections::BTreeSet;
    let (self_entity, _) = self_shells(report, params);

    let mut fired: BTreeMap<(u32, Option<u32>), u32> = BTreeMap::new();
    let mut fired_clock: BTreeMap<(u32, Option<u32>), f32> = BTreeMap::new();
    let mut seen: HashSet<(u32, Option<u32>)> = HashSet::new();
    for salvo in report.salvos().iter().filter(|s| s.owner_id == self_entity) {
        if salvo.salvo_id == 0 || salvo.salvo_id == u32::MAX {
            // Unmatched salvo sentinel; not a real volley key.
            continue;
        }
        let key = (salvo.salvo_id, salvo.first_shot.map(|s| s.raw()));
        // One trigger pull can arrive as several SHOTS_PACK entries sharing a
        // salvo id; `first_shot` discriminates them. A merged/multi-perspective
        // session logs the same group more than once, so dedup before summing
        // or the shot count is inflated.
        if !seen.insert(key) {
            continue;
        }
        *fired.entry(key).or_insert(0) += salvo.shots;
        fired_clock.entry(key).or_insert(report.game_clock_to_elapsed(salvo.clock).0);
    }

    let all = assess(report, params, hull).assessments;
    let mut by_salvo: BTreeMap<(u32, Option<u32>), Vec<&HitAssessment>> = BTreeMap::new();
    for hit in &all {
        if hit.salvo_id == 0 || hit.salvo_id == u32::MAX {
            continue;
        }
        by_salvo.entry((hit.salvo_id, hit.first_shot)).or_default().push(hit);
    }

    // A salvo that was fired but landed no resolved hit must still produce a row,
    // so a miss drags the score down rather than disappearing from the report.
    let mut volley_keys: BTreeSet<(u32, Option<u32>)> = fired.keys().copied().collect();
    volley_keys.extend(by_salvo.keys().copied());

    let mut out = Vec::new();
    for (salvo_id, first_shot) in volley_keys {
        let key = (salvo_id, first_shot);
        let hits = by_salvo.get(&key).map(|v| v.as_slice()).unwrap_or(&[]);
        let shells_fired = fired.get(&key).copied().unwrap_or(0);
        let shells_hit = hits.len() as u32;
        let damage_dealt = hits.iter().map(|h| h.estimated_damage).sum::<f32>();
        let ammo = hits.first().map(|h| h.ammo_used.clone()).unwrap_or_else(|| "?".to_owned());
        let alpha = hits.first().map(|h| h.alpha_damage).unwrap_or(0.0);
        let potential = shells_fired as f32 * alpha * 0.33;
        let score = if potential > 0.0 { (damage_dealt / potential).clamp(0.0, 1.0) } else { 0.0 };
        let mut targets: Vec<String> = Vec::new();
        for h in hits {
            if !targets.contains(&h.victim_ship) {
                targets.push(h.victim_ship.clone());
            }
        }
        // A volley that landed nothing has no hit clock; fall back to the
        // salvo's own fire time so it sits at the right point on the timeline
        // instead of matching start (t=0).
        let clock = hits.first().map(|h| h.clock).unwrap_or_else(|| fired_clock.get(&key).copied().unwrap_or(0.0));
        let leads: Vec<f32> = hits.iter().filter_map(|h| h.lead_error_m).collect();
        let avg_lead = if leads.is_empty() {
            None
        } else {
            Some(leads.iter().sum::<f32>() / leads.len() as f32)
        };
        let score_u32 = (score * 100.0).round() as u32;
        let verdict = volley_verdict(hits, shells_fired, shells_hit, score_u32, avg_lead);
        let hit_details = hits
            .iter()
            .map(|h| VolleyHitDetail {
                target: h.victim_ship.clone(),
                zone: h.zone.clone(),
                ammo: h.ammo_used.clone(),
                ribbon: h.ribbon.clone(),
                reason: h.reason.clone(),
                damage: h.estimated_damage,
                lead_error_m: h.lead_error_m,
            })
            .collect();
        out.push(VolleyScore {
            clock,
            salvo_id,
            first_shot,
            shells_fired,
            shells_hit,
            ammo,
            targets,
            damage_dealt,
            score: score_u32,
            verdict,
            hits: hit_details,
        });
    }
    out.sort_by(|a, b| a.clock.partial_cmp(&b.clock).unwrap_or(std::cmp::Ordering::Equal));
    out
}

fn volley_verdict(
    hits: &[&HitAssessment],
    shells_fired: u32,
    shells_hit: u32,
    score: u32,
    avg_lead: Option<f32>,
) -> String {
    let overpen = hits.iter().filter(|h| h.hit_type.contains("OVERPEN")).count();
    let no_pen = hits.iter().filter(|h| h.hit_type.contains("NOPENETRATION")).count();
    let citadel = hits.iter().filter(|h| h.hit_type.contains("MAJORHIT")).count();
    let saturated = hits.iter().filter(|h| h.saturated).count();
    let mut parts = Vec::new();
    if shells_fired > shells_hit {
        parts.push(format!("{}发未命中", shells_fired - shells_hit));
    }
    if citadel > 0 {
        parts.push(format!("{citadel}发核心"));
    }
    if overpen > 0 {
        parts.push(format!("{overpen}发过穿"));
    }
    if no_pen > 0 {
        parts.push(format!("{no_pen}发未击穿"));
    }
    if saturated > 0 {
        parts.push(format!("{saturated}发打饱和区"));
    }
    let grade = match score {
        80..=100 => "优",
        55..=79 => "良",
        35..=54 => "中",
        _ => "差",
    };
    let mut msg = vec![grade.to_owned()];
    if !parts.is_empty() {
        msg.push(parts.join(","));
    }
    if let Some(lead) = avg_lead {
        if lead.abs() > 30.0 {
            let dir = if lead > 0.0 { "过" } else { "欠" };
            msg.push(format!("提前量偏{dir}约{:.0}m", lead.abs()));
        }
    }
    msg.join("；")
}

/// Render a report. `deep` selects the per-volley full report with per-hit
/// detail; otherwise a concise per-target lesson list is produced.
pub fn render_report(
    report: &BattleReport,
    params: &dyn GameParamProvider,
    deep: bool,
    hull: Option<&HashMap<EntityId, HullData>>,
) -> String {
    if deep {
        render_deep_report(report, params, hull)
    } else {
        render_normal_report(report, params, hull)
    }
}

/// Concise per-target report (normal).
pub fn render_normal_report(
    report: &BattleReport,
    params: &dyn GameParamProvider,
    hull: Option<&HashMap<EntityId, HullData>>,
) -> String {
    let lessons = summarize(report, params, hull);
    let outcome = assess(report, params, hull);
    let ship_name = self_ship_name(report, params).unwrap_or_else(|| "自舰".to_owned());
    let mut s = String::new();
    s.push_str(&format!("=== 瞄准/弹药复盘（按目标）：{ship_name} ===\n"));
    for l in &lessons {
        s.push_str(&format!(
            "- {}（{}） 命中{} 过穿{} 未击穿{} 跳弹{} 核心{} 饱和{} 换弹建议{}",
            l.victim_ship,
            l.victim_class,
            l.hits,
            l.overpen,
            l.no_pen,
            l.bounce,
            l.citadel,
            l.saturated_hits,
            l.switch_calls,
        ));
        if let Some(lead) = l.avg_lead_error_m {
            s.push_str(&format!(" 提前量{:.0}m", lead));
        }
        s.push_str(&format!("\n    {}\n", l.advice));
    }
    if outcome.assessments.is_empty() {
        s.push_str("无可用数据：没有可评估的主炮命中（未命中、非主炮、或命中无法解析）\n");
    } else if outcome.excluded > 0 {
        s.push_str(&format!("另有 {} 发命中无法评估（无受害舰/非主炮/姿态缺失/未知弹种）\n", outcome.excluded));
    }
    s
}

/// Full per-volley report with per-hit detail (deep).
pub fn render_deep_report(
    report: &BattleReport,
    params: &dyn GameParamProvider,
    hull: Option<&HashMap<EntityId, HullData>>,
) -> String {
    let volleys = analyze_volleys(report, params, hull);
    let outcome = assess(report, params, hull);
    let ship_name = self_ship_name(report, params).unwrap_or_else(|| "自舰".to_owned());
    let mut s = String::new();
    s.push_str(&format!("=== 逐轮瞄准/弹药复盘：{ship_name} ===\n"));
    for v in &volleys {
        let (hit_str, score_str) = if v.shells_hit == 0 {
            ("0命".to_owned(), "0".to_owned())
        } else {
            (format!("{}命", v.shells_hit), v.score.to_string())
        };
        s.push_str(&format!(
            "轮{}/#{} t={:.0}s  {}发 [{}] {} 命中{}  评分{}  {}\n",
            v.salvo_id,
            v.first_shot.map(|f| f.to_string()).unwrap_or_else(|| "?".to_owned()),
            v.clock,
            v.shells_fired,
            v.ammo,
            if v.targets.is_empty() { "?".to_owned() } else { v.targets.join("+") },
            hit_str,
            score_str,
            v.verdict,
        ));
        for h in &v.hits {
            s.push_str(&format!(
                "    - {}({})  {}  {:.0}伤: {}\n",
                h.target, h.zone, h.ribbon, h.damage, h.reason
            ));
        }
    }
    if outcome.assessments.is_empty() {
        s.push_str("无可用数据：没有可评估的主炮命中（未命中、非主炮、或命中无法解析）\n");
    } else if outcome.excluded > 0 {
        s.push_str(&format!("另有 {} 发命中无法评估（无受害舰/非主炮/姿态缺失/未知弹种）\n", outcome.excluded));
    }
    s
}

fn self_ship_name(report: &BattleReport, params: &dyn GameParamProvider) -> Option<String> {
    let build = ResolvedBuild::from_player(report.self_player(), &ProviderRef(params), report.version())?;
    let id = build.ship.id().raw().to_string();
    Some(ship_zh(&id, build.ship.name()))
}

/// Resolve the recording player's own main-battery shells via its build.
///
/// Returns the self entity and the two shell types the ship carries.
pub fn self_shells(report: &BattleReport, params: &dyn GameParamProvider) -> (EntityId, Vec<ShellInfo>) {
    let self_player = report.self_player();
    let self_entity = self_player.initial_state().entity_id();
    let shells = (|| {
        let build = ResolvedBuild::from_player(self_player, &ProviderRef(params), report.version())?;
        let artillery = equipped_artillery(&build)?;
        let mut seen = Vec::new();
        for name in &artillery.ammo {
            let shell = params
                .params()
                .iter()
                .find(|p| p.name() == name.as_str())?
                .projectile()?
                .to_shell_info(name.clone());
            if !seen.iter().any(|s: &ShellInfo| s.name == shell.name) {
                seen.push(shell);
            }
        }
        Some(seen)
    })()
    .unwrap_or_default();
    (self_entity, shells)
}

/// The equipped `_Artillery` component.
fn equipped_artillery(build: &ResolvedBuild) -> Option<&ArtilleryGunStats> {
    let components = build.ship.vehicle()?.ttx_components()?;
    let name = build
        .modules
        .iter()
        .find_map(|module| {
            module
                .unit()
                .and_then(|unit| unit.uc_type())
                .filter(|ct| ct.eq_ignore_ascii_case("_Artillery"))
                .map(|_| module.name().to_owned())
        })
        .or_else(|| {
            // No equipped module names the battery: resolve only when there is
            // nothing to choose between, never guess between candidates.
            let mut candidates = components.artillery.keys();
            let only = candidates.next()?;
            if candidates.next().is_some() {
                return None;
            }
            Some(only.clone())
        })?;
    let component = components.artillery(&name)?;
    component.guns.first()
}

/// Aggregate per-hit assessments for the recording player's own shells.
///
/// `hull` carries per-victim hull dimensions used to place zone boundaries
/// (`zone_for_hit`); pass `None` to fall back to the fixed heuristic.
pub fn assess(
    report: &BattleReport,
    params: &dyn GameParamProvider,
    hull: Option<&HashMap<EntityId, HullData>>,
) -> AssessOutcome {
    let (self_entity, shells) = self_shells(report, params);
    let victims = victim_info(report, params);
    let reload_s = self_reload_s(report, params);
    // A shell can only damage an enemy of the recording player. Hits whose
    // resolved victim is an ally or the self ship are a nearest-ship
    // misattribution (the real target is out-of-AOI), so they are excluded
    // rather than reported as a hit on a friend.
    let enemies: HashSet<EntityId> = report
        .players()
        .iter()
        .filter(|p| p.relation().is_enemy())
        .map(|p| p.initial_state().entity_id())
        .collect();
    let mut zone_damage: HashMap<(EntityId, String), f32> = HashMap::new();
    let mut out = Vec::new();
    let mut excluded = 0u32;

    for hit in report.hit_history().iter().filter(|hit| hit.hit.owner_id == self_entity) {
        // An unresolved victim (None) cannot be attributed to any enemy target,
        // so there is no recordable hit on a ship.
        let Some(victim_entity_id) = hit.victim_entity_id else { excluded += 1; continue };
        // A self-fired shell can never hit the self ship. For a known self owner
        // the resolver only considers enemy candidates, so a resolve to self is
        // defensive (e.g. the owner was absent from the player index and the
        // default chose the self team); exclude it rather than invent a target.
        if victim_entity_id == self_entity {
            continue;
        }
        if !enemies.contains(&victim_entity_id) {
            continue;
        }
        let Some(used) = shell_for_hit(hit, params) else { excluded += 1; continue };
        // Only main-battery shells are a player ammo choice; secondary/AA shells
        // are auto-fired and cannot be swapped, so they are out of scope.
        if !shells.iter().any(|s| s.name == used.name) {
            excluded += 1;
            continue;
        }
        let other = other_shell(&shells, &used);
        let (victim_id, victim_raw, victim_class) = victims
            .get(&victim_entity_id)
            .cloned()
            .unwrap_or_else(|| ("?".to_owned(), "?".to_owned(), "unknown".to_owned()));
        let victim = ship_zh(&victim_id, &victim_raw);
        let Some(pose) = hit.victim_pose else { excluded += 1; continue };
        let Some(origin) = shot_origin(hit) else { excluded += 1; continue };
        let impact = hit.hit.position.0;
        let incoming = origin_to_impact(hit);
        let belt_strike = belt_strike_angle(incoming, pose.yaw, pose.pitch, pose.roll);
        let aob = angle_on_bow(origin, impact, pose.yaw, pose.pitch, pose.roll);
        let Some(hit_type_name) = hit.hit.hit_type.shell_hit.known().map(|s| s.name()) else {
            excluded += 1;
            continue;
        };
        let hit_type = hit_type_name.to_owned();
        let zone = zone_for_hit(hit, hull.and_then(|m| m.get(&victim_entity_id)));
        // Prefer the exact GameParams zone from the ship's splash boxes so the
        // armour thickness/saturation budget reads the right plate (e.g. "St" or
        // "Cas" instead of a fuzzy "Hull" fallback); keep the coarse label for
        // the reason/swaps text and the reported zone.
        let hitloc_zone = hull
            .and_then(|m| m.get(&victim_entity_id))
            .and_then(|data| exact_zone_for_hit(hit, data))
            .unwrap_or_else(|| zone.clone());
        let (lead_error_m, lead_off_axis_m) = match shot_aim(hit) {
            Some(aim) => {
                let victim = pose.position.0;
                let offset = Vec3::new(aim.x - victim.x, aim.y - victim.y, aim.z - victim.z);
                let body = world_offset_to_body(offset, pose.yaw, pose.pitch, pose.roll);
                let along = body.x * 15.0;
                let off = body.z * 15.0;
                // Plausible lead errors are well under ~400 m; larger values are
                // a data/unit artifact (mismatched salvo or coordinate space).
                let sane = |v: f32| (v.abs() < 400.0).then_some(v);
                (sane(along), sane(off))
            }
            None => (None, None),
        };
        let hitloc = victim_hit_location(report, params, victim_entity_id, &hitloc_zone);
        let zone_mm = hitloc.as_ref().map(|hl| hl.thickness());
        let budget = hitloc.as_ref().map(|hl| hl.max_hp()).unwrap_or(0.0);
        // Saturation is per exact zone (the budget's `max_hp` pool), so the
        // accumulator and the citadel exception are keyed on the exact zone too;
        // the coarse label only feeds the reason/text field.
        let zone_damage_so_far = zone_damage.get(&(victim_entity_id, hitloc_zone.clone())).copied().unwrap_or(0.0);
        let saturated = !is_citadel_zone(&hitloc_zone) && budget > 0.0 && zone_damage_so_far >= budget;
        let pen = pen_verdict(&used, &hit_type, belt_strike, zone_mm.as_ref());
        let ribbon = ribbon_for(&hit_type);
        let reason = reason_for(&used, &zone, &hit_type, &victim_class);
        let mut swap = swap_verdict(&used, other, &hit_type, belt_strike, zone_mm.as_ref(), &victim_class);
        if saturated {
            swap = format!("{swap}; zone already saturated (~1/6 dmg), aim elsewhere");
        }
        if victim_class == "destroyer" {
            if let Some(reload) = reload_s {
                swap = format!(
                    "{swap}; note: switching to HE needs a ~{reload:.0}s full reload, only if the window allows"
                );
            }
        }
        let base = estimate_damage(&used, &hit_type, zone_mm.as_ref());
        let est = if saturated { base / 6.0 } else { base };
        zone_damage.entry((victim_entity_id, hitloc_zone.clone())).and_modify(|v| *v += est).or_insert(est);
        out.push(HitAssessment {
            victim_entity_id,
            victim_ship: victim,
            victim_class,
            zone,
            ammo_used: ammo_str(&used.ammo_type).to_owned(),
            ammo_other: ammo_str(&other.map(|s| s.ammo_type.clone()).unwrap_or(AmmoType::Unknown(String::new()))).to_owned(),
            alpha_damage: used.alpha_damage,
            strike_angle_deg: belt_strike,
            angle_on_bow_deg: aob,
            hit_type,
            pen_verdict: pen,
            swap_text: swap,
            saturated,
            zone_damage_so_far,
            reload_s,
            lead_error_m,
            lead_off_axis_m,
            salvo_id: hit.salvo.as_ref().map(|s| s.salvo_id).unwrap_or(0),
            first_shot: hit.salvo.as_ref().and_then(|s| s.shots.first()).map(|shot| shot.shot_id.raw()),
            clock: hit.clock.0,
            estimated_damage: est,
            ribbon,
            reason,
        });
    }
    AssessOutcome { assessments: out, excluded }
}

pub(crate) fn victim_info(report: &BattleReport, params: &dyn GameParamProvider) -> HashMap<EntityId, (String, String, String)> {
    let mut map = HashMap::new();
    for player in report.players() {
        if let Some(build) = ResolvedBuild::from_player(player, &ProviderRef(params), report.version()) {
            let class = species_class(&build.species).to_owned();
            let id = build.ship.id().raw().to_string();
            map.insert(player.initial_state().entity_id(), (id, build.ship.name().to_owned(), class));
        }
    }
    map
}

#[allow(dead_code)]
fn victim_armor(report: &BattleReport, params: &dyn GameParamProvider, entity: EntityId) -> Option<f32> {
    let player = report.players().iter().find(|p| p.initial_state().entity_id() == entity)?;
    let build = ResolvedBuild::from_player(player, &ProviderRef(params), report.version())?;
    belt_armor_mm(&build.ship)
}

pub(crate) fn shell_for_hit(hit: &ResolvedShotHit, params: &dyn GameParamProvider) -> Option<ShellInfo> {
    let salvo = hit.salvo.as_ref()?;
    let param = params.game_param_by_id(salvo.params_id)?;
    param.projectile().map(|proj| proj.to_shell_info(param.name().to_owned()))
}

fn other_shell<'a>(shells: &'a [ShellInfo], used: &ShellInfo) -> Option<&'a ShellInfo> {
    let used_type = ammo_str(&used.ammo_type);
    shells
        .iter()
        .find(|s| ammo_str(&s.ammo_type) != used_type)
}

pub(crate) fn shot_origin(hit: &ResolvedShotHit) -> Option<Vec3> {
    let salvo = hit.salvo.as_ref()?;
    salvo
        .shots
        .iter()
        .find(|shot| shot.shot_id == hit.hit.shot_id)
        .map(|shot| shot.origin.0)
        .or_else(|| salvo.shots.first().map(|shot| shot.origin.0))
}

fn shot_aim(hit: &ResolvedShotHit) -> Option<Vec3> {
    let salvo = hit.salvo.as_ref()?;
    salvo
        .shots
        .iter()
        .find(|shot| shot.shot_id == hit.hit.shot_id)
        .map(|shot| shot.target.0)
        .or_else(|| salvo.shots.first().map(|shot| shot.target.0))
}

pub(crate) fn origin_to_impact(hit: &ResolvedShotHit) -> Vec3 {
    let origin = shot_origin(hit).unwrap_or(Vec3::new(0.0, 0.0, 0.0));
    let impact = hit.hit.position.0;
    Vec3::new(impact.x - origin.x, impact.y - origin.y, impact.z - origin.z)
}

pub(crate) fn ammo_str(ammo: &AmmoType) -> &'static str {
    match ammo {
        AmmoType::AP => "AP",
        AmmoType::HE => "HE",
        AmmoType::SAP => "SAP",
        AmmoType::Unknown(_) => "?",
    }
}

pub(crate) fn ribbon_for(hit_type: &str) -> String {
    if hit_type.contains("OVERPEN") {
        "过穿".to_owned()
    } else if hit_type.contains("NOPENETRATION") {
        "未击穿".to_owned()
    } else if hit_type.contains("MAJORHIT") {
        "核心".to_owned()
    } else if hit_type.contains("RICOCHET") {
        "跳弹".to_owned()
    } else if hit_type.contains("NORMAL") {
        "命中".to_owned()
    } else {
        "其他".to_owned()
    }
}

fn reason_for(shell: &ShellInfo, zone: &str, hit_type: &str, victim_class: &str) -> String {
    let ammo = ammo_str(&shell.ammo_type);
    if hit_type.contains("OVERPEN") {
        if matches!(zone, "bow" | "stern" | "superstructure") {
            format!("{ammo}命中{zone}薄甲，未引信起爆而过穿；应瞄主装/核心或换 HE")
        } else {
            format!("{ammo}命中装甲过薄（口径碾压），未引信而过穿；换 HE 或瞄更厚部位")
        }
    } else if hit_type.contains("RICOCHET") {
        format!("目标角度过斜致{ammo}跳弹；换 HE 或等目标露侧")
    } else if hit_type.contains("NOPENETRATION") {
        format!("{ammo}穿深不足或角度太斜，未能击穿；考虑 HE 溅射或等露侧")
    } else if hit_type.contains("MAJORHIT") {
        format!("{ammo}命中核心区，穿深足够，获得核心伤害")
    } else if hit_type.contains("NORMAL") {
        if victim_class.is_empty() {
            "正常命中".to_owned()
        } else {
            format!("{ammo}正常命中{victim_class}")
        }
    } else {
        "其他".to_owned()
    }
}

pub(crate) fn species_class(species: &Species) -> &'static str {
    match species {
        Species::Battleship => "battleship",
        Species::Cruiser => "cruiser",
        Species::Destroyer => "destroyer",
        Species::AirCarrier => "carrier",
        _ => "other",
    }
}

/// Local Chinese ship-name table, keyed by the GameParams index. Unknown ships
/// fall back to the English name embedded in the index (after its class prefix).
pub(crate) fn ship_zh(id: &str, name: &str) -> String {
    if let Some(map) = SHIP_NAMES.get() {
        if let Some(zh) = map.get(id) {
            // Only trust a value that carries a CJK char; the generated table
            // falls back to the romanized name for ships it did not translate,
            // and the embedded tables know them.
            if zh.chars().any(|c| ('\u{4E00}'..='\u{9FFF}').contains(&c)) {
                return zh.clone();
            }
        }
    }
    if let Some(zh) = exact_zh(name) {
        return zh.to_owned();
    }
    // Fallback to the latin base name (after the class prefix), then its first
    // token, so variant hulls (Furutaka_1926) still map to one Chinese ship.
    let base = name.split_once('_').map(|(_, b)| b).unwrap_or(name);
    if let Some(zh) = latin_zh(base) {
        return zh.to_owned();
    }
    let first = base.split('_').next().unwrap_or(base);
    if let Some(zh) = latin_zh(first) {
        return zh.to_owned();
    }
    base.to_owned()
}

fn exact_zh(name: &str) -> Option<&'static str> {
    let zh = match name {
        "PASB729_Georgia" => "佐治亚",
        "PJSD004_Minekadze_1920" => "峯风",
        "PJSD025_True_Kamikaze" => "神风",
        "PJSC007_Aoba_1943" => "青叶",
        "PJSC009_Mogami_1935" => "最上",
        "PJSC517_Maya" => "摩耶",
        "PJSB509_Musashi" => "武藏",
        "PJSD105_Mutsuki" => "睦月",
        "PJSD107_Akatsuki" => "晓",
        "PJSD108_Akizuki" => "秋月",
        "PJSD207_Shiratsuyu" => "白露",
        "PJSD208_Kagero" => "阳炎",
        "PJSD518_Asashio" => "朝潮",
        "PRSC109_Dmitry_Donskoy" => "德米特里·顿斯科伊",
        "PGSC109_Roon" => "罗恩",
        "PGSD110_Z_52" => "Z-52",
        _ => "",
    };
    (!zh.is_empty()).then_some(zh)
}

fn latin_zh(base: &str) -> Option<&'static str> {
    let zh = match base {
        "Kamikaze" | "True_Kamikaze" => "神风",
        "Minekadze_1920" | "Minekadze" => "峯风",
        "Aoba_1943" | "Aoba" => "青叶",
        "Mogami_1935" | "Mogami" => "最上",
        "Maya" => "摩耶",
        "Musashi" => "武藏",
        "Mutsuki" => "睦月",
        "Akatsuki" => "晓",
        "Akizuki" => "秋月",
        "Shiratsuyu" => "白露",
        "Kagero" => "阳炎",
        "Asashio" => "朝潮",
        "Furutaka_1926" | "Furutaka" => "古鷹",
        "Fubuki" => "吹雪",
        "Myoko_1945" | "Myoko" => "妙高",
        "Myōkō" | "Myōkō_1945" => "妙高",
        "Hōchi" => "帆风",
        "Yudachi" => "夕立",
        "Hatsuharu" => "初春",
        "Shirane_1944" | "Shirane" => "白根",
        "Roon" => "罗恩",
        "Hindenburg" => "希登堡",
        "Hannover" => "汉诺威",
        "Mecklenburg" => "梅克伦堡",
        "Preussen" => "普鲁士",
        "Schlieffen" => "施里芬",
        "Z_52" | "Z52" => "Z-52",
        "Elbing" => "埃尔宾",
        "Georg_Hoffmann" => "格奥尔格·霍夫曼",
        "Prinz_Adalbert" => "阿达尔伯特亲王",
        "Dmitry_Donskoy" => "德米特里·顿斯科伊",
        _ => "",
    };
    (!zh.is_empty()).then_some(zh)
}

fn pen_verdict(shell: &ShellInfo, hit_type: &str, belt_strike_deg: f32, belt_mm: Option<&f32>) -> String {
    if hit_type.contains("RICOCHET") {
        return "bounce".to_owned();
    }
    if hit_type.contains("OVERPEN") {
        return "overpen".to_owned();
    }
    if hit_type.contains("NOPENETRATION") {
        return "no-pen".to_owned();
    }
    if hit_type.contains("MAJORHIT") {
        return "citadel".to_owned();
    }
    match shell.ammo_type {
        AmmoType::AP => {
            if belt_strike_deg >= shell.always_ricochet_angle {
                "bounce".to_owned()
            } else if belt_strike_deg >= shell.ricochet_angle {
                "bounce-risk".to_owned()
            } else {
                "can-pen".to_owned()
            }
        }
        AmmoType::HE => match belt_mm {
            Some(belt) if shell.he_pen_mm.unwrap_or(0.0) < *belt => "splash".to_owned(),
            Some(_) => "pen".to_owned(),
            None => "unknown".to_owned(),
        },
        AmmoType::SAP => match belt_mm {
            Some(belt) if shell.sap_pen_mm.unwrap_or(0.0) < *belt => "no-pen".to_owned(),
            Some(_) => "pen".to_owned(),
            None => "unknown".to_owned(),
        },
        AmmoType::Unknown(_) => "unknown".to_owned(),
    }
}

fn swap_verdict(
    used: &ShellInfo,
    other: Option<&ShellInfo>,
    hit_type: &str,
    belt_strike_deg: f32,
    _belt_mm: Option<&f32>,
    victim_class: &str,
) -> String {
    let Some(other) = other else {
        return "unknown".to_owned();
    };
    let other_is_he = matches!(other.ammo_type, AmmoType::HE);
    let is_thin = matches!(victim_class, "destroyer" | "carrier");
    match used.ammo_type {
        AmmoType::HE => {
            let target_bad_for_he = hit_type.contains("NOPENETRATION") || hit_type.contains("RICOCHET");
            if is_thin {
                return "keep: destroyer/carrier plating is too thin for a shell-type swap; stick with HE".to_owned();
            }
            let other_is_ap = matches!(other.ammo_type, AmmoType::AP);
            let ap_would_pen =
                other_is_ap && belt_strike_deg < other.ricochet_angle && belt_strike_deg < other.always_ricochet_angle;
            if target_bad_for_he && ap_would_pen {
                "switch: thick target, angle is inside AP range; AP may pen the belt".to_owned()
            } else {
                "keep: HE splash fine at this angle".to_owned()
            }
        }
        AmmoType::AP => {
            if is_thin {
                return if hit_type.contains("OVERPEN") {
                    if other_is_he {
                        "switch: AP overpens a destroyer/carrier; HE deals full damage".to_owned()
                    } else {
                        "keep: AP overpens a thin plate and no HE is available".to_owned()
                    }
                } else {
                    "keep: thin target; shell-type swap is not the fix".to_owned()
                };
            }
            if hit_type.contains("RICOCHET") {
                if other_is_he {
                    "keep: target too angled, AP bounces; use HE to splash".to_owned()
                } else {
                    "keep: target too angled and no HE available to splash".to_owned()
                }
            } else if hit_type.contains("NOPENETRATION") {
                if other_is_he {
                    "keep: AP cannot reach here; HE splashes more".to_owned()
                } else {
                    "keep: AP cannot reach here and no HE is available".to_owned()
                }
            } else if hit_type.contains("OVERPEN") {
                if other_is_he {
                    "switch: AP overpens a thin/DD plate; HE deals full damage (or aim at a thicker section)"
                        .to_owned()
                } else {
                    "keep: AP overpens; no HE available to swap to".to_owned()
                }
            } else {
                "keep: AP penetrating is the right call here".to_owned()
            }
        }
        AmmoType::SAP => {
            if hit_type.contains("NOPENETRATION") {
                "switch: SAP could not pierce; HE splashes better".to_owned()
            } else {
                "keep: SAP fine here".to_owned()
            }
        }
        AmmoType::Unknown(_) => "unknown".to_owned(),
    }
}

#[allow(dead_code)]
fn belt_armor_mm(ship: &Param) -> Option<f32> {
    let armor = ship.vehicle()?.armor()?;
    let mut best: Option<f32> = None;
    for (material_id, layers) in armor {
        if is_belt_material(*material_id) {
            for thickness in layers.values() {
                best = Some(best.map_or(*thickness, |b| b.max(*thickness)));
            }
        }
    }
    best
}

#[allow(dead_code)]
fn is_belt_material(material_id: u32) -> bool {
    if material_id > u32::from(u8::MAX) {
        return false;
    }
    let name = collision_material_name(material_id as u8);
    name.contains("Belt") || name.contains("Cit") || name.contains("Armor")
}

/// The per-victim zone boundaries, in meters, from the hull dimensions (or the
/// fixed battleship-scaled heuristic when the hull is unknown).
///
/// The bow/stern and belt boundaries scale with the hull (see
/// [`crate::hull_dim`]); they are the two that a fixed threshold gets wrong for
/// a small ship. The deck/superstructure bounds stay on the fixed heuristic
/// because the armour-mesh bounding box cannot localise where the deck or the
/// superstructure base sits (it only yields the total height, which on a
/// tall-masted battleship is far above the deck) -- scaling them by total
/// height would put a destroyer's deck below any real hit.
fn zone_thresholds(data: Option<&HullData>) -> ZoneThresholds {
    // Calibrated on Iowa's armour-mesh bbox (half-length 135.2 m, half-beam
    // 16.5 m): the old 110 m bow boundary sits at 110 / 135.2 = 0.814 of the
    // half-length and the old 8 m belt boundary at 8 / 16.5 = 0.485 of the
    // half-beam. Applied to the per-side reach, a centred ship reproduces the
    // old boundaries exactly; Iowa's fore reach (137.5 m) gives ~112 m, within
    // ~2% of the old 110 m.
    const BOW_BOUNDARY_FRACTION: f32 = 0.814;
    const BELT_BOUNDARY_FRACTION: f32 = 0.485;
    const DEFAULT_FORE: f32 = 110.0;
    const DEFAULT_AFT: f32 = 110.0;
    const DEFAULT_DECK: f32 = 6.0;
    const DEFAULT_SUPERSTRUCTURE: f32 = 14.0;
    const DEFAULT_BELT: f32 = 8.0;

    match data.map(|d| &d.dim) {
        Some(h) => ZoneThresholds {
            fore: h.fore_m * BOW_BOUNDARY_FRACTION,
            aft: h.aft_m * BOW_BOUNDARY_FRACTION,
            deck: DEFAULT_DECK,
            superstructure: DEFAULT_SUPERSTRUCTURE,
            belt: h.half_beam_m * BELT_BOUNDARY_FRACTION,
        },
        None => ZoneThresholds {
            fore: DEFAULT_FORE,
            aft: DEFAULT_AFT,
            deck: DEFAULT_DECK,
            superstructure: DEFAULT_SUPERSTRUCTURE,
            belt: DEFAULT_BELT,
        },
    }
}

#[derive(Clone, Copy)]
struct ZoneThresholds {
    fore: f32,
    aft: f32,
    deck: f32,
    superstructure: f32,
    belt: f32,
}

/// Coarse zone from the body-frame impact. World units are scaled to ship
/// meters by [`crate::fire_chance::geometry`]'s 15x (BW_TO_SHIP); the
/// horizontal bow/belt bounds come from the victim's hull dimensions when known
/// and otherwise fall back to the fixed battleship-scaled heuristic (the
/// vertical deck/superstructure bounds stay on the fixed heuristic).
pub(crate) fn zone_for_hit(hit: &ResolvedShotHit, data: Option<&HullData>) -> String {
    let Some(pose) = hit.victim_pose else { return "unknown".to_owned() };
    let impact = hit.hit.position.0;
    // The zone is the impact's offset from the victim's centre, not from the
    // muzzle. `shot_origin` is the gun (kilometres away), so projecting the
    // flight vector into the victim's body frame labels by shot range and makes
    // bow/stern reachable and deck/superstructure/citadel unreachable.
    let body = world_offset_to_body(
        Vec3::new(
            impact.x - pose.position.x,
            impact.y - pose.position.y,
            impact.z - pose.position.z,
        ),
        pose.yaw,
        pose.pitch,
        pose.roll,
    );
    let y = body.y * crate::hull_dim::SHIP_MODEL_TO_METERS;
    let x = body.x * crate::hull_dim::SHIP_MODEL_TO_METERS;
    let z = body.z * crate::hull_dim::SHIP_MODEL_TO_METERS;
    let bounds = zone_thresholds(data);
    if y > bounds.superstructure {
        "superstructure".to_owned()
    } else if x > bounds.fore {
        "bow".to_owned()
    } else if x < -bounds.aft {
        "stern".to_owned()
    } else if y > bounds.deck {
        "deck".to_owned()
    } else if z.abs() > bounds.belt && y < bounds.deck {
        "belt".to_owned()
    } else {
        "citadel".to_owned()
    }
}

/// Estimated damage this shell applied to the target zone, using the game's
/// damage-saturation fractions: citadel 100%, normal pen 33%, overpen 10%,
/// shatter/ricochet 0, splash 33%. Never the client-exact value.
pub fn estimate_damage(shell: &ShellInfo, hit_type: &str, belt_mm: Option<&f32>) -> f32 {
    let alpha = shell.alpha_damage;
    if hit_type.contains("MAJORHIT") {
        return alpha;
    }
    if hit_type.contains("OVERPEN") {
        return alpha * 0.10;
    }
    if hit_type.contains("RICOCHET") || hit_type.contains("NOPENETRATION") {
        return 0.0;
    }
    match shell.ammo_type {
        AmmoType::HE => match belt_mm {
            Some(belt) if shell.he_pen_mm.unwrap_or(0.0) >= *belt => alpha,
            _ => alpha * 0.33,
        },
        _ => alpha * 0.33,
    }
}

/// The self ship's own hits on enemies, as an (elapsed clock, estimated damage)
/// timeline. This is the OUTPUT dimension that survival's coupling composes
/// against the HP timeline; the output-end report (`hit-value` etc.) is a
/// separate consumer of the same `hit_history`.
pub struct OutputTimeline {
    /// (elapsed clock, estimated damage) for each fully-resolved hit.
    pub events: Vec<(f32, f32)>,
    /// Enemy-victim hits that could not be fully estimated (missing shell, pose,
    /// or origin); disclosed so output is honest about its lower bound.
    pub dropped: u32,
}

pub fn self_output_timeline(
    report: &BattleReport,
    self_entity: EntityId,
    enemies: &HashSet<EntityId>,
    params: &dyn GameParamProvider,
    hull: Option<&HashMap<EntityId, HullData>>,
) -> OutputTimeline {
    let mut events: Vec<(f32, f32)> = Vec::new();
    let mut dropped = 0u32;
    for hit in report.hit_history().iter().filter(|h| h.hit.owner_id == self_entity) {
        let Some(victim_id) = hit.victim_entity_id else { continue };
        if !enemies.contains(&victim_id) {
            continue;
        }
        let Some(shell) = shell_for_hit(hit, params) else { dropped += 1; continue };
        let Some(_pose) = hit.victim_pose else { dropped += 1; continue };
        let Some(_origin) = shot_origin(hit) else { dropped += 1; continue };
        let zone = zone_for_hit(hit, hull.and_then(|m| m.get(&victim_id)));
        let hitloc_zone = hull
            .and_then(|m| m.get(&victim_id))
            .and_then(|data| exact_zone_for_hit(hit, data))
            .unwrap_or_else(|| zone.clone());
        let hitloc = victim_hit_location(report, params, victim_id, &hitloc_zone);
        let zone_mm = hitloc.as_ref().map(|hl| hl.thickness());
        let hit_type = hit.hit.hit_type.shell_hit.known().map(|s| s.name()).unwrap_or("UNKNOWN");
        let est = estimate_damage(&shell, hit_type, zone_mm.as_ref());
        events.push((report.game_clock_to_elapsed(hit.clock).0, est));
    }
    events.sort_by(|a, b| a.0.total_cmp(&b.0));
    OutputTimeline { events, dropped }
}

/// Approximate HP a zone can absorb before saturating. A fraction of the
/// victim's maximum HP; the citadel never saturates for damage purposes.
#[allow(dead_code)]
pub(crate) fn saturation_budget(max_hp: f32, zone: &str) -> f32 {
    if max_hp <= 0.0 {
        return 0.0;
    }
    match zone {
        "citadel" => 0.0,
        "superstructure" => max_hp * 0.15,
        "bow" | "stern" => max_hp * 0.15,
        _ => max_hp * 0.30,
    }
}

/// Whether a hit-location key is the citadel (which never saturates for damage
/// purposes). GameParams spells it "Citadel" or "Cit" across ships.
pub(crate) fn is_citadel_zone(zone: &str) -> bool {
    zone.eq_ignore_ascii_case("citadel") || zone.eq_ignore_ascii_case("cit")
}

/// The victim's hit-location record for `zone`, cloned out of the build.
pub(crate) fn victim_hit_location(
    report: &BattleReport,
    params: &dyn GameParamProvider,
    entity: EntityId,
    zone: &str,
) -> Option<wowsunpack::game_params::types::HitLocation> {
    let player = report.players().iter().find(|p| p.initial_state().entity_id() == entity)?;
    let build = ResolvedBuild::from_player(player, &ProviderRef(params), report.version())?;
    let locations = build.ship.vehicle()?.hit_locations()?;
    hit_location_for(locations, zone).cloned()
}

pub(crate) fn hit_location_for<'a>(
    locations: &'a std::collections::HashMap<String, wowsunpack::game_params::types::HitLocation>,
    zone: &str,
) -> Option<&'a wowsunpack::game_params::types::HitLocation> {
    if let Some(key) = locations.keys().find(|k| k.eq_ignore_ascii_case(zone)) {
        return locations.get(key);
    }
    let needles: &[&str] = match zone {
        "bow" => &["Bow"],
        "stern" => &["Stern"],
        "citadel" => &["Citadel", "Cit"],
        "superstructure" => &["Superstructure", "Super"],
        "deck" => &["Hull", "Deck"],
        "belt" => &["Hull", "Belt", "Casemate"],
        _ => &["Hull"],
    };
    for needle in needles {
        if let Some(key) = locations.keys().find(|k| k.contains(needle)) {
            return locations.get(key);
        }
    }
    None
}

fn self_reload_s(report: &BattleReport, params: &dyn GameParamProvider) -> Option<f32> {
    let self_player = report.self_player();
    let build = ResolvedBuild::from_player(self_player, &ProviderRef(params), report.version())?;
    equipped_artillery(&build)?.shot_delay.map(|seconds| seconds.value())
}

/// Re-derived for completeness; kept separate from the verdict because the
/// range-to-impact is not yet trusted, so it is not used in the verdicts.
#[allow(dead_code)]
fn pen_at_range(shell: &ShellInfo, range_m: f32) -> Option<f32> {
    let params = ShellParams::from_shell_info(shell)?;
    let impact = solve_for_range(&params, Meters::from(range_m))?;
    Some(params.raw_penetration(impact.impact_velocity).value())
}

/// Adapt `&dyn GameParamProvider` to the generic `P: GameParamProvider` that
/// `ResolvedBuild::from_player` needs. Mirrors `fire_chance::resolve`.
pub(crate) struct ProviderRef<'a>(pub &'a dyn GameParamProvider);

impl GameParamProvider for ProviderRef<'_> {
    fn game_param_by_id(&self, id: wowsunpack::game_types::GameParamId) -> Option<Rc<Param>> {
        self.0.game_param_by_id(id)
    }
    fn game_param_by_index(&self, index: &str) -> Option<Rc<Param>> {
        self.0.game_param_by_index(index)
    }
    fn game_param_by_name(&self, name: &str) -> Option<Rc<Param>> {
        self.0.game_param_by_name(name)
    }
    fn params(&self) -> &[Rc<Param>] {
        self.0.params()
    }
}

#[cfg(test)]
mod zone_tests {
    use crate::hull_dim::HullDim;
    use wows_replays::analyzer::battle_controller::state::VictimPose;
    use wows_replays::analyzer::decoder::HitType;
    use wows_replays::analyzer::decoder::ShotHit;
    use wows_replays::types::EntityId;
    use wows_replays::types::GameClock;
    use wows_replays::types::WorldPos;
    use wowsunpack::game_types::ShotId;
    use wowsunpack::game_types::Vec3;
    use wowsunpack::recognized::Recognized;

    use super::*;

    fn hit_at(offset: Vec3, yaw: f32) -> ResolvedShotHit {
        ResolvedShotHit {
            clock: GameClock(0.0),
            hit: ShotHit {
                owner_id: EntityId::from(1u32),
                hit_type: HitType {
                    collision: Recognized::Unknown("0".to_owned()),
                    shell_hit: Recognized::Unknown("0".to_owned()),
                    raw: 0,
                },
                shot_id: ShotId::from(1u32),
                position: WorldPos::new(offset.x, offset.y, offset.z),
                terminal_ballistics: None,
            },
            victim_entity_id: Some(EntityId::from(2u32)),
            salvo: None,
            fired_at: None,
            victim_pose: Some(VictimPose { position: WorldPos::new(0.0, 0.0, 0.0), yaw, pitch: 0.0, roll: 0.0 }),
        }
    }

    /// The body frame equals the world frame at yaw=0, so a world offset maps
    /// directly to a body offset. WORLD_TO_METERS is 15, so 8.67 world units =
    /// 130 m (bow), 1.0 = 15 m (superstructure), 0.5 = 7.5 m (deck), 0.6 = 9 m
    /// (belt), 0.1 = 1.5 m (citadel).
    #[test]
    fn zones_use_the_15m_scale() {
        assert_eq!(zone_for_hit(&hit_at(Vec3::new(8.67, 0.0, 0.0), 0.0), None), "bow");
        assert_eq!(zone_for_hit(&hit_at(Vec3::new(-8.67, 0.0, 0.0), 0.0), None), "stern");
        assert_eq!(zone_for_hit(&hit_at(Vec3::new(0.0, 1.0, 0.0), 0.0), None), "superstructure");
        assert_eq!(zone_for_hit(&hit_at(Vec3::new(0.0, 0.5, 0.0), 0.0), None), "deck");
        assert_eq!(zone_for_hit(&hit_at(Vec3::new(0.0, 0.0, 0.6), 0.0), None), "belt");
        assert_eq!(zone_for_hit(&hit_at(Vec3::new(0.0, 0.0, 0.1), 0.0), None), "citadel");
    }

    /// A yawed broadside impact must be classified laterally (belt/citadel), not
    /// as bow/stern: the rotation is applied before the zone thresholds, so the
    /// ship's heading is honored rather than ignored.
    #[test]
    fn zones_respect_the_yaw_rotation() {
        let zone = zone_for_hit(&hit_at(Vec3::new(8.67, 0.0, 0.0), std::f32::consts::FRAC_PI_2), None);
        assert!(
            zone == "belt" || zone == "citadel" || zone == "deck",
            "expected a lateral/vertical zone for a yawed broadside, got {zone}"
        );
    }

    /// A hull-unknown classifier uses the fixed battleship thresholds, so a
    /// destroyer-sized hull (half-length ~70 m, so a ~57 m bow boundary) is
    /// misread as citadel for an impact 66 m forward (inside the hull, below
    /// the old 110 m bow line). With the hull's dimensions the same impact
    /// lands in the bow zone, which is what the per-ship refinement is for.
    #[test]
    fn per_ship_bow_boundary_rescues_a_destroyer_hit() {
        let dd = HullData {
            dim: HullDim { fore_m: 70.5, aft_m: 70.5, half_beam_m: 6.6, height_m: 19.4 },
            zones: None,
        };
        let hit = hit_at(Vec3::new(4.4, 0.0, 0.0), 0.0);
        assert_eq!(zone_for_hit(&hit, None), "citadel");
        assert_eq!(zone_for_hit(&hit, Some(&dd)), "bow");
    }
}
