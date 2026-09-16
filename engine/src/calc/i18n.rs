//! Translation overlay, applied to the patched JSON just before it is
//! deserialised into `GameData`.
//!
//! Catalogues are keyed by the English source text rather than by a JSON path.
//! Upstream reshuffles the data arrays every season, so path keys rot; the
//! English prose is what actually identifies a message. Keying on it also
//! deduplicates the very repetitive tree stat lines and guarantees one phrase
//! renders identically wherever it appears.
//!
//! Several English names are *lookup keys*, not prose: item `skillBonuses` is a
//! map keyed by English skill name, `lootfilter.rs` normalises stat names with
//! English-word regexes, and `tooltip_parse.rs` reads English game tooltips off
//! the screen. Translating those in place would make the matching silently miss
//! and drop bonuses from the calculation without raising an error. So every
//! translated `name` keeps its original next to it under `nameEn`, and the
//! matching code reads that instead. Structs that do not declare `name_en`
//! simply ignore the extra field — nothing here uses `deny_unknown_fields`.

use std::cell::RefCell;
use std::collections::HashMap;
use std::sync::{LazyLock, Mutex, RwLock};

use serde_json::{Map, Value};

#[allow(dead_code)]
mod includes {
    include!(concat!(env!("OUT_DIR"), "/i18n_includes.rs"));
}

pub(crate) use includes::{CATALOGS, CONTEXT_CATALOGS, UI_CATALOGS};

/// Locale that means "leave the data exactly as upstream shipped it".
pub const SOURCE_LOCALE: &str = "en";

/// Object keys whose string value is displayed prose. Must stay in step with
/// `TEXT_FIELDS` in tools/i18n_extract.py: a field listed there but not here is
/// extracted and translated in the catalogue yet never applied, which reads as
/// a missing translation rather than a wiring mistake.
///
/// `t` is the incarnation node title; the tree files reuse `t` for the node
/// size (root/small/big), which never appears in a catalogue, so the lookup
/// simply misses there. `tree` is the skill subtree heading — it also joins a
/// skill to an item's random-skill pool, but both sides are the same English
/// string and share one catalogue entry, so they translate together.
const TEXT_FIELDS: &[&str] = &[
    "name",
    "description",
    "desc",
    "label",
    "title",
    "flavor",
    "t",
    "tree",
];

/// Object keys holding a list of prose strings: the incarnation node stat lines.
const TEXT_LIST_FIELDS: &[&str] = &["l"];

/// Field carrying the untranslated original, for the name-as-lookup-key paths.
const SOURCE_FIELD: &str = "nameEn";

thread_local! {
    static CURRENT_LOCALE: RefCell<Option<String>> = const { RefCell::new(None) };
}

/// RAII guard installing the per-command locale; `!Send` so it never crosses an
/// `.await`, matching `SeasonScope`.
///
/// Unlike `SeasonScope` this restores whatever was installed before rather than
/// clearing outright, because the data loader enters a nested scope while an
/// outer one is already active — clearing would drop the caller's locale.
pub struct LocaleScope {
    previous: Option<String>,
    _not_send: std::marker::PhantomData<*const ()>,
}

impl LocaleScope {
    #[must_use]
    pub fn enter(locale: Option<String>) -> LocaleScope {
        let previous = CURRENT_LOCALE.with(|c| c.replace(locale));
        LocaleScope {
            previous,
            _not_send: std::marker::PhantomData,
        }
    }
}

impl Drop for LocaleScope {
    fn drop(&mut self) {
        let previous = self.previous.take();
        CURRENT_LOCALE.with(|c| *c.borrow_mut() = previous);
    }
}

// Process-wide fallback for threads with no scope installed. The app sets it
// once at startup; without it every lookup serves the source language, which is
// exactly what the tests and the English build want.
static DEFAULT_LOCALE: RwLock<Option<String>> = RwLock::new(None);

pub fn set_default_locale(locale: &str) {
    let mut slot = DEFAULT_LOCALE.write().expect("default locale poisoned");
    *slot = Some(locale.to_string());
}

pub fn default_locale() -> String {
    DEFAULT_LOCALE
        .read()
        .expect("default locale poisoned")
        .clone()
        .unwrap_or_else(|| SOURCE_LOCALE.to_string())
}

pub fn with_current_locale<R>(f: impl FnOnce(&str) -> R) -> R {
    let scoped = CURRENT_LOCALE.with(|c| c.borrow().clone());
    match scoped {
        Some(locale) => f(&locale),
        None => f(&default_locale()),
    }
}

pub fn current_locale() -> String {
    with_current_locale(str::to_string)
}

/// A locale counts as translated if anything ships for it, embedded or on disk.
/// An external-only catalogue is enough, so a new language needs no rebuild.
pub fn is_translated(locale: &str) -> bool {
    locale != SOURCE_LOCALE
        && (CATALOGS
            .iter()
            .chain(UI_CATALOGS.iter())
            .any(|(id, _)| *id == locale)
            || [&EXTERNAL, &EXTERNAL_UI].iter().any(|store| {
                store
                    .read()
                    .expect("external catalogs poisoned")
                    .contains_key(locale)
            }))
}

/// Every locale the build can serve, for a language picker. A locale counts
/// even if only its interface strings are translated.
pub fn available_locales() -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut add = |lang: &str| {
        if !out.iter().any(|existing| existing == lang) {
            out.push(lang.to_string());
        }
    };
    for (lang, _) in CATALOGS.iter().chain(UI_CATALOGS.iter()) {
        add(lang);
    }
    for store in [&EXTERNAL, &EXTERNAL_UI] {
        for lang in store.read().expect("external catalogs poisoned").keys() {
            add(lang);
        }
    }
    out.sort();
    out
}

/// Untranslated locales all collapse onto one cache entry so a garbage id
/// cannot grow the per-locale caches. Mirrors `season::cache_key`.
pub fn cache_key(locale: &str) -> &str {
    if is_translated(locale) {
        locale
    } else {
        SOURCE_LOCALE
    }
}

static CATALOG_CACHE: LazyLock<Mutex<HashMap<String, &'static HashMap<String, String>>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

// Catalogues found on disk at startup, layered over the embedded ones. This is
// what makes a translation fix shippable as a ~1 MB file instead of a reinstall.
static EXTERNAL: LazyLock<RwLock<HashMap<String, String>>> =
    LazyLock::new(|| RwLock::new(HashMap::new()));
static EXTERNAL_UI: LazyLock<RwLock<HashMap<String, String>>> =
    LazyLock::new(|| RwLock::new(HashMap::new()));

/// Read `<directory>/i18n/<lang>.json` and `<directory>/i18n/ui/<lang>.json`
/// into the override layer — the shape a shipped translation patch takes.
///
/// Must run before the first data access: catalogues are parsed once and leaked,
/// so anything installed later would be ignored by an already-built cache.
/// Returns the locales it picked up.
pub fn install_external_catalogs(directory: &std::path::Path) -> Vec<String> {
    let root = directory.join("i18n");
    let mut installed = read_catalog_dir(&root, &EXTERNAL);
    for lang in read_catalog_dir(&root.join("ui"), &EXTERNAL_UI) {
        if !installed.contains(&lang) {
            installed.push(lang);
        }
    }
    installed
}

fn read_catalog_dir(dir: &std::path::Path, into: &RwLock<HashMap<String, String>>) -> Vec<String> {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut installed = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|s| s.to_str()) != Some("json") {
            continue;
        }
        let Some(lang) = path.file_stem().and_then(|s| s.to_str()) else {
            continue;
        };
        if lang == "sources" {
            continue;
        }
        match std::fs::read_to_string(&path) {
            Ok(text) => {
                into.write()
                    .expect("external catalogs poisoned")
                    .insert(lang.to_string(), text);
                installed.push(lang.to_string());
            }
            Err(e) => log::error!("cannot read catalog {}: {e}", path.display()),
        }
    }
    installed
}

fn parse_catalog(json: &str, label: &str) -> HashMap<String, String> {
    match serde_json::from_str::<HashMap<String, String>>(json) {
        // Empty translations are untranslated entries in the template, not an
        // instruction to blank the string on screen.
        Ok(map) => map.into_iter().filter(|(_, v)| !v.is_empty()).collect(),
        Err(e) => {
            log::error!("{label}: invalid catalog: {e}");
            HashMap::new()
        }
    }
}

/// Parsed catalogue for a locale, or `None` when nothing ships for it.
fn catalog(locale: &str) -> Option<&'static HashMap<String, String>> {
    if !is_translated(locale) {
        return None;
    }
    {
        let cache = CATALOG_CACHE.lock().expect("i18n catalog cache poisoned");
        if let Some(found) = cache.get(locale) {
            return Some(found);
        }
    }

    let mut merged = CATALOGS
        .iter()
        .find(|(id, _)| *id == locale)
        .map(|(_, json)| parse_catalog(json, &format!("embedded {locale}")))
        .unwrap_or_default();
    // Entry by entry, so a partial override file corrects the phrases it names
    // and leaves the rest of the shipped catalogue intact.
    if let Some(text) = EXTERNAL
        .read()
        .expect("external catalogs poisoned")
        .get(locale)
    {
        merged.extend(parse_catalog(text, &format!("external {locale}")));
    }

    let mut cache = CATALOG_CACHE.lock().expect("i18n catalog cache poisoned");
    if let Some(found) = cache.get(locale) {
        return Some(found);
    }
    let leaked: &'static HashMap<String, String> = Box::leak(Box::new(merged));
    cache.insert(locale.to_string(), leaked);
    Some(leaked)
}

// Keyed by a JSON path prefix ("game-config/slots") then by English text.
// Exists because the catalogue is keyed on the English alone, and the same word
// is not always the same thing: "Armor" is a defence stat almost everywhere and
// the chest slot in exactly one place, so the gear screen labelled that slot
// 방어력 until this could say otherwise.
static CONTEXT_CACHE: LazyLock<
    Mutex<HashMap<String, &'static HashMap<String, HashMap<String, String>>>>,
> = LazyLock::new(|| Mutex::new(HashMap::new()));

type ContextOverrides = HashMap<String, HashMap<String, String>>;

fn context_overrides(locale: &str) -> &'static ContextOverrides {
    {
        let cache = CONTEXT_CACHE.lock().expect("context cache poisoned");
        if let Some(found) = cache.get(locale) {
            return found;
        }
    }
    let parsed: ContextOverrides = CONTEXT_CATALOGS
        .iter()
        .find(|(id, _)| *id == locale)
        .map(|(_, json)| {
            serde_json::from_str(json).unwrap_or_else(|e| {
                log::error!("locale {locale}: invalid context overrides: {e}");
                HashMap::new()
            })
        })
        .unwrap_or_default();

    let mut cache = CONTEXT_CACHE.lock().expect("context cache poisoned");
    if let Some(found) = cache.get(locale) {
        return found;
    }
    let leaked: &'static ContextOverrides = Box::leak(Box::new(parsed));
    cache.insert(locale.to_string(), leaked);
    leaked
}

/// Translate every prose field in `value` in place. A miss leaves the English
/// text alone, so a partially translated catalogue degrades field by field
/// instead of blanking anything.
///
/// `collection` names the source file ("game-config"), and forms the root of
/// the path the context overrides are keyed by.
pub fn localize_in(value: Value, locale: &str, collection: &str) -> Value {
    match catalog(locale) {
        Some(catalog) => {
            let overrides = context_overrides(locale);
            translate(value, catalog, overrides, collection)
        }
        None => value,
    }
}

pub fn localize(value: Value, locale: &str) -> Value {
    localize_in(value, locale, "")
}

/// `localize` against the locale installed by the innermost `LocaleScope`.
pub fn localize_current(value: Value, collection: &str) -> Value {
    with_current_locale(|locale| localize_in(value, locale, collection))
}

// ---------- interface strings ----------

static UI_CACHE: LazyLock<Mutex<HashMap<String, &'static HashMap<String, String>>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

fn ui_catalog(locale: &str) -> Option<&'static HashMap<String, String>> {
    if locale == SOURCE_LOCALE {
        return None;
    }
    {
        let cache = UI_CACHE.lock().expect("ui catalog cache poisoned");
        if let Some(found) = cache.get(locale) {
            return Some(found);
        }
    }
    let mut merged = UI_CATALOGS
        .iter()
        .find(|(id, _)| *id == locale)
        .map(|(_, json)| parse_catalog(json, &format!("embedded ui {locale}")))
        .unwrap_or_default();
    if let Some(text) = EXTERNAL_UI
        .read()
        .expect("external ui catalogs poisoned")
        .get(locale)
    {
        merged.extend(parse_catalog(text, &format!("external ui {locale}")));
    }

    let mut cache = UI_CACHE.lock().expect("ui catalog cache poisoned");
    if let Some(found) = cache.get(locale) {
        return Some(found);
    }
    let leaked: &'static HashMap<String, String> = Box::leak(Box::new(merged));
    cache.insert(locale.to_string(), leaked);
    Some(leaked)
}

/// Translate an interface literal. Takes `&'static str` because call sites pass
/// string literals; a miss returns the literal unchanged, so wrapping a string
/// that is not in the catalogue is a no-op rather than a bug.
pub fn tr(source: &'static str) -> &'static str {
    with_current_locale(|locale| {
        ui_catalog(locale)
            .and_then(|catalog| catalog.get(source))
            .map(String::as_str)
            .unwrap_or(source)
    })
}

/// Translate a **game-data** string that reached the caller outside the normal
/// load path — a tree description baked into a build script, say. Looks in the
/// data catalogue, not the interface one, and returns the input on a miss.
pub fn tr_data(source: &str) -> String {
    with_current_locale(|locale| {
        catalog(locale)
            .and_then(|catalog| catalog.get(source))
            .cloned()
            .unwrap_or_else(|| source.to_string())
    })
}

/// `tr` for text built at runtime rather than written as a literal.
pub fn tr_owned(source: &str) -> String {
    with_current_locale(|locale| {
        ui_catalog(locale)
            .and_then(|catalog| catalog.get(source))
            .cloned()
            .unwrap_or_else(|| source.to_string())
    })
}

/// Parse a JSON blob through the translation overlay. For the collections that
/// load outside `GameData` and so miss the season-patch path.
pub fn parse_localized<T: serde::de::DeserializeOwned>(json: &str, ctx: &str) -> T {
    let value: Value =
        serde_json::from_str(json).unwrap_or_else(|e| panic!("failed to parse {ctx}: {e}"));
    let collection = ctx.strip_suffix(".json").unwrap_or(ctx);
    serde_json::from_value(localize_current(value, collection))
        .unwrap_or_else(|e| panic!("invalid {ctx} shape after translation: {e}"))
}

/// Double-checked-lock cache of leaked per-locale singletons, the locale
/// counterpart of `season::cached_per_season`.
pub fn cached_per_locale<T>(
    cache: &Mutex<HashMap<String, &'static T>>,
    build: impl FnOnce() -> T,
) -> &'static T {
    let key = with_current_locale(|locale| cache_key(locale).to_string());
    {
        let cache = cache.lock().expect("per-locale cache poisoned");
        if let Some(found) = cache.get(&key) {
            return found;
        }
    }
    let built = build();
    let mut cache = cache.lock().expect("per-locale cache poisoned");
    if let Some(found) = cache.get(&key) {
        return found;
    }
    let leaked: &'static T = Box::leak(Box::new(built));
    cache.insert(key, leaked);
    leaked
}

fn translate(
    value: Value,
    catalog: &HashMap<String, String>,
    overrides: &ContextOverrides,
    path: &str,
) -> Value {
    match value {
        Value::Object(map) => Value::Object(translate_object(map, catalog, overrides, path)),
        Value::Array(items) => Value::Array(
            items
                .into_iter()
                // Array position carries no meaning for a path, so entries
                // share their parent's context.
                .map(|v| translate(v, catalog, overrides, path))
                .collect(),
        ),
        other => other,
    }
}

/// The override for `text` at `path`, if any path prefix declares one.
fn override_for<'a>(
    overrides: &'a ContextOverrides,
    path: &str,
    text: &str,
) -> Option<&'a String> {
    let mut prefix = path;
    loop {
        if let Some(found) = overrides.get(prefix).and_then(|table| table.get(text)) {
            return Some(found);
        }
        match prefix.rfind('/') {
            Some(cut) => prefix = &prefix[..cut],
            None => return None,
        }
    }
}

fn translate_object(
    map: Map<String, Value>,
    catalog: &HashMap<String, String>,
    overrides: &ContextOverrides,
    path: &str,
) -> Map<String, Value> {
    let mut out = Map::with_capacity(map.len());
    for (key, value) in map {
        let child = if path.is_empty() {
            key.clone()
        } else {
            format!("{path}/{key}")
        };
        match value {
            Value::String(text) if TEXT_FIELDS.contains(&key.as_str()) => {
                let replacement = override_for(overrides, path, &text).or_else(|| catalog.get(&text));
                match replacement {
                    Some(translated) => {
                        // Keep the original reachable for the matching paths.
                        if key == "name" {
                            out.insert(SOURCE_FIELD.to_string(), Value::String(text));
                        }
                        out.insert(key, Value::String(translated.clone()));
                    }
                    None => {
                        out.insert(key, Value::String(text));
                    }
                }
            }
            Value::Array(items) if TEXT_LIST_FIELDS.contains(&key.as_str()) => {
                let translated = items
                    .into_iter()
                    .map(|item| match item {
                        Value::String(text) => Value::String(
                            override_for(overrides, path, &text)
                                .or_else(|| catalog.get(&text))
                                .cloned()
                                .unwrap_or(text),
                        ),
                        other => translate(other, catalog, overrides, &child),
                    })
                    .collect();
                out.insert(key, Value::Array(translated));
            }
            other => {
                out.insert(key, translate(other, catalog, overrides, &child));
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn catalog() -> HashMap<String, String> {
        [
            ("Charged Bolts", "차지드 볼트"),
            ("+5 to Strength", "힘 +5"),
            ("Deals lightning damage.", "번개 피해를 입힙니다."),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .collect()
    }

    #[test]
    fn translated_name_keeps_the_english_original() {
        let out = translate(
            json!({"id": "charged_bolts", "name": "Charged Bolts"}), &catalog(), &ContextOverrides::new(), "");
        assert_eq!(out["name"], json!("차지드 볼트"));
        assert_eq!(out["nameEn"], json!("Charged Bolts"));
    }

    #[test]
    fn untranslated_text_is_left_alone_and_gains_no_source_field() {
        let out = translate(json!({"name": "Fireball"}), &catalog(), &ContextOverrides::new(), "");
        assert_eq!(out["name"], json!("Fireball"));
        assert!(out.get("nameEn").is_none());
    }

    #[test]
    fn node_stat_lines_translate_element_by_element() {
        let out = translate(
            json!({"t": "Strength", "l": ["+5 to Strength", "+25 to Maximum Life"]}), &catalog(), &ContextOverrides::new(), "");
        assert_eq!(out["l"], json!(["힘 +5", "+25 to Maximum Life"]));
    }

    #[test]
    fn every_locale_translates_the_skill_subtree_heading() {
        // The extractor and this module keep separate field lists, and `tree`
        // was once added only to the extractor: the headings sat translated in
        // the catalogue while the Skills tab still read "BERSERKER".
        let source = loaded(SOURCE_LOCALE);
        for locale in available_locales() {
            // `super::` because the fixture below shadows the module's own.
            let Some(catalog) = super::catalog(&locale) else {
                continue;
            };
            let translated = loaded(&locale);
            for (class, skills) in &source.skills_by_class {
                for skill in skills {
                    let Some(english) = skill.tree.as_deref() else {
                        continue;
                    };
                    let Some(expected) = catalog.get(english) else {
                        continue;
                    };
                    let actual = translated.skills_by_class[class]
                        .iter()
                        .find(|s| s.id == skill.id)
                        .and_then(|s| s.tree.as_deref());
                    assert_eq!(
                        actual,
                        Some(expected.as_str()),
                        "{locale}: subtree heading of {} was not translated",
                        skill.id
                    );
                }
            }
        }
    }

    #[test]
    fn skill_synergy_sources_still_resolve_in_every_locale() {
        // `bonusSources[].source` names another skill in English, exactly like
        // item skillBonuses. The synergy panel compared it against the shown
        // name, so in Korean it matched nothing: "provides synergy to" came up
        // empty and every "receives synergy from" row showed a dash.
        fn resolves(data: &crate::calc::data::GameData, class: &str, source: &str) -> bool {
            let needle = source.trim().to_lowercase();
            data.skills_by_class
                .get(class)
                .is_some_and(|skills| {
                    skills
                        .iter()
                        .any(|s| s.match_name().trim().to_lowercase() == needle)
                })
        }

        let source = loaded(SOURCE_LOCALE);
        let mut pairs = Vec::new();
        for (class, skills) in &source.skills_by_class {
            for skill in skills {
                for bonus in skill.bonus_sources.iter().flatten() {
                    if bonus.per == "skill_level" && resolves(source, class, &bonus.source) {
                        pairs.push((class.clone(), bonus.source.clone()));
                    }
                }
            }
        }
        assert!(!pairs.is_empty(), "no skill synergies found; the data moved");

        for locale in available_locales() {
            let translated = loaded(&locale);
            for (class, name) in &pairs {
                assert!(
                    resolves(translated, class, name),
                    "{locale}: synergy source {name:?} resolves in English but not here"
                );
            }
        }
    }

    #[test]
    fn item_skill_bonuses_still_resolve_in_every_locale() {
        // An item's `skillBonuses` keys are English skill names. Every lookup
        // that starts from one has to compare against `match_name`; comparing
        // the displayed name instead makes the lookup miss with no error at
        // all, and the bonus silently counts as zero.
        fn resolves(data: &crate::calc::data::GameData, key: &str) -> bool {
            let needle = key.trim().to_lowercase();
            let hit = |candidate: &str| candidate.trim().to_lowercase() == needle;
            data.item_granted_skills
                .iter()
                .any(|s| hit(s.match_name()))
                || data
                    .skills_by_class
                    .values()
                    .flatten()
                    .any(|s| hit(s.match_name()))
        }

        let source = loaded(SOURCE_LOCALE);
        let keys: Vec<&String> = source
            .items
            .values()
            .filter_map(|item| item.skill_bonuses.as_ref())
            .flat_map(|bonuses| bonuses.keys())
            .collect();
        assert!(!keys.is_empty(), "no item grants skills; the fixture moved");

        // A handful of keys name no skill at all — dangling references in the
        // upstream item data. They miss in English too, so the bar is that
        // translation changes nothing, not that everything resolves.
        let resolvable: Vec<&&String> = keys.iter().filter(|k| resolves(source, k)).collect();
        assert!(resolvable.len() > keys.len() / 2, "most keys should resolve");

        for locale in available_locales() {
            let translated = loaded(&locale);
            for key in &resolvable {
                assert!(
                    resolves(translated, key),
                    "{locale}: skill bonus key {key:?} resolves in English but not here"
                );
            }
        }
    }

    #[test]
    fn every_locale_translates_the_ether_node_labels() {
        // The ether tree loads outside GameData, on its own LazyLock, so it
        // misses the season-patch path where everything else gets translated.
        // It needed separate wiring, and this is what proves the wiring holds.
        for locale in available_locales() {
            let Some(catalog) = super::catalog(&locale) else {
                continue;
            };
            let _scope = LocaleScope::enter(Some(locale.clone()));
            let ids: Vec<u32> = (0..80).collect();
            let summaries = crate::calc::planner::summarize_ether(&ids);
            assert!(
                !summaries.is_empty(),
                "{locale}: no ether nodes resolved, the fixture ids moved"
            );
            for summary in summaries {
                // The label reaching the screen must be whatever the catalogue
                // says, never the English it was built from.
                if let Some(expected) = catalog.get(&summary.label) {
                    panic!(
                        "{locale}: ether node {} still shows English {:?} (catalogue has {expected:?})",
                        summary.key, summary.label
                    );
                }
            }
        }
    }

    #[test]
    fn a_context_override_beats_the_flat_catalogue_only_on_its_own_path() {
        // "Armor" is the defence stat nearly everywhere and the chest slot in
        // one place; only the slot may read differently.
        let catalog: HashMap<String, String> =
            [("Armor".to_string(), "방어력".to_string())].into_iter().collect();
        let overrides: ContextOverrides = [(
            "game-config/slots".to_string(),
            [("Armor".to_string(), "갑옷".to_string())]
                .into_iter()
                .collect(),
        )]
        .into_iter()
        .collect();

        let doc = json!({
            "slots": [{"key": "armor", "name": "Armor"}],
            "stats": [{"key": "armor", "name": "Armor"}],
        });
        let out = translate(doc, &catalog, &overrides, "game-config");
        assert_eq!(out["slots"][0]["name"], json!("갑옷"));
        assert_eq!(out["stats"][0]["name"], json!("방어력"));
    }

    #[test]
    fn tree_node_size_is_not_prose_and_never_matches() {
        // `t` means the node title in incarnation-nodes.json but the node size
        // in the tree files; sizes are absent from every catalogue.
        let out = translate(json!({"id": 2, "t": "small"}), &catalog(), &ContextOverrides::new(), "");
        assert_eq!(out["t"], json!("small"));
    }

    #[test]
    fn item_skill_bonus_keys_stay_english() {
        // These object *keys* pair with SkillSpec.name_en in rank.rs; if they
        // ever moved, granted ranks would silently resolve to zero.
        let out = translate(
            json!({"skillBonuses": {"Charged Bolts": [5, 7]}}), &catalog(), &ContextOverrides::new(), "");
        assert_eq!(out["skillBonuses"]["Charged Bolts"], json!([5, 7]));
    }

    // The guards below run against the real embedded catalogues rather than a
    // fixture, and assert an invariant instead of a particular translation, so
    // they keep working as the catalogue fills up.

    fn loaded(locale: &str) -> &'static crate::calc::data::GameData {
        crate::calc::data::data_for_locale(crate::calc::season::DEFAULT_SEASON_ID, locale)
    }

    #[test]
    fn every_locale_keeps_english_skill_match_names() {
        // Item `skillBonuses` is keyed by English skill name. If match_name ever
        // drifts from the source name, granted ranks resolve to zero and the
        // damage numbers go quietly wrong.
        let source = loaded(SOURCE_LOCALE);
        for locale in available_locales() {
            let translated = loaded(&locale);
            for (class, skills) in &translated.skills_by_class {
                for skill in skills {
                    let original = source.skills_by_class[class]
                        .iter()
                        .find(|s| s.id == skill.id)
                        .expect("every skill exists in the source language");
                    assert_eq!(
                        skill.match_name(),
                        original.name,
                        "{locale}: skill {} lost its English match name",
                        skill.id
                    );
                }
            }
        }
    }

    #[test]
    fn every_locale_keeps_english_granted_skill_match_names() {
        let source = loaded(SOURCE_LOCALE);
        for locale in available_locales() {
            for granted in &loaded(&locale).item_granted_skills {
                let original = source
                    .item_granted_skills
                    .iter()
                    .find(|g| g.id == granted.id)
                    .expect("every granted skill exists in the source language");
                assert_eq!(
                    granted.match_name(),
                    original.name,
                    "{locale}: granted skill {} lost its English match name",
                    granted.id
                );
            }
        }
    }

    #[test]
    fn every_locale_keeps_english_stat_match_names() {
        // The loot-filter encoder normalises these with English-word regexes.
        let source = loaded(SOURCE_LOCALE);
        for locale in available_locales() {
            for stat in &loaded(&locale).game_config.stats {
                let original = source
                    .game_config
                    .stats
                    .iter()
                    .find(|s| s.key == stat.key)
                    .expect("every stat exists in the source language");
                assert_eq!(
                    stat.match_name(),
                    original.name,
                    "{locale}: stat {} lost its English match name",
                    stat.key
                );
            }
        }
    }

    #[test]
    fn nested_collections_translate_all_the_way_down() {
        let out = translate(
            json!({"subskills": [{"name": "Charged Bolts",
                                  "description": "Deals lightning damage."}]}), &catalog(), &ContextOverrides::new(), "");
        assert_eq!(out["subskills"][0]["name"], json!("차지드 볼트"));
        assert_eq!(
            out["subskills"][0]["description"],
            json!("번개 피해를 입힙니다.")
        );
    }
}
