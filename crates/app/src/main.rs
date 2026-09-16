#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

mod bug_report;
mod bug_report_transport;
mod changelog;
mod chrome;
mod settings;
mod shell;
mod startup;
mod update;

fn main() {
    #[cfg(target_os = "linux")]
    if gpui_kit::guess_compositor() != "Wayland" {
        eprintln!("HSPlanner requires a native Wayland session.");
        std::process::exit(1);
    }
    #[cfg(debug_assertions)]
    hsplanner_ui::debug_log::install();
    let directory = hsplanner_build::storage::data_directory().unwrap_or_else(|error| {
        eprintln!("{error}");
        std::process::exit(1)
    });
    // Before anything touches the game data: catalogues are parsed once and
    // leaked, so an override installed later would never be seen.
    hsplanner_engine::calc::i18n::install_external_catalogs(&directory);
    hsplanner_engine::calc::i18n::set_default_locale(&resolve_locale());

    let loaded = hsplanner_build::storage::Writer::open(directory.clone());
    shell::run(directory, loaded);
}

/// `HSPLANNER_LOCALE` wins so a build can be checked in either language without
/// touching the OS; otherwise follow the system language when we ship that
/// language, and fall back to the untranslated source text when we do not.
fn resolve_locale() -> String {
    use hsplanner_engine::calc::i18n;

    if let Some(forced) = std::env::var_os("HSPLANNER_LOCALE") {
        return forced.to_string_lossy().into_owned();
    }
    let system = sys_locale::get_locale().unwrap_or_default();
    let language = system.split(['-', '_']).next().unwrap_or("").to_lowercase();
    if i18n::is_translated(&language) {
        language
    } else {
        i18n::SOURCE_LOCALE.to_string()
    }
}
