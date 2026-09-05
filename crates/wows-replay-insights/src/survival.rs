//! S1: survival-side evaluation.
//!
//! Assesses how the recording player survived the match from data that is
//! already decoded: incoming hits on the self ship and their estimated damage,
//! fires, DCP / repair self-rescue, death timing, and the server "agro"
//! (potential damage aimed at the self ship). Produces a 0-100 survival score
//! with evidence-backed conclusions.
//!
//! The incoming-hit damage reuse the committed output-side engine
//! (`hit_value::estimate_damage`) and its enemy-only victim rule. It never
//! fabricates a hit: a hit whose victim pose or salvo is absent is counted as
//! unidentified rather than assigned damage.

use std::collections::HashMap;

use wows_battle_world::report::BattleReport;
use wows_replays::types::EntityId;
use wows_replays::types::GameClock;
use wowsunpack::game_params::types::GameParamProvider;
use wowsunpack::game_params::types::Param;
use wowsunpack::game_types::ChargeCount;
use wowsunpack::game_types::Consumable;
use wowsunpack::game_types::DamageStatCategory;
use wowsunpack::recognized::Recognized;
use wowsunpack::Rc;

use crate::build::ResolvedBuild;
use crate::fire_chance::geometry::angle_on_bow;
use crate::fire_chance::geometry::belt_strike_angle;
use crate::hit_value;

/// How long after a fire starts a DCP that extinguishes it still counts as
/// prompt. Chosen from the fire section's default duration; a DCP is prompt
/// only inside this window.
const PROMPT_DCP_WINDOW_S: f32 = 10.0;

/// One incoming shell hit on the self ship, with the damage it estimated.
#[derive(Clone, Debug)]
#[cfg_attr(feature = "serde", derive(serde::Serialize))]
pub struct IncomingHit {
    pub clock_s: f32,
    pub attacker: String,
    pub attacker_class: String,
    pub ammo: String,
    pub hit_type: String,
    pub ribbon: String,
    pub zone: String,
    pub estimated_damage: f32,
    pub strike_angle_deg: f32,
    pub angle_on_bow_deg: f32,
    pub saturated: bool,
    pub zone_max_hp: f32,
}

/// Damage aggregated per hostile attacker that hit the self ship.
#[derive(Clone, Debug)]
#[cfg_attr(feature = "serde", derive(serde::Serialize))]
pub struct IncomingSource {
    pub attacker: String,
    pub attacker_class: String,
    pub hits: u32,
    pub damage_estimated: f32,
    pub biggest_hit: f32,
    pub ammo: Vec<String>,
    pub zones: Vec<String>,
}

/// Potential (agro) damage split by the weapon that aimed it at the self ship.
#[derive(Clone, Debug)]
#[cfg_attr(feature = "serde", derive(serde::Serialize))]
pub struct WeaponPotential {
    pub weapon: String,
    pub potential: f32,
}

/// The weighted components of the S1 survival score, so the score is auditable.
#[derive(Clone, Debug)]
#[cfg_attr(feature = "serde", derive(serde::Serialize))]
pub struct ScoreBreakdown {
    /// 1 - taken/potential (evasion). 1.0 = chewed up none of what was aimed.
    pub avoidance: f32,
    /// 1.0 while alive; died -> death clock / match length.
    pub survival: f32,
    /// Prompt-DCP / repair coverage of fires. Baseline for ships without DCP.
    pub self_rescue: f32,
    pub avoidance_weight: f32,
    pub survival_weight: f32,
    pub self_rescue_weight: f32,
    pub score: f32,
}

/// The full S1 survival profile for the recording player.
#[derive(Clone, Debug)]
#[cfg_attr(feature = "serde", derive(serde::Serialize))]
pub struct SurvivalProfile {
    pub self_ship: String,
    pub self_class: String,
    pub self_max_hp: Option<f32>,
    pub map: String,
    pub game_mode: String,
    pub match_group: String,
    pub version: String,
    pub result: String,
    pub finish_type: String,
    pub max_duration_s: u32,
    pub played_duration_s: Option<f32>,

    /// Server potential damage aimed at the self ship (DamageStatCategory::Agro).
    pub potential_damage: f32,
    pub potential_by_weapon: Vec<WeaponPotential>,
    /// Estimated damage the self ship actually took from identified shell hits.
    pub taken_damage_estimated: f32,
    /// How much of the aimed potential actually connected (0..1).
    pub taken_frac_of_potential: f32,
    /// 1 - taken/potential. A player who was heavily aimed at but not hit is high.
    pub avoidance_ratio: f32,
    /// Estimated damage taken as a share of the ship's max HP.
    pub taken_frac_of_hp: f32,

    pub shell_hits_taken: u32,
    /// Hits whose salvo (and therefore shell identity) could not be matched;
    /// every torpedo hit and every shell whose salvo aged out of the 30s list.
    pub unidentified_hits: u32,
    pub saturating_hits: u32,
    pub biggest_hit: f32,

    /// Fires the self ship lit. `None` when `burningFlags` never replicated, so
    /// "no fires" is unknown rather than zero.
    pub fires_lit: Option<u32>,
    pub burn_observed: bool,
    /// Flood state is not decoded at report level (the burn log ignores flood
    /// bits). Set only when determinable; otherwise "unknown".
    pub flood_status: String,

    pub has_dcp: bool,
    /// `None` means the Damage Control has unlimited charges (base DCP).
    pub dcp_charges: Option<u32>,
    pub dcp_activations: u32,
    pub has_repair_party: bool,
    pub repair_party_activations: u32,
    pub smoke_activations: u32,
    /// Number of sustained (>= 10s) fire episodes that a DCP covered.
    pub fires_covered: u32,
    /// Number of sustained fire episodes the self ship ran.
    pub sustained_fires: u32,
    pub dcp_prompt_ratio: f32,

    pub died: bool,
    pub death_clock_s: Option<f32>,
    pub death_share_of_match: Option<f32>,

    pub survival_score: u32,
    pub grade: String,
    pub verdict: String,
    pub conclusions: Vec<String>,
    pub score_breakdown: ScoreBreakdown,
    pub hits: Vec<IncomingHit>,
    pub sources: Vec<IncomingSource>,
}

/// Adapt `&dyn GameParamProvider` to the generic `P: GameParamProvider` that
/// `ResolvedBuild::from_player` needs. Mirrors `hit_value::ProviderRef`.
struct ProviderRef<'a>(&'a dyn GameParamProvider);

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

fn elapsed(report: &BattleReport, clock: GameClock) -> f32 {
    report.game_clock_to_elapsed(clock).0
}

fn self_build(report: &BattleReport, params: &dyn GameParamProvider) -> Option<ResolvedBuild> {
    ResolvedBuild::from_player(report.self_player(), &ProviderRef(params), report.version())
}

fn grade_for(score: u32) -> &'static str {
    match score {
        80..=100 => "优",
        55..=79 => "良",
        35..=54 => "中",
        _ => "差",
    }
}

/// Build the S1 survival profile from a finished battle report.
pub fn assess(report: &BattleReport, params: &dyn GameParamProvider) -> SurvivalProfile {
    let self_entity = report.self_player().initial_state().entity_id();
    let build = self_build(report, params);
    let (self_ship, self_class) = match &build {
        Some(b) => {
            let id = b.ship.id().raw().to_string();
            (hit_value::ship_zh(&id, b.ship.name()), hit_value::species_class(&b.species).to_owned())
        }
        None => ("自舰".to_owned(), "unknown".to_owned()),
    };
    let self_max_hp = build
        .as_ref()
        .and_then(|b| b.ship.vehicle()?.ttx_components())
        .map(|c| c.hulls.values().filter_map(|h| h.health).map(|hp| hp.value()).fold(0.0f32, f32::max))
        .filter(|v| *v > 0.0);

    let mut has_dcp = false;
    let mut dcp_charges = 0u32;
    let mut has_repair_party = false;
    if let Some(b) = &build {
        for slot in &b.slots {
            match slot.consumable_type {
                Recognized::Known(Consumable::DamageControl) => {
                    has_dcp = true;
                    dcp_charges = match slot.total_charges {
                        ChargeCount::Finite(n) => n,
                        ChargeCount::Unlimited => u32::MAX,
                    };
                }
                Recognized::Known(Consumable::RepairParty) => has_repair_party = true,
                _ => {}
            }
        }
    }

    // Consumable activations for the self ship, ordered by clock.
    let mut dcp_activations = 0u32;
    let mut repair_party_activations = 0u32;
    let mut smoke_activations = 0u32;
    let mut dcp_clocks: Vec<f32> = Vec::new();
    if let Some(activated) = report.active_consumables().get(&self_entity) {
        for ac in activated {
            match ac.consumable {
                Recognized::Known(Consumable::DamageControl) => {
                    dcp_activations += 1;
                    dcp_clocks.push(elapsed(report, ac.activated_at));
                }
                Recognized::Known(Consumable::RepairParty) => repair_party_activations += 1,
                Recognized::Known(Consumable::Smoke) => smoke_activations += 1,
                _ => {}
            }
        }
    }
    dcp_clocks.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

    // Fire timeline for the self ship: lit / out deltas with elapsed clocks.
    // A DCP is only a self-rescue win when it is used while a fire is actually
    // burning; a fire that self-extinguishes (short) never needed DCP, so it
    // is not counted as a miss. We reconstruct burning episodes from the
    // section-bitmask transitions and judge only the sustained ones.
    let burn_observed = report.burn_state_observed();
    let mut fires_lit = 0u32;
    let mut fire_events: Vec<(f32, i32)> = Vec::new();
    for change in report.burn_state_changes() {
        if change.victim != self_entity {
            continue;
        }
        let t = elapsed(report, change.clock);
        let lit = change.newly_lit().count() as u32;
        fires_lit += lit;
        for _ in 0..lit {
            fire_events.push((t, 1));
        }
        let out = (change.previous & !change.current).count_ones() as i32;
        for _ in 0..out {
            fire_events.push((t, -1));
        }
    }
    fire_events.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));

    // Collapse the raw deltas into consecutive "burning" episodes: a period
    // where at least one fire section is alight, from the first lit to the last
    // extinguished.
    let mut episodes: Vec<(f32, f32)> = Vec::new();
    let mut active_fires = 0i32;
    let mut episode_start: Option<f32> = None;
    let mut last_t = 0.0f32;
    for (t, delta) in &fire_events {
        last_t = *t;
        let was_burning = active_fires > 0;
        active_fires = (active_fires + delta).max(0);
        if !was_burning && active_fires > 0 {
            episode_start = Some(*t);
        } else if was_burning && active_fires == 0 {
            if let Some(start) = episode_start.take() {
                episodes.push((start, *t));
            }
        }
    }
    if let Some(start) = episode_start {
        episodes.push((start, last_t));
    }

    // A DCP that fires while a sustained episode is burning covers it. A
    // sustained episode is one long enough that dousing was warranted.
    let sustained = episodes.iter().filter(|(s, e)| e - s >= PROMPT_DCP_WINDOW_S).count();
    let covers = episodes.iter().filter(|(s, e)| {
        e - s >= PROMPT_DCP_WINDOW_S
            && dcp_clocks.iter().any(|&c| c >= s - 2.0 && c <= e + 2.0)
    }).count();
    let dcp_prompt_ratio = if sustained == 0 {
        1.0
    } else {
        (covers as f32 / sustained as f32).clamp(0.0, 1.0)
    };

    // Server potential damage (agro) by weapon, and its total.
    let mut potential_by_weapon: HashMap<String, f32> = HashMap::new();
    let mut potential_total = 0.0f32;
    for entry in report.self_damage_stats() {
        if entry.category.known().copied() == Some(DamageStatCategory::Agro) {
            let weapon = entry
                .weapon
                .known()
                .map(|w| w.name().to_owned())
                .or_else(|| entry.weapon.unknown().cloned())
                .unwrap_or_else(|| "?".to_owned());
            let amount = entry.total as f32;
            *potential_by_weapon.entry(weapon).or_default() += amount;
            potential_total += amount;
        }
    }
    let mut potential_weapons: Vec<WeaponPotential> =
        potential_by_weapon.into_iter().map(|(weapon, potential)| WeaponPotential { weapon, potential }).collect();
    potential_weapons.sort_by(|a, b| b.potential.partial_cmp(&a.potential).unwrap_or(std::cmp::Ordering::Equal));

    // Incoming hits: hostile shells that the nearest-ship resolver landed on the
    // self ship. Reuses `hit_value`'s enemy-only rule and its damage estimate.
    let enemies: std::collections::HashSet<EntityId> = report
        .players()
        .iter()
        .filter(|p| p.relation().is_enemy())
        .map(|p| p.initial_state().entity_id())
        .collect();
    let info = hit_value::victim_info(report, params);

    let mut hits: Vec<IncomingHit> = Vec::new();
    let mut sources: HashMap<EntityId, IncomingSource> = HashMap::new();
    let mut zone_damage: HashMap<String, f32> = HashMap::new();
    let mut shell_hits_taken = 0u32;
    let mut unidentified_hits = 0u32;
    let mut saturating_hits = 0u32;
    let mut taken_damage = 0.0f32;
    let mut biggest_hit = 0.0f32;

    for hit in report
        .hit_history()
        .iter()
        .filter(|h| h.hit.owner_id != self_entity && h.victim_entity_id == self_entity)
    {
        let owner = hit.hit.owner_id;
        if !enemies.contains(&owner) {
            continue;
        }
        let Some(shell) = hit_value::shell_for_hit(hit, params) else {
            unidentified_hits += 1;
            continue;
        };
        let Some(pose) = hit.victim_pose else {
            unidentified_hits += 1;
            continue;
        };
        let Some(origin) = hit_value::shot_origin(hit) else {
            unidentified_hits += 1;
            continue;
        };
        let impact = hit.hit.position.0;
        let incoming = hit_value::origin_to_impact(hit);
        let strike_angle_deg = belt_strike_angle(incoming, pose.yaw, pose.pitch, pose.roll);
        let angle_on_bow_deg = angle_on_bow(origin, impact, pose.yaw, pose.pitch, pose.roll);
        let hit_type = hit
            .hit
            .hit_type
            .shell_hit
            .known()
            .map(|s| s.name().to_owned())
            .unwrap_or_else(|| "UNKNOWN".to_owned());
        let zone = hit_value::zone_for_hit(hit);
        let hitloc = hit_value::victim_hit_location(report, params, self_entity, &zone);
        let zone_mm = hitloc.as_ref().map(|hl| hl.thickness());
        let zone_max_hp = hitloc.as_ref().map(|hl| hl.max_hp()).unwrap_or(0.0);
        let zone_damage_so_far = zone_damage.get(&zone).copied().unwrap_or(0.0);
        let saturated = zone != "citadel" && zone_max_hp > 0.0 && zone_damage_so_far >= zone_max_hp;
        let base = hit_value::estimate_damage(&shell, &hit_type, zone_mm.as_ref());
        // A saturated (exhausted) zone absorbs only marginal damage (~1/6);
        // the citadel zone never saturates, so it is left at full rate.
        let est = if saturated { base / 6.0 } else { base };
        *zone_damage.entry(zone.clone()).or_insert(0.0) += est;
        shell_hits_taken += 1;
        taken_damage += est;
        biggest_hit = biggest_hit.max(est);
        if saturated {
            saturating_hits += 1;
        }

        let (attacker, attacker_class) = match info.get(&owner) {
            Some((id, name, class)) => (hit_value::ship_zh(id, name), class.clone()),
            None => ("?".to_owned(), "unknown".to_owned()),
        };
        let ammo = hit_value::ammo_str(&shell.ammo_type).to_owned();
        hits.push(IncomingHit {
            clock_s: elapsed(report, hit.clock),
            attacker: attacker.clone(),
            attacker_class: attacker_class.clone(),
            ammo: ammo.clone(),
            hit_type: hit_type.clone(),
            ribbon: hit_value::ribbon_for(&hit_type),
            zone: zone.clone(),
            estimated_damage: est,
            strike_angle_deg,
            angle_on_bow_deg,
            saturated,
            zone_max_hp,
        });

        let src = sources.entry(owner).or_insert(IncomingSource {
            attacker: attacker.clone(),
            attacker_class: attacker_class.clone(),
            hits: 0,
            damage_estimated: 0.0,
            biggest_hit: 0.0,
            ammo: Vec::new(),
            zones: Vec::new(),
        });
        src.hits += 1;
        src.damage_estimated += est;
        src.biggest_hit = src.biggest_hit.max(est);
        if !src.ammo.contains(&ammo) {
            src.ammo.push(ammo);
        }
        if !src.zones.contains(&zone) {
            src.zones.push(zone);
        }
    }
    hits.sort_by(|a, b| a.clock_s.partial_cmp(&b.clock_s).unwrap_or(std::cmp::Ordering::Equal));
    let mut sources: Vec<IncomingSource> = sources.into_values().collect();
    sources.sort_by(|a, b| b.damage_estimated.partial_cmp(&a.damage_estimated).unwrap_or(std::cmp::Ordering::Equal));

    // Death timing.
    let died = report.deaths_by_victim().contains_key(&self_entity);
    let death_clock_s = report.deaths_by_victim().get(&self_entity).map(|&c| elapsed(report, c));
    let played_duration = report.played_duration();
    let death_share_of_match = match (died, death_clock_s, played_duration) {
        (true, Some(clock), Some(played)) if played > 0.0 => Some((clock / played).clamp(0.0, 1.0)),
        // Died but no playable duration (recording cut short): the share is
        // unknown, and the survival factor falls to the "died" baseline.
        (true, Some(_), _) => None,
        _ => None,
    };

    let avoidance = if potential_total > 0.0 {
        (1.0 - (taken_damage / potential_total)).clamp(0.0, 1.0)
    } else if taken_damage <= 0.0 {
        1.0
    } else {
        0.0
    };
    let survival = if died {
        death_share_of_match.unwrap_or(0.0)
    } else {
        1.0
    };
    let self_rescue = if fires_lit == 0 {
        1.0
    } else if !has_dcp {
        // No DCP on the ship: the fire was not a miscallable moment-of-play
        // mistake, it is a resource/build limit. Baseline rather than zero.
        0.6
    } else {
        dcp_prompt_ratio
    };
    let score = (0.40 * avoidance + 0.35 * survival + 0.25 * self_rescue).clamp(0.0, 1.0);
    let survival_score = (score * 100.0).round() as u32;

    let flame_note = if fires_lit == 0 && !burn_observed {
        "burningFlags 未复制, 着火计数未知, 不做自欺归因".to_owned()
    } else if fires_lit == 0 {
        "未观测到着火".to_owned()
    } else if has_dcp {
        format!("共起火 {fires_lit} 次(持续≥{PROMPT_DCP_WINDOW_S:.0}s 的火段 {sustained} 个), DCP 及时覆盖 {covers} 个")
    } else {
        format!("共起火 {fires_lit} 次(持续火段 {sustained} 个), 该舰无 DCP(资源限制, 非操作失误)")
    };

    let mut conclusions: Vec<String> = Vec::new();
    conclusions.push(flame_note);
    conclusions.push("伤害为 wows_shell 社区估伤近似, 非客户端精确值".to_owned());
    if potential_total > 0.0 {
        let taken_share = (taken_damage / potential_total).clamp(0.0, 1.0);
        let share_pct = ret_pct(taken_share);
        if taken_share < 0.25 {
            conclusions.push(format!("被瞄准潜在伤害 {potential_total:.0}, 实际吃伤 {taken_damage:.0}(占比 {share_pct}), 规避/隐蔽良好"));
        } else if taken_share > 0.55 {
            conclusions.push(format!("被瞄准潜在伤害 {potential_total:.0}, 实际吃伤 {taken_damage:.0}(占比 {share_pct}); 高承受可能是集火/团队卖点, 也可能是暴露"));
        } else {
            conclusions.push(format!("被瞄准潜在伤害 {potential_total:.0}, 实际吃伤 {taken_damage:.0}(占比 {share_pct})"));
        }
    } else if taken_damage <= 0.0 {
        conclusions.push("未被敌舰瞄准(agro=0)且零吃伤; 生存分高不代表有输出".to_owned());
    }
    if died {
        let share = death_share_of_match
            .map(|s| format!("约为对局 {} 处死亡", ret_pct(s)))
            .unwrap_or_else(|| "死亡时刻无法换算".to_owned());
        conclusions.push(format!("确认死亡(死于 {share}); 死亡原因需事件级/S3 佐证"));
    } else {
        conclusions.push("整局存活".to_owned());
    }
    if unidentified_hits > 0 {
        conclusions.push(format!("{unidentified_hits} 发命中无法匹配弹道/鱼雷, 未计入伤害"));
    }
    conclusions.push("进水/濒死状态缺 HP 与位置时间线(属 S2/S3), S1 未做暴露/走位归因".to_owned());
    if saturating_hits > 0 {
        conclusions.push(format!("{saturating_hits} 发命中已饱和分区, 按 ~1/6 边际伤害计入"));
    } else if taken_damage > 0.0 {
        conclusions.push(
            "分区饱和未计入(该构建 hit_locations 可能未启用): 估伤为上限, 实际吃伤可能更低".to_owned(),
        );
    }

    let grade = grade_for(survival_score);
    let verdict = format!(
        "规避 {:.0}% / 存活 {:.0}% / 自救 {:.0}% -> {grade}",
        avoidance * 100.0,
        survival * 100.0,
        self_rescue * 100.0
    );

    SurvivalProfile {
        self_ship,
        self_class,
        self_max_hp,
        map: report.map_name().to_owned(),
        game_mode: report.game_mode().to_owned(),
        match_group: report.match_group().to_owned(),
        version: {
            let v = report.version();
            format!("{}.{}.{}.{}", v.major, v.minor, v.patch, v.build_number().unwrap_or(0))
        },
        result: match report.battle_result() {
            Some(wows_replays::analyzer::battle_controller::BattleResult::Win(_)) => "win".to_owned(),
            Some(wows_replays::analyzer::battle_controller::BattleResult::Loss(_)) => "loss".to_owned(),
            Some(wows_replays::analyzer::battle_controller::BattleResult::Draw) => "draw".to_owned(),
            None => "unknown".to_owned(),
        },
        finish_type: report
            .finish_type()
            .map(|ft| ft.known().map(|f| f.name().to_owned()).or_else(|| ft.unknown().cloned()).unwrap_or_else(|| "?".to_owned()))
            .unwrap_or_else(|| "?".to_owned()),
        max_duration_s: report.max_duration(),
        played_duration_s: played_duration,
        potential_damage: potential_total,
        potential_by_weapon: potential_weapons,
        taken_damage_estimated: taken_damage,
        taken_frac_of_potential: if potential_total > 0.0 { (taken_damage / potential_total).clamp(0.0, 1.0) } else { 0.0 },
        avoidance_ratio: avoidance,
        // Not clamped: >1.0 means the player healed more than once (Repair
        // Party), surviving more than their max HP in raw damage.
        taken_frac_of_hp: self_max_hp.map_or(0.0, |hp| if hp > 0.0 { taken_damage / hp } else { 0.0 }),
        shell_hits_taken,
        unidentified_hits,
        saturating_hits,
        biggest_hit,
        fires_lit: if burn_observed { Some(fires_lit) } else { None },
        burn_observed,
        flood_status: "unknown".to_owned(),
        has_dcp,
        dcp_charges: {
            let charges = dcp_charges;
            (charges != u32::MAX).then_some(charges)
        },
        dcp_activations,
        has_repair_party,
        repair_party_activations,
        smoke_activations,
        fires_covered: covers as u32,
        sustained_fires: sustained as u32,
        dcp_prompt_ratio,
        died,
        death_clock_s,
        death_share_of_match,
        survival_score,
        grade: grade.to_owned(),
        verdict,
        conclusions,
        score_breakdown: ScoreBreakdown {
            avoidance,
            survival,
            self_rescue,
            avoidance_weight: 0.40,
            survival_weight: 0.35,
            self_rescue_weight: 0.25,
            score: survival_score as f32,
        },
        hits,
        sources,
    }
}

fn ret_pct(v: f32) -> String {
    format!("{:.0}%", v * 100.0)
}

/// Render a human-readable S1 report for the recording player.
pub fn render(report: &BattleReport, params: &dyn GameParamProvider) -> String {
    let p = assess(report, params);
    let mut s = String::new();
    s.push_str(&format!(
        "=== 生存画像 S1: {} ({}) ===\n",
        p.self_ship,
        p.self_class
    ));
    s.push_str(&format!(
        "[{}] {} t={} / {}s, result={}, finish={}\n",
        p.map,
        p.game_mode,
        p.played_duration_s.map(|d| format!("{d:.0}")).unwrap_or_else(|| "?".to_owned()),
        p.max_duration_s,
        p.result,
        p.finish_type,
    ));
    s.push_str(&format!(
        "\n生存分 {} ({})  {}\n",
        p.survival_score,
        p.grade,
        p.verdict
    ));
    s.push_str(&format!(
        "  潜在伤害(agro) {:.0}, 实际吃伤(估) {:.0}, 承受比 {:.0}%, 规避 {:.0}%",
        p.potential_damage,
        p.taken_damage_estimated,
        p.taken_frac_of_potential * 100.0,
        p.avoidance_ratio * 100.0
    ));
    if p.self_max_hp.is_some() {
        s.push_str(&format!("; 占最大HP {:.0}%", p.taken_frac_of_hp * 100.0));
    }
    s.push('\n');
    s.push_str(&format!(
        "  被打命中(壳) {} 发, 未识别 {} 发, 饱和区 {} 发, 最大单发伤害 {:.0}\n",
        p.shell_hits_taken,
        p.unidentified_hits,
        p.saturating_hits,
        p.biggest_hit
    ));
    s.push_str(&format!(
        "  DCP {}次(装{}), 维修小组 {}次, 烟雾 {}次; 起火 {}; DCP覆盖 {} / 持续火段 {} (比例{})\n",
        p.dcp_activations,
        p.dcp_charges.map(|c| c.to_string()).unwrap_or_else(|| "无限".to_owned()),
        p.repair_party_activations,
        p.smoke_activations,
        p.fires_lit.map(|f| f.to_string()).unwrap_or_else(|| "未知".to_owned()),
        p.fires_covered,
        p.sustained_fires,
        format!("{:.0}%", p.dcp_prompt_ratio * 100.0)
    ));
    if p.died {
        let share = p.death_share_of_match.map(|v| format!("{:.0}%", v * 100.0)).unwrap_or_else(|| "?".to_owned());
        s.push_str(&format!(
            "  死亡于 t={}s (对局 {})\n",
            p.death_clock_s.map(|c| format!("{c:.0}")).unwrap_or_else(|| "?".to_owned()),
            share
        ));
    } else {
        s.push_str("  整局存活\n");
    }

    s.push_str("\n-- 主要承伤来源 --\n");
    if p.sources.is_empty() {
        s.push_str("  无\n");
    } else {
        for src in &p.sources {
            s.push_str(&format!(
                "  {}({}) {}发 {:.0}伤 最大{:.0} [{}] {}\n",
                src.attacker,
                src.attacker_class,
                src.hits,
                src.damage_estimated,
                src.biggest_hit,
                src.ammo.join("/"),
                src.zones.join("/")
            ));
        }
    }

    s.push_str("\n-- 命中时间线 --\n");
    if p.hits.is_empty() {
        s.push_str("  无\n");
    } else {
        for h in &p.hits {
            s.push_str(&format!(
                "  t={:.0}s {}({}) {} {} {} {:.0}伤 命中角{:.0} 舷角{:.0}{}\n",
                h.clock_s,
                h.attacker,
                h.zone,
                h.ammo,
                h.ribbon,
                h.hit_type,
                h.estimated_damage,
                h.strike_angle_deg,
                h.angle_on_bow_deg,
                if h.saturated { " (饱和)" } else { "" }
            ));
        }
    }

    s.push_str("\n-- 结论 --\n");
    for c in &p.conclusions {
        s.push_str(&format!("  - {}\n", c));
    }
    s
}
