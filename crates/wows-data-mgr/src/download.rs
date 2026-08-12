use std::io::Write;
use std::path::Path;
use std::process::Command;

use rootcause::prelude::*;

use crate::manifest::DepotManifest;
use crate::manifest::GameVersionEntry;

const APP_ID: u32 = 552990;

/// Download game data for a specific build via DepotDownloader.
/// If `entry` is Some, downloads each pinned depot.
/// If `entry` is None, downloads the latest public branch.
pub fn download_build(
    build: u32,
    entry: Option<&GameVersionEntry>,
    data_dir: &Path,
    repo_root: &Path,
    username_override: Option<&str>,
) -> Result<(), Report> {
    // Check DepotDownloader is available
    let dd_cmd = find_depot_downloader()?;

    // Resolve Steam username
    let username = resolve_username(username_override, repo_root)?;

    // Create output directory
    let output_dir = data_dir.join("builds").join(build.to_string());
    std::fs::create_dir_all(&output_dir).attach_with(|| format!("Failed to create {}", output_dir.display()))?;

    // Write filelist for selective download
    let filelist = write_filelist(data_dir)?;

    println!("Downloading build {build} to {}", output_dir.display());

    let download_result: Result<(), Report> = (|| {
        for request in download_requests(entry) {
            let mut cmd = Command::new(&dd_cmd);
            cmd.arg("-app").arg(APP_ID.to_string());

            if let Some(depot) = request {
                cmd.arg("-depot").arg(depot.depot_id.0.to_string());
                cmd.arg("-manifest").arg(&depot.manifest_id.0);
                println!("  depot: {}, manifest: {}", depot.depot_id.0, depot.manifest_id.0);
            } else {
                println!("  (latest public branch)");
            }
            println!();

            cmd.arg("-dir").arg(&output_dir);
            cmd.arg("-filelist").arg(&filelist);
            cmd.arg("-username").arg(&username);
            cmd.arg("-remember-password");

            let status = cmd.status().attach_with(|| "Failed to run DepotDownloader")?;

            if !status.success() {
                if let Some(depot) = request {
                    bail!(
                        "DepotDownloader exited with status {status} for depot {} (manifest {})",
                        depot.depot_id.0,
                        depot.manifest_id.0
                    );
                }
                bail!("DepotDownloader exited with status {status}");
            }
        }
        Ok(())
    })();

    let _ = std::fs::remove_file(&filelist);
    download_result?;

    println!("Download complete.");
    Ok(())
}

fn download_requests(entry: Option<&GameVersionEntry>) -> Vec<Option<&DepotManifest>> {
    let Some(entry) = entry else {
        return vec![None];
    };

    let mut requests = vec![Some(&entry.client)];
    requests.extend([entry.content.as_ref(), entry.localization.as_ref()].into_iter().flatten().map(Some));
    requests
}

fn find_depot_downloader() -> Result<String, Report> {
    // Try common names
    for name in &["DepotDownloader", "depotdownloader"] {
        if Command::new(name).arg("--help").output().is_ok() {
            return Ok(name.to_string());
        }
    }

    // Try dotnet tool
    if let Ok(output) = Command::new("dotnet").args(["tool", "list", "-g"]).output() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        if stdout.to_lowercase().contains("depotdownloader") {
            // dotnet tools are available on PATH when installed globally
            bail!(
                "DepotDownloader is installed as a dotnet tool but not on PATH.\n\
                 Try running: dotnet tool install -g DepotDownloader\n\
                 Then ensure ~/.dotnet/tools is in your PATH."
            );
        }
    }

    bail!(
        "DepotDownloader not found.\n\
         Install it with: dotnet tool install -g DepotDownloader"
    );
}

fn resolve_username(override_username: Option<&str>, repo_root: &Path) -> Result<String, Report> {
    if let Some(u) = override_username {
        return Ok(u.to_string());
    }

    let steam_user_file = repo_root.join(".steam-user");
    if steam_user_file.exists() {
        let user =
            std::fs::read_to_string(&steam_user_file).attach_with(|| "Failed to read .steam-user")?.trim().to_string();
        if !user.is_empty() {
            println!("Using saved Steam username: {user}");
            println!("(delete .steam-user to change)");
            return Ok(user);
        }
    }

    println!("World of Warships requires a Steam account to download.");
    println!("Your username will be saved to .steam-user for future runs.");
    println!();
    print!("Steam username: ");
    std::io::stdout().flush()?;

    let mut input = String::new();
    std::io::stdin().read_line(&mut input)?;
    let username = input.trim().to_string();

    if username.is_empty() {
        bail!("No username provided");
    }

    std::fs::write(&steam_user_file, &username).attach_with(|| "Failed to save .steam-user")?;

    Ok(username)
}

fn write_filelist(data_dir: &Path) -> Result<std::path::PathBuf, Report> {
    let filelist_path = data_dir.join(".filelist.tmp");
    let content = "regex:bin/\\d+/idx/.*\\.idx$\nregex:res_packages/.*\\.pkg$\n";
    std::fs::create_dir_all(data_dir)?;
    std::fs::write(&filelist_path, content)
        .attach_with(|| format!("Failed to write filelist to {}", filelist_path.display()))?;
    Ok(filelist_path)
}

#[cfg(test)]
mod test {
    use super::*;
    use crate::manifest::DepotId;
    use crate::manifest::DepotManifest;
    use crate::manifest::ManifestId;

    fn entry_with_all_depots() -> GameVersionEntry {
        GameVersionEntry {
            version: "15.7.0".to_string(),
            client: DepotManifest::new(DepotId(552993), ManifestId("client".to_string())),
            content: Some(DepotManifest::new(DepotId(552991), ManifestId("content".to_string()))),
            localization: Some(DepotManifest::new(DepotId(552994), ManifestId("localization".to_string()))),
        }
    }

    #[test]
    fn pinned_download_selects_every_available_depot() {
        let entry = entry_with_all_depots();

        assert_eq!(
            download_requests(Some(&entry)),
            vec![Some(&entry.client), entry.content.as_ref(), entry.localization.as_ref()]
        );
    }

    #[test]
    fn historical_download_selects_only_the_client_depot() {
        let entry = GameVersionEntry {
            version: "0.6.13".to_string(),
            client: DepotManifest::new(DepotId(552993), ManifestId("client".to_string())),
            content: None,
            localization: None,
        };

        assert_eq!(download_requests(Some(&entry)), vec![Some(&entry.client)]);
    }

    #[test]
    fn public_download_has_one_unpinned_request() {
        assert_eq!(download_requests(None), vec![None]);
    }
}
