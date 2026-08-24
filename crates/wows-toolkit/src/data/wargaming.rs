//! Client for the World of Warships Wargaming public API.
//!
//! Covers `wows/account/list` (name to account-id resolution, whose search is
//! fuzzy) and `wows/account/info` (solo Operations statistics for a batch of
//! account ids).

use std::collections::HashMap;
use std::sync::Arc;

use serde::Deserialize;
use serde::Serialize;
use wows_replays::types::AccountId;
use wows_replays::types::GameParamId;

use crate::data::match_stats::Region;

const API_PATH: &str = "/wows/account/list/";
const ACCOUNT_INFO_PATH: &str = "/wows/account/info/";
const SHIP_STATS_PATH: &str = "/wows/ships/stats/";
/// Columns kept when reading per-ship Operations stats. The endpoint answers
/// every owned ship, so the column list stays minimal and zero-battle ships
/// are dropped by the parser.
const SHIP_STATS_FIELDS: &str = "ship_id,oper_solo.battles,oper_solo.wins,oper_solo.losses,oper_solo.survived_wins,oper_solo.survived_battles,oper_solo.wins_by_tasks,oper_solo.xp";

/// Wargaming application id used by the toolkit. This is the public
/// developer-portal application id, not a secret.
const APPLICATION_ID: &str = "4abd85d2d22608f74b646410ef7e3a16";

/// One account returned by `wows/account/list`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WargamingAccount {
    pub account_id: AccountId,
    pub nickname: String,
}

/// Solo Operations statistics, the shape under `statistics.oper_solo`.
///
/// Operations report win/loss, survival, XP and per-task wins only. The WG
/// API exposes no damage or PR for this mode, so win rate is derived from
/// `wins / battles` by the caller.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WowsOperationsStats {
    #[serde(default)]
    pub xp: Option<i64>,
    #[serde(default)]
    pub battles: Option<i64>,
    #[serde(default)]
    pub survived_wins: Option<i64>,
    #[serde(default)]
    pub survived_battles: Option<i64>,
    #[serde(default)]
    pub wins: Option<i64>,
    #[serde(default)]
    pub losses: Option<i64>,
    /// Wins grouped by task difficulty, keyed `"0"` through `"5"`.
    #[serde(default)]
    pub wins_by_tasks: HashMap<String, i64>,
}

impl WowsOperationsStats {
    /// Win rate as a percentage, or `None` with no battles.
    pub fn win_rate(&self) -> Option<f64> {
        let battles = self.battles.unwrap_or(0);
        if battles <= 0 {
            return None;
        }
        let wins = self.wins.unwrap_or(0);
        Some(100.0 * wins as f64 / battles as f64)
    }

    /// Five-star rate as a percentage over all battles, or `None` with no
    /// battles. A five-star game is a win whose task map counts the `"5"`
    /// key, so this divides those wins by the battle total.
    pub fn five_star_rate(&self) -> Option<f64> {
        let battles = self.battles.unwrap_or(0);
        if battles <= 0 {
            return None;
        }
        let five_star_wins = self.wins_by_tasks.get("5").copied().unwrap_or(0);
        Some(100.0 * five_star_wins as f64 / battles as f64)
    }

    /// Average XP per battle, or `None` with no battles.
    pub fn avg_xp(&self) -> Option<f64> {
        let battles = self.battles.unwrap_or(0);
        if battles <= 0 {
            return None;
        }
        let xp = self.xp.unwrap_or(0);
        Some(xp as f64 / battles as f64)
    }
}

/// The account-list response body.
#[derive(Debug, Clone, Deserialize)]
struct AccountListResponse {
    status: String,
    #[serde(default)]
    data: Vec<WargamingAccount>,
    #[serde(default)]
    error: Option<WargamingApiErrorBody>,
}

#[derive(Debug, Clone, Deserialize)]
struct WargamingApiErrorBody {
    message: String,
}

/// The account-info response body. `data` is keyed by account id string, not a
/// list, matching this endpoint's map shape.
#[derive(Debug, Clone, Deserialize)]
struct AccountInfoResponse {
    status: String,
    #[serde(default)]
    data: HashMap<String, WowsAccountInfo>,
    #[serde(default)]
    error: Option<WargamingApiErrorBody>,
}

#[derive(Debug, Clone, Deserialize)]
struct WowsAccountInfo {
    #[serde(default)]
    statistics: Option<WowsAccountStatistics>,
}

#[derive(Debug, Clone, Deserialize)]
struct WowsAccountStatistics {
    #[serde(default)]
    oper_solo: Option<WowsOperationsStats>,
}

/// The per-ship stats response body. `data` maps an account id to its ship
/// entries, matching the account-scoped map shape even for a single-account
/// request.
#[derive(Debug, Clone, Deserialize)]
struct ShipStatsResponse {
    status: String,
    #[serde(default)]
    data: HashMap<String, Vec<ShipStatsEntry>>,
    #[serde(default)]
    error: Option<WargamingApiErrorBody>,
}

#[derive(Debug, Clone, Deserialize)]
struct ShipStatsEntry {
    ship_id: GameParamId,
    #[serde(default)]
    oper_solo: Option<WowsOperationsStats>,
}

/// Failure modes for the Wargaming account-list lookup.
#[derive(Debug, thiserror::Error)]
pub enum WargamingApiError {
    #[error("Wargaming API request failed: {0}")]
    Request(#[from] reqwest::Error),
    #[error("Wargaming API returned status {status}: {message}")]
    Api { status: String, message: String },
    #[error("Wargaming API response could not be decoded: {0}")]
    Json(#[from] serde_json::Error),
    #[error("search must not be empty")]
    EmptySearch,
}

/// Blocking client for small Wargaming API requests.
#[derive(Clone)]
pub struct WargamingClient {
    http: Arc<reqwest::blocking::Client>,
}

impl WargamingClient {
    pub fn new(proxy: Option<&crate::util::proxy::ProxyConfig>) -> reqwest::Result<Self> {
        // Wargaming errors are carried in the JSON body rather than redirects,
        // so redirects stay disabled like the other blocking API client.
        crate::util::http::blocking_client(reqwest::redirect::Policy::none(), proxy)
            .map(|http| Self { http: Arc::new(http) })
    }

    /// Search the Wargaming account list for `search`.
    ///
    /// `search` is trimmed before use. An empty result set and a fuzzy result
    /// set are both valid outcomes; the returned list preserves API order.
    pub fn search_accounts(&self, region: Region, search: &str) -> Result<Vec<WargamingAccount>, WargamingApiError> {
        let search = search.trim();
        if search.is_empty() {
            return Err(WargamingApiError::EmptySearch);
        }

        let url = format!("{}{API_PATH}", region.wargaming_api_host());
        let response = self
            .http
            .get(url)
            .query(&[("application_id", APPLICATION_ID), ("search", search)])
            .send()?
            .error_for_status()?;
        let bytes = response.bytes()?;
        parse_account_list_response(&bytes)
    }

    /// Return the account whose nickname exactly equals `search`.
    ///
    /// `search` is trimmed first. The comparison is case-insensitive because
    /// the Wargaming account search itself is case-insensitive.
    pub fn find_exact_account(
        &self,
        region: Region,
        search: &str,
    ) -> Result<Option<WargamingAccount>, WargamingApiError> {
        let search = search.trim();
        if search.is_empty() {
            return Err(WargamingApiError::EmptySearch);
        }
        Ok(exact_account(self.search_accounts(region, search)?, search))
    }

    /// Look up several exact nicknames in one Wargaming `type=exact` request.
    ///
    /// Empty or whitespace-only names are ignored. An empty request returns an
    /// empty result rather than an error, matching the auto-query path where a
    /// roster may have no eligible names.
    pub fn find_exact_accounts(
        &self,
        region: Region,
        searches: &[String],
    ) -> Result<Vec<WargamingAccount>, WargamingApiError> {
        let Some(search) = exact_search_param(searches) else {
            return Ok(Vec::new());
        };

        let url = format!("{}{API_PATH}", region.wargaming_api_host());
        let response = self
            .http
            .post(url)
            .form(&[("application_id", APPLICATION_ID), ("search", search.as_str()), ("type", "exact")])
            .send()?
            .error_for_status()?;
        let bytes = response.bytes()?;
        parse_account_list_response(&bytes)
    }

    /// Fetch solo Operations statistics for a batch of account ids.
    ///
    /// Empty account ids return an empty map. Entries whose profile is hidden
    /// or who never played Operations are omitted rather than treated as an
    /// error, so one missing player cannot cost the rest of the roster.
    pub fn fetch_operations_stats(
        &self,
        region: Region,
        account_ids: &[AccountId],
    ) -> Result<HashMap<AccountId, WowsOperationsStats>, WargamingApiError> {
        let Some(joined) = account_ids_param(account_ids) else {
            return Ok(HashMap::new());
        };

        let url = format!("{}{ACCOUNT_INFO_PATH}", region.wargaming_api_host());
        let response = self
            .http
            .post(url)
            .form(&[
                ("application_id", APPLICATION_ID),
                ("account_id", joined.as_str()),
                ("extra", "statistics.oper_solo"),
                ("fields", "-statistics.pvp"),
            ])
            .send()?
            .error_for_status()?;
        let bytes = response.bytes()?;
        parse_account_info_response(&bytes)
    }

    /// Fetch solo Operations stats for one account, keyed by ship.
    ///
    /// The endpoint returns every ship the account owns, so ships with no
    /// Operations battles are dropped and the map holds only ships that have
    /// played Operations.
    pub fn fetch_ship_operations_stats(
        &self,
        region: Region,
        account_id: AccountId,
    ) -> Result<HashMap<GameParamId, WowsOperationsStats>, WargamingApiError> {
        let account_id_param = account_id.raw().to_string();
        let url = format!("{}{SHIP_STATS_PATH}", region.wargaming_api_host());
        let response = self
            .http
            .post(url)
            .form(&[
                ("application_id", APPLICATION_ID),
                ("account_id", account_id_param.as_str()),
                ("extra", "oper_solo"),
                ("fields", SHIP_STATS_FIELDS),
            ])
            .send()?
            .error_for_status()?;
        let bytes = response.bytes()?;
        parse_ship_stats_response(&bytes)
    }
}

/// Parse the JSON body returned by `wows/account/list`.
fn parse_account_list_response(bytes: &[u8]) -> Result<Vec<WargamingAccount>, WargamingApiError> {
    let response: AccountListResponse = serde_json::from_slice(bytes)?;
    if response.status != "ok" {
        return Err(WargamingApiError::Api {
            status: response.status,
            message: response.error.map(|error| error.message).unwrap_or_else(|| "no error message".to_string()),
        });
    }
    Ok(response.data)
}

/// Parse the JSON body returned by `wows/account/info` into Operations stats
/// keyed by account id. Entries with no `oper_solo` block are dropped.
fn parse_account_info_response(bytes: &[u8]) -> Result<HashMap<AccountId, WowsOperationsStats>, WargamingApiError> {
    let response: AccountInfoResponse = serde_json::from_slice(bytes)?;
    if response.status != "ok" {
        return Err(WargamingApiError::Api {
            status: response.status,
            message: response.error.map(|error| error.message).unwrap_or_else(|| "no error message".to_string()),
        });
    }

    let mut by_account = HashMap::new();
    for (key, info) in response.data {
        let Ok(raw) = key.parse::<i64>() else {
            continue;
        };
        let account_id = AccountId(raw);
        if let Some(statistics) = info.statistics.and_then(|stats| stats.oper_solo) {
            by_account.insert(account_id, statistics);
        }
    }
    Ok(by_account)
}

/// Parse the JSON body returned by `wows/ships/stats` into per-ship
/// Operations stats. Ships without an `oper_solo` block or with zero battles
/// are dropped.
fn parse_ship_stats_response(bytes: &[u8]) -> Result<HashMap<GameParamId, WowsOperationsStats>, WargamingApiError> {
    let response: ShipStatsResponse = serde_json::from_slice(bytes)?;
    if response.status != "ok" {
        return Err(WargamingApiError::Api {
            status: response.status,
            message: response.error.map(|error| error.message).unwrap_or_else(|| "no error message".to_string()),
        });
    }

    let mut by_ship = HashMap::new();
    for entries in response.data.into_values() {
        for entry in entries {
            let Some(stats) = entry.oper_solo else {
                continue;
            };
            if stats.battles.unwrap_or(0) <= 0 {
                continue;
            }
            by_ship.insert(entry.ship_id, stats);
        }
    }
    Ok(by_ship)
}

/// Select the exact nickname match from an already-fetched result set.
fn exact_account(accounts: Vec<WargamingAccount>, search: &str) -> Option<WargamingAccount> {
    accounts.into_iter().find(|account| account.nickname.eq_ignore_ascii_case(search))
}

/// Build the comma-separated `search` value for a `type=exact` request.
fn exact_search_param(searches: &[String]) -> Option<String> {
    let joined =
        searches.iter().map(|search| search.trim()).filter(|search| !search.is_empty()).collect::<Vec<_>>().join(",");
    (!joined.is_empty()).then_some(joined)
}

/// Build the comma-separated `account_id` value for an account-info request.
fn account_ids_param(account_ids: &[AccountId]) -> Option<String> {
    let joined = account_ids.iter().map(|id| id.raw().to_string()).collect::<Vec<_>>().join(",");
    (!joined.is_empty()).then_some(joined)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn account(id: i64, nickname: &str) -> WargamingAccount {
        WargamingAccount { account_id: AccountId(id), nickname: nickname.to_string() }
    }

    #[test]
    fn parses_an_ok_account_list() {
        let bytes = br#"{
            "status": "ok",
            "meta": { "count": 1 },
            "data": [
                { "account_id": 503278143, "nickname": "skmon" }
            ]
        }"#;

        let accounts = parse_account_list_response(bytes).expect("account list parses");

        assert_eq!(accounts, vec![account(503_278_143, "skmon")]);
    }

    #[test]
    fn an_api_error_carries_its_message() {
        let bytes = br#"{
            "status": "error",
            "error": { "message": "INVALID_SEARCH" }
        }"#;

        let error = parse_account_list_response(bytes).expect_err("an API error is not a success");

        match error {
            WargamingApiError::Api { status, message } => {
                assert_eq!(status, "error");
                assert_eq!(message, "INVALID_SEARCH");
            }
            other => panic!("expected Api error, got {other:?}"),
        }
    }

    #[test]
    fn exact_match_prefers_the_verbatim_nickname() {
        let accounts = vec![account(1, "skmon"), account(2, "skmonx"), account(3, "SKMON")];

        let matched = exact_account(accounts, "skmon").expect("exact match is present");
        assert_eq!(matched, account(1, "skmon"));
    }

    #[test]
    fn exact_match_accepts_case_difference_but_rejects_fuzzy_results() {
        let accounts = vec![account(2, "skmonx"), account(3, "SKMON")];

        assert_eq!(exact_account(accounts, "skmon"), Some(account(3, "SKMON")));
    }

    #[test]
    fn exact_search_param_joins_names_and_skips_blank_entries() {
        let searches = vec![" uocat ".to_string(), String::new(), "uomouse".to_string()];
        assert_eq!(exact_search_param(&searches).as_deref(), Some("uocat,uomouse"));
    }

    #[test]
    fn exact_search_param_is_none_for_an_empty_roster() {
        let searches = vec![String::new(), "  ".to_string()];
        assert_eq!(exact_search_param(&searches), None);
    }

    #[test]
    fn parses_an_ok_account_info_with_operations_stats() {
        let bytes = br#"{
            "status": "ok",
            "meta": { "count": 2 },
            "data": {
                "502514064": {
                    "account_id": 502514064,
                    "nickname": "uocat",
                    "statistics": {
                        "battles": 27093,
                        "distance": 1248132,
                        "oper_solo": {
                            "xp": 258001,
                            "battles": 111,
                            "survived_wins": 66,
                            "survived_battles": 71,
                            "wins": 99,
                            "losses": 12,
                            "wins_by_tasks": { "2": 2, "3": 4, "4": 21, "5": 72 }
                        }
                    }
                },
                "566060956": {
                    "account_id": 566060956,
                    "nickname": "uomouse",
                    "statistics": {
                        "battles": 40799,
                        "oper_solo": null
                    }
                }
            }
        }"#;

        let stats = parse_account_info_response(bytes).expect("account info parses");

        assert_eq!(stats.len(), 1, "the null oper_solo entry is omitted");
        let uocat = &stats[&AccountId(502_514_064)];
        assert_eq!(uocat.battles, Some(111));
        assert_eq!(uocat.wins, Some(99));
        assert_eq!(uocat.losses, Some(12));
        assert_eq!(uocat.survived_battles, Some(71));
        assert_eq!(uocat.survived_wins, Some(66));
        assert_eq!(uocat.xp, Some(258_001));
        assert_eq!(uocat.wins_by_tasks.get("5"), Some(&72));
    }

    #[test]
    fn an_account_info_error_carries_its_message() {
        let bytes = br#"{
            "status": "error",
            "error": { "message": "INVALID_APPLICATION_ID" }
        }"#;

        let error = parse_account_info_response(bytes).expect_err("an API error is not a success");

        match error {
            WargamingApiError::Api { status, message } => {
                assert_eq!(status, "error");
                assert_eq!(message, "INVALID_APPLICATION_ID");
            }
            other => panic!("expected Api error, got {other:?}"),
        }
    }

    #[test]
    fn account_ids_param_joins_ids_and_is_none_when_empty() {
        assert_eq!(account_ids_param(&[AccountId(1), AccountId(20), AccountId(300)]).as_deref(), Some("1,20,300"));
        assert_eq!(account_ids_param(&[]), None);
    }

    fn ops_stats(battles: i64, wins: i64, xp: i64, five_star: i64) -> WowsOperationsStats {
        WowsOperationsStats {
            xp: Some(xp),
            battles: Some(battles),
            survived_wins: Some(0),
            survived_battles: Some(0),
            wins: Some(wins),
            losses: Some(0),
            wins_by_tasks: if five_star > 0 { HashMap::from([("5".to_string(), five_star)]) } else { HashMap::new() },
        }
    }

    #[test]
    fn operations_metrics_derive_from_raw_fields() {
        let stats = ops_stats(1000, 890, 2_200_000, 500);

        assert_eq!(stats.win_rate(), Some(89.0));
        assert_eq!(stats.five_star_rate(), Some(50.0));
        assert_eq!(stats.avg_xp(), Some(2200.0));
    }

    #[test]
    fn operations_metrics_are_none_without_battles() {
        let stats = ops_stats(0, 0, 1000, 0);

        assert_eq!(stats.win_rate(), None);
        assert_eq!(stats.five_star_rate(), None);
        assert_eq!(stats.avg_xp(), None);
    }

    #[test]
    fn parses_an_ok_ship_stats_response_and_drops_zero_battle_ships() {
        let bytes = br#"{
            "status": "ok",
            "meta": { "count": 2 },
            "data": {
                "566060956": [
                    { "ship_id": 3765319664, "oper_solo": { "battles": 0, "xp": 0 } },
                    { "ship_id": 3760142032, "oper_solo": {
                        "xp": 17576,
                        "battles": 8,
                        "survived_wins": 3,
                        "survived_battles": 4,
                        "wins": 6,
                        "losses": 2,
                        "wins_by_tasks": { "4": 1, "5": 5 }
                    } }
                ]
            }
        }"#;

        let stats = parse_ship_stats_response(bytes).expect("ship stats parse");

        assert_eq!(stats.len(), 1, "the zero-battle ship is dropped");
        let ship = &stats[&GameParamId::from(3_760_142_032u64)];
        assert_eq!(ship.battles, Some(8));
        assert_eq!(ship.wins, Some(6));
        assert_eq!(ship.wins_by_tasks.get("5"), Some(&5));
    }
}
