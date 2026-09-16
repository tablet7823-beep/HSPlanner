//! Mercenary catalog, shared by native and transport-backed workflows.
use serde::Deserialize;
use std::sync::LazyLock;

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MercenaryData {
    pub max_skill_rank: u32,
    pub slots: Vec<String>,
    pub classes: Vec<MercenaryClass>,
}
#[derive(Debug, Deserialize)]
pub struct MercenaryClass {
    pub id: String,
    pub name: String,
    pub role: String,
    pub location: String,
    pub skills: Vec<MercenarySkill>,
}
#[derive(Debug, Deserialize)]
pub struct MercenarySkill {
    pub id: String,
    pub name: String,
    pub kind: String,
    #[serde(default)]
    pub damage_type: Option<String>,
    pub shared: bool,
    pub description: String,
}
// Same as the ether tree: loaded outside GameData, so it caches per locale here.
const MERCENARIES_JSON: &str = include_str!("../../../data/mercenaries.json");
static DATA_BY_LOCALE: LazyLock<
    std::sync::Mutex<std::collections::HashMap<String, &'static MercenaryData>>,
> = LazyLock::new(|| std::sync::Mutex::new(std::collections::HashMap::new()));

pub fn data() -> &'static MercenaryData {
    crate::calc::i18n::cached_per_locale(&DATA_BY_LOCALE, || {
        crate::calc::i18n::parse_localized(MERCENARIES_JSON, "mercenaries.json")
    })
}
