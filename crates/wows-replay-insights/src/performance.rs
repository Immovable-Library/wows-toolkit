//! Whole-match performance: the survival profile (S1-S4) and the output-end
//! assessment merged into a single one-page report, so V and D are read
//! together rather than as two separate dumps.

use std::collections::HashMap;

use wows_battle_world::report::BattleReport;
use wows_replays::types::EntityId;
use wowsunpack::game_params::types::GameParamProvider;

use crate::hull_dim::HullData;
use crate::hit_value;
use crate::hit_value::VictimLesson;
use crate::survival;
use crate::survival::SurvivalProfile;

/// The output-end summary aggregated for the whole match.
#[cfg_attr(feature = "serde", derive(serde::Serialize))]
#[derive(Clone, Debug)]
pub struct OutputSummary {
    /// Estimated damage dealt by the recording player's resolved main-battery
    /// hits on enemies.
    pub estimated_damage: f32,
    /// Number of fully-resolved hits.
    pub hits: u32,
    /// Self-fired-on-enemy hits that could not be assessed (no shell, no pose,
    /// not main battery, etc.).
    pub excluded: u32,
    /// Total volleys fired.
    pub volleys: u32,
    /// Volleys that landed at least one shell (the ones the score is over).
    pub scored_volleys: u32,
    /// Mean 0-100 volley value over the volleys that hit.
    pub avg_volley_score: Option<f32>,
    /// Best 0-100 volley value.
    pub best_volley_score: u32,
    /// Hits that struck an already-saturated exact zone (marginal ~1/6 damage).
    pub saturating_hits: u32,
    /// Per-target lessons (hits, overpens, ammo-switch advice).
    pub lessons: Vec<VictimLesson>,
}

/// The whole-match performance record.
#[cfg_attr(feature = "serde", derive(serde::Serialize))]
#[derive(Clone, Debug)]
pub struct WholeMatch {
    pub survival: SurvivalProfile,
    pub output: OutputSummary,
}

/// Merge the survival profile (S1-S4) with the output-end assessment.
pub fn assess_whole(
    report: &BattleReport,
    params: &dyn GameParamProvider,
    hull: Option<&HashMap<EntityId, HullData>>,
) -> WholeMatch {
    let survival = survival::assess(report, params, hull);
    let outcome = hit_value::assess(report, params, hull);
    let volleys = hit_value::analyze_volleys(report, params, hull);
    let lessons = hit_value::summarize(report, params, hull);

    let mut estimated_damage = 0.0f32;
    let mut saturating_hits = 0u32;
    for a in &outcome.assessments {
        estimated_damage += a.estimated_damage;
        if a.saturated {
            saturating_hits += 1;
        }
    }
    let scored: Vec<f32> = volleys.iter().filter(|v| v.shells_hit > 0).map(|v| v.score as f32).collect();
    let avg_volley_score = if scored.is_empty() {
        None
    } else {
        Some(scored.iter().sum::<f32>() / scored.len() as f32)
    };
    let best_volley_score = volleys.iter().filter(|v| v.shells_hit > 0).map(|v| v.score).max().unwrap_or(0);

    WholeMatch {
        survival,
        output: OutputSummary {
            estimated_damage,
            hits: outcome.assessments.len() as u32,
            excluded: outcome.excluded,
            volleys: volleys.len() as u32,
            scored_volleys: scored.len() as u32,
            avg_volley_score,
            best_volley_score,
            saturating_hits,
            lessons,
        },
    }
}

/// Render a one-page whole-match performance report.
pub fn render_whole(whole: &WholeMatch) -> String {
    let s = &whole.survival;
    let o = &whole.output;
    let mut out = String::new();
    out.push_str(&format!(
        "=== 整局表现 {}（{}）===\n地图 {} | 模式 {} | 结果 {} | 时长 {}/{}s\n",
        s.self_ship,
        s.self_class,
        s.map,
        s.game_mode,
        s.result,
        s.played_duration_s.map(|d| format!("{d:.0}")).unwrap_or_else(|| "?".to_owned()),
        s.max_duration_s,
    ));

    out.push_str("\n-- 输出端 --\n");
    out.push_str(&format!(
        "  主炮命中 {} 发（未评估 {}）估伤 {:.0}；仅命中轮均分 {}/100（打中 {}/{} 轮，最高 {}）\n",
        o.hits,
        o.excluded,
        o.estimated_damage,
        o.avg_volley_score.map(|v| format!("{v:.0}")).unwrap_or_else(|| "?".to_owned()),
        o.scored_volleys,
        o.volleys,
        if o.scored_volleys > 0 { o.best_volley_score.to_string() } else { "?".to_owned() },
    ));
    if o.saturating_hits > 0 {
        out.push_str(&format!(
            "  我方命中敌方饱和区 {} 发（约 1/6 边际伤害，需换区域瞄准）\n",
            o.saturating_hits
        ));
    }
    out.push_str("  分区：有船壳/splash 数据用精确区，否则固定阈值（deck/super 6/14m）；估伤为 wows_shell 社区近似\n");
    for l in &o.lessons {
        out.push_str(&format!(
            "  - {}（{}）命中{} 过穿{} 未击穿{} 跳弹{} 核心{} 换弹建议{}\n",
            l.victim_ship,
            l.victim_class,
            l.hits,
            l.overpen,
            l.no_pen,
            l.bounce,
            l.citadel,
            l.switch_calls,
        ));
    }

    out.push_str("\n-- 生存端（S1-S4）--\n");
    out.push_str(&format!(
        "  生存分 {}（{}）{}；规避 {}；吃伤/潜在 {:.0}/{:.0}；非炮弹潜在 {:.0}\n",
        s.survival_score.map(|v| v.to_string()).unwrap_or_else(|| "未知".to_owned()),
        s.grade.as_deref().unwrap_or("未知"),
        s.verdict,
        s.avoidance_ratio.map(|v| format!("{:.0}%", v * 100.0)).unwrap_or_else(|| "?".to_owned()),
        s.taken_damage_estimated,
        s.shell_potential_damage,
        s.non_shell_potential_damage,
    ));
    out.push_str(&format!(
        "  着火 {} 次 DCP覆盖 {}/{}；DCP使用 {}；修船 {} 次；烟 {} 次\n",
        s.fires_lit.map(|v| v.to_string()).unwrap_or_else(|| "?".to_owned()),
        s.fires_covered,
        s.sustained_fires,
        s.dcp_activations,
        s.repair_party_activations,
        s.smoke_activations,
    ));
    out.push_str(&format!(
        "  暴露：12km内占比 {}，近敌均 {}m，approach {} kiting {}（掩体未建模）；HP：最低 {} 结束 {} 濒死 {}；\n",
        s.exposure.exposed_time_frac.map(|v| format!("{:.0}%", v * 100.0)).unwrap_or_else(|| "?".to_owned()),
        s.exposure.nearest_enemy_avg_m.map(|v| format!("{v:.0}")).unwrap_or_else(|| "?".to_owned()),
        s.exposure.approach_frac.map(|v| format!("{:.0}%", v * 100.0)).unwrap_or_else(|| "?".to_owned()),
        s.exposure.kiting_frac.map(|v| format!("{:.0}%", v * 100.0)).unwrap_or_else(|| "?".to_owned()),
        s.hp_timeline.min_health_frac.map(|v| format!("{:.0}%", v * 100.0)).unwrap_or_else(|| "?".to_owned()),
        s.hp_timeline.end_health_frac.map(|v| format!("{:.0}%", v * 100.0)).unwrap_or_else(|| "?".to_owned()),
        s.hp_timeline.near_death.map(|v| if v { "是" } else { "否" }).unwrap_or("?"),
    ));
    out.push_str(&format!("  生存->输出耦合：{}\n", s.output_coupling.coupling_note));

    out.push_str("\n-- 结论 --\n");
    for c in &s.conclusions {
        out.push_str(&format!("  - {c}\n"));
    }
    out.push_str(&format!(
        "  综合：{} 主炮估伤 {:.0} / 仅命中轮均 {}；生存 {}。\n",
        s.self_ship,
        o.estimated_damage,
        o.avg_volley_score.map(|v| format!("{v:.0}")).unwrap_or_else(|| "?".to_owned()),
        s.survival_score.map(|v| format!("{}分({})", v, s.grade.as_deref().unwrap_or("?"))).unwrap_or_else(|| "未知".to_owned()),
    ));
    out
}
