//! Where the app's HTTP clients should send their traffic on a managed network.

/// Where a proxy setting came from, for the startup log line.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProxySource {
    Manual,
    Environment,
    SystemRegistry,
}

/// A proxy to route HTTP through, plus the hosts that must not go through it.
#[derive(Debug, Clone)]
pub struct ProxyConfig {
    pub url: String,
    pub bypass: Vec<String>,
    pub source: ProxySource,
}

/// Accept what a user or the registry might write and produce a URL a client
/// can use. A bare `host:port` is what the Windows proxy dialog stores.
fn normalize_proxy_url(raw: &str) -> Option<String> {
    let raw = raw.trim();
    if raw.is_empty() {
        return None;
    }
    if raw.contains("://") { Some(raw.to_string()) } else { Some(format!("http://{raw}")) }
}

/// Read the `ProxyServer` value, which is either one proxy for every scheme or
/// a `scheme=host:port` list. HTTPS is what this app speaks; its own entry wins,
/// then the HTTP entry, which is the one most such lists actually set.
fn proxy_for_https(value: &str) -> Option<String> {
    if !value.contains('=') {
        return normalize_proxy_url(value);
    }
    let entry = |scheme: &str| {
        value
            .split(';')
            .filter_map(|part| part.split_once('='))
            .find(|(key, _)| key.trim().eq_ignore_ascii_case(scheme))
            .map(|(_, host)| host)
    };
    entry("https").and_then(normalize_proxy_url).or_else(|| entry("http").and_then(normalize_proxy_url))
}

/// Split a `ProxyOverride` list, expanding Windows' `<local>` token into the
/// loopback names a client can actually match on.
fn parse_bypass(value: &str) -> Vec<String> {
    let mut out = Vec::new();
    for entry in value.split(';') {
        let entry = entry.trim();
        if entry.is_empty() {
            continue;
        }
        if entry.eq_ignore_ascii_case("<local>") {
            out.push("localhost".to_string());
            out.push("127.0.0.1".to_string());
            out.push("::1".to_string());
            continue;
        }
        out.push(entry.to_string());
    }
    out
}

/// The proxy this app should use, in precedence order: the user's own setting,
/// then the standard environment variables, then the Windows configuration.
///
/// Returning `None` means direct connections, which is the correct default:
/// most users are not behind a proxy and must not be routed through one.
pub fn resolve_proxy(manual: Option<&str>) -> Option<ProxyConfig> {
    if let Some(url) = manual.and_then(normalize_proxy_url) {
        return Some(ProxyConfig { url, bypass: env_bypass(), source: ProxySource::Manual });
    }
    for var in ["HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"] {
        if let Ok(value) = std::env::var(var)
            && let Some(url) = normalize_proxy_url(&value)
        {
            return Some(ProxyConfig { url, bypass: env_bypass(), source: ProxySource::Environment });
        }
    }
    system_proxy()
}

fn env_bypass() -> Vec<String> {
    ["NO_PROXY", "no_proxy"]
        .iter()
        .find_map(|var| std::env::var(var).ok())
        .map(|value| value.split(',').map(|e| e.trim().to_string()).filter(|e| !e.is_empty()).collect())
        // Neither variable is set: nothing is exempted from the proxy, which is
        // the correct behavior when the user never configured a bypass list.
        .unwrap_or_default()
}

#[cfg(target_os = "windows")]
fn system_proxy() -> Option<ProxyConfig> {
    // HKCU Internet Settings is where the Windows proxy dialog writes, and what
    // WinINET-based clients read. A PAC script (`AutoConfigURL`) is not resolved
    // here; it is logged so a support conversation can identify that case.
    let key =
        windows_registry::CURRENT_USER.open(r"Software\Microsoft\Windows\CurrentVersion\Internet Settings").ok()?;
    if let Ok(pac) = key.get_string("AutoConfigURL")
        && !pac.trim().is_empty()
    {
        tracing::info!("system proxy is configured by a PAC script, which this app does not resolve: {pac}");
    }
    if key.get_u32("ProxyEnable").ok()? != 1 {
        return None;
    }
    let url = proxy_for_https(&key.get_string("ProxyServer").ok()?)?;
    // Absent means the user never set an override list in the proxy dialog, so
    // nothing is exempted.
    let bypass = key.get_string("ProxyOverride").map(|value| parse_bypass(&value)).unwrap_or_default();
    Some(ProxyConfig { url, bypass, source: ProxySource::SystemRegistry })
}

#[cfg(not(target_os = "windows"))]
fn system_proxy() -> Option<ProxyConfig> {
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_bare_host_and_port_becomes_an_http_url() {
        assert_eq!(normalize_proxy_url("proxy.corp:8080").as_deref(), Some("http://proxy.corp:8080"));
        assert_eq!(normalize_proxy_url("http://proxy.corp:8080").as_deref(), Some("http://proxy.corp:8080"));
        assert_eq!(normalize_proxy_url("  ").as_deref(), None);
    }

    #[test]
    fn a_scheme_keyed_setting_prefers_the_https_entry() {
        let value = "ftp=ftp.corp:21;http=proxy.corp:8080;https=secure.corp:8443";
        assert_eq!(proxy_for_https(value).as_deref(), Some("http://secure.corp:8443"));
    }

    #[test]
    fn a_scheme_keyed_setting_falls_back_to_the_http_entry() {
        assert_eq!(proxy_for_https("http=proxy.corp:8080").as_deref(), Some("http://proxy.corp:8080"));
    }

    #[test]
    fn an_empty_https_entry_falls_back_to_the_http_entry() {
        assert_eq!(proxy_for_https("http=proxy.corp:8080;https=").as_deref(), Some("http://proxy.corp:8080"));
    }

    #[test]
    fn a_scheme_keyed_setting_with_no_usable_entry_yields_nothing() {
        assert_eq!(proxy_for_https("ftp=ftp.corp:21"), None);
    }

    #[test]
    fn a_single_value_applies_to_every_scheme() {
        assert_eq!(proxy_for_https("proxy.corp:8080").as_deref(), Some("http://proxy.corp:8080"));
    }

    #[test]
    fn the_bypass_list_is_split_and_local_is_expanded() {
        // Windows writes `<local>` for "any hostname without a dot".
        let bypass = parse_bypass("*.corp.example;10.*;<local>");
        assert!(bypass.contains(&"*.corp.example".to_string()));
        assert!(bypass.contains(&"10.*".to_string()));
        assert!(bypass.contains(&"localhost".to_string()));
        assert!(bypass.contains(&"127.0.0.1".to_string()));
        assert!(!bypass.iter().any(|entry| entry.contains('<')));
    }

    #[test]
    fn an_empty_bypass_list_yields_nothing() {
        assert!(parse_bypass("").is_empty());
        assert!(parse_bypass("   ;;  ").is_empty());
    }
}
