use hsplanner_engine::calc::i18n::tr;
use anyhow::Context as _;
use futures::AsyncReadExt;
use gpui_kit::component::{WindowExt, button::Button};
use gpui_kit::http_client::{
    AsyncBody, HttpClient, HttpRequestExt, RedirectPolicy, Request, Response,
};
use gpui_kit::{prelude::*, *};
use hsplanner_ui::{controls::PlannerControl, theme::TooltipTheme};
use semver::Version;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{path::Path, sync::Arc, time::Duration};

// This fork's own releases. Pointing at upstream would offer the English build
// as an update and, since the installer identity is unchanged, replace the
// Korean one with it.
pub const REPO: &str = "tablet7823-beep/HSPlanner";
pub const USER_AGENT: &str = concat!("HSPlanner/", env!("CARGO_PKG_VERSION"));
// SHA256SUMS identifies releases produced by our packaging pipeline.
//
// The case varies by format: cargo-packager names the macOS bundle after
// `productName` ("HSPlanner_1.1.0_aarch64.dmg") but the NSIS installer after
// `name` ("hsplanner_1.1.0_x64-setup.exe"). Matching this prefix exactly found
// the DMG and missed every Windows installer, so the comparison ignores case.
const ASSET_PREFIX: &str = "HSPlanner_";

fn is_package(name: &str) -> bool {
    name.get(..ASSET_PREFIX.len())
        .is_some_and(|prefix| prefix.eq_ignore_ascii_case(ASSET_PREFIX))
}
const CHECK_TIMEOUT: Duration = Duration::from_secs(10);
const DOWNLOAD_TIMEOUT: Duration = Duration::from_secs(600);

#[derive(Deserialize)]
struct Release {
    tag_name: String,
    html_url: String,
    assets: Vec<Asset>,
}

#[derive(Deserialize, Clone, Debug, PartialEq)]
pub struct Asset {
    pub name: String,
    pub browser_download_url: String,
    pub digest: Option<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Update {
    pub version: Version,
    pub page: String,
    pub installer: Option<Asset>,
}

#[derive(Clone, Debug, PartialEq, Default)]
pub enum State {
    #[default]
    Idle,
    Checking,
    UpToDate,
    Available(Update),
    Installing(Update),
    Failed(String),
}

pub struct Installed;

pub struct Updater {
    pub state: State,
}

impl EventEmitter<Installed> for Updater {}

impl Updater {
    pub fn new(cx: &mut Context<Self>) -> Self {
        let mut this = Self { state: State::Idle };
        this.check(true, cx);
        this
    }

    pub fn check(&mut self, silent: bool, cx: &mut Context<Self>) {
        if matches!(self.state, State::Checking | State::Installing(_)) {
            return;
        }
        self.state = State::Checking;
        cx.notify();
        let http = cx.http_client();
        let task = cx.background_spawn(async move { fetch_latest(http).await });
        cx.spawn(async move |this, cx| {
            let result = task.await;
            let _ = this.update(cx, |this, cx| {
                this.state = match result {
                    Ok(release) => match pick(release, &current_version(), std::env::consts::OS) {
                        Some(update) => State::Available(update),
                        None => State::UpToDate,
                    },
                    Err(error) => {
                        log::warn!("Update check failed: {error:#}");
                        if silent {
                            State::Idle
                        } else {
                            State::Failed(
                                tr("Could not check for updates: {error}")
                                    .replace("{error}", &format!("{error:#}")),
                            )
                        }
                    }
                };
                cx.notify();
            });
        })
        .detach();
    }

    pub fn install(&mut self, cx: &mut Context<Self>) {
        let State::Available(update) = self.state.clone() else {
            return;
        };
        let Some(asset) = update.installer.clone() else {
            cx.open_url(&update.page);
            return;
        };
        self.state = State::Installing(update);
        cx.notify();
        let http = cx.http_client();
        let task = cx.background_spawn(async move {
            let path = download(http, &asset).await?;
            install(&path)
        });
        cx.spawn(async move |this, cx| {
            let result = task.await;
            let _ = this.update(cx, |this, cx| match result {
                Ok(()) => cx.emit(Installed),
                Err(error) => {
                    log::error!("Update install failed: {error:#}");
                    this.state = State::Failed(tr("Update failed: {error}").replace("{error}", &format!("{error:#}")));
                    cx.notify();
                }
            });
        })
        .detach();
    }
}

pub fn current_version() -> Version {
    Version::parse(env!("CARGO_PKG_VERSION")).expect("valid crate version")
}

fn pick(release: Release, current: &Version, os: &str) -> Option<Update> {
    let version = Version::parse(release.tag_name.trim_start_matches('v')).ok()?;
    if version <= *current
        || !release
            .assets
            .iter()
            .any(|asset| asset.name == "SHA256SUMS")
        || !release
            .assets
            .iter()
            .any(|asset| is_package(&asset.name))
    {
        return None;
    }
    let extension = match os {
        "macos" => Some(".dmg"),
        "windows" => Some(".exe"),
        _ => None,
    };
    let installer = extension.and_then(|extension| {
        release
            .assets
            .into_iter()
            .find(|asset| is_package(&asset.name) && asset.name.ends_with(extension))
    });
    Some(Update {
        version,
        page: release.html_url,
        installer,
    })
}

async fn fetch_latest(http: Arc<dyn HttpClient>) -> anyhow::Result<Release> {
    let request = Request::get(format!(
        "https://api.github.com/repos/{REPO}/releases/latest"
    ))
    // Protocol, not prose: the automatic wrapping pass caught these and the
    // catalogue then turned Accept into 확인, which is not a valid header name.
    .header("Accept", "application/vnd.github+json")
    .follow_redirects(RedirectPolicy::FollowAll)
    .timeout(CHECK_TIMEOUT)
    .body(AsyncBody::default())?;
    let body = read(http.send(request).await?).await?;
    serde_json::from_slice(&body).context(tr("unexpected release JSON"))
}

async fn download(http: Arc<dyn HttpClient>, asset: &Asset) -> anyhow::Result<std::path::PathBuf> {
    let expected = asset
        .digest
        .as_deref()
        .and_then(|digest| digest.strip_prefix("sha256:"))
        .context(
            tr("GitHub published no checksum for this installer; download it from the release page"),
        )?;
    let request = Request::get(&asset.browser_download_url)
        .follow_redirects(RedirectPolicy::FollowAll)
        .timeout(DOWNLOAD_TIMEOUT)
        .body(AsyncBody::default())?;
    let bytes = read(http.send(request).await?).await?;
    anyhow::ensure!(
        digest_matches(&bytes, expected),
        "checksum mismatch for {}",
        asset.name
    );
    let path = std::env::temp_dir().join(&asset.name);
    std::fs::write(&path, bytes).with_context(|| tr("writing {path}").replace("{path}", &path.display().to_string()))?;
    Ok(path)
}

async fn read(mut response: Response<AsyncBody>) -> anyhow::Result<Vec<u8>> {
    let status = response.status();
    let mut body = Vec::new();
    response.body_mut().read_to_end(&mut body).await?;
    anyhow::ensure!(status.is_success(), "GitHub answered {status}");
    Ok(body)
}

fn digest_matches(bytes: &[u8], expected_hex: &str) -> bool {
    format!("{:x}", Sha256::digest(bytes)).eq_ignore_ascii_case(expected_hex)
}

#[cfg(target_os = "macos")]
fn install(dmg: &Path) -> anyhow::Result<()> {
    let bundle = std::env::current_exe().ok().and_then(|exe| bundle_of(&exe));
    let Some(bundle) = bundle else {
        run("open", &[dmg.as_os_str()])?;
        anyhow::bail!(
            tr("not running from an app bundle; the disk image was opened for manual installation")
        );
    };
    let mount = std::env::temp_dir().join("hsplanner-update-mount");
    run(
        "hdiutil",
        &[
            "attach".as_ref(),
            "-nobrowse".as_ref(),
            "-readonly".as_ref(),
            "-mountpoint".as_ref(),
            mount.as_os_str(),
            dmg.as_os_str(),
        ],
    )?;
    let replaced = replace_bundle(&mount, &bundle);
    let _ = run(
        "hdiutil",
        &["detach".as_ref(), mount.as_os_str(), "-force".as_ref()],
    );
    if let Err(error) = replaced {
        let _ = run("open", &[dmg.as_os_str()]);
        return Err(error.context(tr("the disk image was opened for manual installation")));
    }
    // ponytail: the new copy launches after this process exits; if the delay is too
    // short the user simply reopens the app from Applications.
    std::process::Command::new("sh")
        .arg("-c")
        .arg("sleep 2; open \"$0\"")
        .arg(&bundle)
        .spawn()?;
    Ok(())
}

#[cfg(target_os = "macos")]
fn replace_bundle(mount: &Path, bundle: &Path) -> anyhow::Result<()> {
    let fresh = std::fs::read_dir(mount)?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .find(|path| path.extension().is_some_and(|extension| extension == "app"))
        .context(tr("no application in the disk image"))?;
    let staged = bundle.with_extension("app.update");
    let old = bundle.with_extension("app.old");
    let _ = std::fs::remove_dir_all(&staged);
    let _ = std::fs::remove_dir_all(&old);
    run("ditto", &[fresh.as_os_str(), staged.as_os_str()])?;
    std::fs::rename(bundle, &old).with_context(|| {
        tr("replacing {path}").replace("{path}", &bundle.display().to_string())
    })?;
    std::fs::rename(&staged, bundle)?;
    let _ = std::fs::remove_dir_all(&old);
    Ok(())
}

#[cfg(target_os = "macos")]
fn run(program: &str, args: &[&std::ffi::OsStr]) -> anyhow::Result<()> {
    let output = std::process::Command::new(program)
        .args(args)
        .output()
        .with_context(|| tr("running {program}").replace("{program}", program))?;
    anyhow::ensure!(
        output.status.success(),
        "{program} failed: {}",
        String::from_utf8_lossy(&output.stderr).trim()
    );
    Ok(())
}

fn bundle_of(exe: &Path) -> Option<std::path::PathBuf> {
    let bundle = exe.ancestors().nth(3)?;
    (bundle.extension()? == "app").then(|| bundle.to_path_buf())
}

#[cfg(target_os = "windows")]
fn install(installer: &Path) -> anyhow::Result<()> {
    std::process::Command::new(installer)
        .spawn()
        .context(tr("starting the installer"))?;
    Ok(())
}

#[cfg(not(any(target_os = "macos", target_os = "windows")))]
fn install(_: &Path) -> anyhow::Result<()> {
    anyhow::bail!(tr("in-app installation is not available on this platform"))
}

pub fn open_dialog(updater: Entity<Updater>, window: &mut Window, cx: &mut App) {
    window.open_dialog(cx, move |dialog, _, cx| {
        let palette = cx.global::<TooltipTheme>();
        let state = updater.read(cx).state.clone();
        let (update, installing) = match &state {
            State::Available(update) => (Some(update.clone()), false),
            State::Installing(update) => (Some(update.clone()), true),
            _ => (None, false),
        };
        let Some(update) = update else {
            let message = match state {
                State::Failed(message) => message,
                _ => tr("HSPlanner is up to date.").to_string(),
            };
            return dialog.title(tr("Updates")).child(message);
        };
        let explanation = if update.installer.is_some() {
            tr("The installer is downloaded from GitHub, verified against its published checksum and started. HSPlanner closes to finish the update.")
        } else {
            tr("Download the package for your platform from the release page and reinstall.")
        };
        let action = if installing {
            tr("Downloading…")
        } else if update.installer.is_some() {
            tr("Install and restart")
        } else {
            tr("Open release page")
        };
        let page = update.page.clone();
        let install = updater.clone();
        dialog
            .title(tr("HSPlanner v{version} is available").replace("{version}", &update.version.to_string()))
            .child(div().flex().flex_col().gap_2()
                .child(tr("You are running v{version}.").replace("{version}", &current_version().to_string()))
                .child(div().text_color(palette.muted).child(explanation)))
            .footer(div().flex().items_center().justify_between().gap_3()
                .child(gpui_kit::base::Link::new("update-release-page").child(tr("Release notes")).href(page)
                    .text_color(palette.accent).underline().accessibility_label(tr("Release notes on GitHub"))
                    .open_with(|url, _, _, cx| cx.open_url(url)))
                .child(Button::new("install-update").planner_style(cx).label(action).loading(installing)
                    .on_click(move |_, _, cx| install.update(cx, |updater, cx| updater.install(cx)))))
    });
}

#[cfg(test)]
mod tests {
    // Explicit imports: the crate's `gpui_kit::*` glob would shadow `#[test]` with `gpui::test`.
    use super::{Asset, Release, Version, bundle_of, digest_matches, pick};
    use std::path::Path;

    fn asset(name: &str) -> Asset {
        Asset {
            name: name.into(),
            browser_download_url: format!("https://x/{name}"),
            digest: None,
        }
    }

    fn release(tag: &str, names: &[&str]) -> Release {
        Release {
            tag_name: tag.into(),
            html_url: "https://x/release".into(),
            assets: names.iter().map(|name| asset(name)).collect(),
        }
    }

    #[test]
    fn newer_native_release_yields_platform_installer() {
        let current = Version::new(1, 1, 0);
        let release = release(
            "v1.2.0",
            &[
                "HSPlanner_1.2.0_aarch64.dmg",
                "HSPlanner_1.2.0_x64-setup.exe",
                "SHA256SUMS",
            ],
        );
        let update = pick(release, &current, "macos").unwrap();
        assert_eq!(update.version, Version::new(1, 2, 0));
        assert_eq!(
            update.installer.unwrap().name,
            "HSPlanner_1.2.0_aarch64.dmg"
        );
    }

    #[test]
    fn packager_output_names_are_recognised_whatever_their_case() {
        // The names cargo-packager actually produces, taken from a published
        // release: the DMG is capitalised and the installer is not.
        let release = release(
            "v1.2.0",
            &[
                "HSPlanner_1.2.0_aarch64.dmg",
                "hsplanner_1.2.0_x64-setup.exe",
                "SHA256SUMS",
            ],
        );
        let update = pick(release, &Version::new(1, 1, 0), "windows").unwrap();
        assert_eq!(
            update.installer.expect("windows installer").name,
            "hsplanner_1.2.0_x64-setup.exe"
        );
    }

    #[test]
    fn a_windows_only_release_is_still_offered() {
        // This fork publishes no macOS build, so the lowercase installer is the
        // only package in the release; an exact-prefix check hid it entirely.
        let release = release(
            "v1.2.0",
            &["hsplanner_1.2.0_x64-setup.exe", "SHA256SUMS"],
        );
        let update = pick(release, &Version::new(1, 1, 0), "windows")
            .expect("a windows-only release should still be an update");
        assert_eq!(update.version, Version::new(1, 2, 0));
    }

    #[test]
    fn windows_picks_setup_exe_and_linux_gets_page_only() {
        let names = [
            "HSPlanner_1.2.0_aarch64.dmg",
            "HSPlanner_1.2.0_x64-setup.exe",
            "HSPlanner_1.2.0_amd64.deb",
            "SHA256SUMS",
        ];
        let windows = pick(release("v1.2.0", &names), &Version::new(1, 1, 0), "windows").unwrap();
        assert_eq!(
            windows.installer.unwrap().name,
            "HSPlanner_1.2.0_x64-setup.exe"
        );
        let linux = pick(release("v1.2.0", &names), &Version::new(1, 1, 0), "linux").unwrap();
        assert_eq!(linux.installer, None);
        assert_eq!(linux.page, "https://x/release");
    }

    #[test]
    fn same_or_older_version_is_not_an_update() {
        let names = ["HSPlanner_1.1.0_aarch64.dmg", "SHA256SUMS"];
        assert!(pick(release("v1.1.0", &names), &Version::new(1, 1, 0), "macos").is_none());
        assert!(pick(release("v1.0.9", &names), &Version::new(1, 1, 0), "macos").is_none());
        assert!(pick(release("nightly", &names), &Version::new(1, 1, 0), "macos").is_none());
    }

    #[test]
    fn legacy_tauri_release_is_ignored_even_when_newer() {
        let release = release(
            "v9.0.0",
            &[
                "HSPlanner_9.0.0_aarch64.dmg",
                "HSPlanner_9.0.0_x64-setup.exe",
                "latest.json",
            ],
        );
        assert!(pick(release, &Version::new(1, 1, 0), "macos").is_none());
    }

    #[test]
    fn digest_comparison_is_case_insensitive() {
        let expected = "2CF24DBA5FB0A30E26E83B2AC5B9E29E1B161E5C1FA7425E73043362938B9824";
        assert!(digest_matches(b"hello", expected));
        assert!(!digest_matches(b"hello!", expected));
    }

    #[test]
    #[ignore = "talks to api.github.com; run with --ignored"]
    fn live_release_json_parses_and_carries_digests() {
        let http: std::sync::Arc<dyn super::HttpClient> = std::sync::Arc::new(
            reqwest_client::ReqwestClient::user_agent(super::USER_AGENT).unwrap(),
        );
        let release = futures::executor::block_on(super::fetch_latest(http)).unwrap();
        assert!(release.tag_name.starts_with('v'), "{}", release.tag_name);
        assert!(release.html_url.contains("/releases/tag/"));
        assert!(release.assets.iter().all(|asset| {
            asset
                .digest
                .as_deref()
                .is_some_and(|d| d.starts_with("sha256:"))
        }));
    }

    #[test]
    fn bundle_is_three_levels_above_the_executable() {
        let exe = Path::new("/Applications/HSPlanner.app/Contents/MacOS/hsplanner");
        assert_eq!(
            bundle_of(exe).unwrap(),
            Path::new("/Applications/HSPlanner.app")
        );
        assert_eq!(bundle_of(Path::new("/repo/target/release/hsplanner")), None);
    }
}
