#!/usr/bin/env python3
"""Compose Korean for the game-data catalogue from a glossary and phrase rules.

The data catalogue holds ~12,900 strings, but they are not 12,900 independent
sentences: stat and affix names are built from a small vocabulary slotted into a
handful of shapes ("Increased X", "Chance to X", "Extra X to Y", "Ignore X
Resistance"). Translating the vocabulary once and composing from it keeps one
English term rendering as one Korean term everywhere, which hand translation
across thousands of entries does not.

Everything is all-or-nothing on purpose. If any fragment of a phrase is missing
from the glossary the entry is left blank and stays English on screen, because a
half-translated label reads worse than an untranslated one and hides the gap.

Run:  python tools/i18n_translate_ko.py          report coverage, write nothing
      python tools/i18n_translate_ko.py --write  merge into data/i18n/ko.json
"""

from __future__ import annotations

import functools
import json
import pathlib
import re
import sys

CATALOG = "data/i18n/ko.json"
SOURCES = "data/i18n/sources.json"
MANUAL = "data/i18n/manual/ko.json"

# ---------------------------------------------------------------- vocabulary

# Longest match wins, so multi-word terms must be able to beat their parts.
GLOSSARY = {
    # elements and damage kinds
    "Arcane": "비전", "Cold": "냉기", "Fire": "화염", "Lightning": "번개",
    "Poison": "독", "Physical": "물리", "Magic": "마법", "Elemental": "속성",
    "Chaos": "혼돈", "Shadow": "암흑",
    # attributes
    "Strength": "힘", "Dexterity": "민첩", "Intelligence": "지능",
    "Vitality": "활력", "Energy": "기력",
    "All Attributes": "모든 능력치", "Attributes": "능력치",
    # core nouns
    "Damage": "데미지", "Defense": "방어", "Armor": "방어구",
    "Resistance": "저항", "Resistances": "저항",
    "All Resistances": "모든 저항",
    "Life": "생명력", "Mana": "마나",
    "Maximum Life": "최대 생명력", "Maximum Mana": "최대 마나",
    "Attack Speed": "공격 속도", "Attack Rating": "공격 적중도",
    "Attack Radius": "공격 반경", "Attack Damage": "공격 데미지",
    "Cast Rate": "시전 속도", "Faster Cast Rate": "시전 속도",
    "Faster Hit Recovery": "피격 회복 속도",
    "Movement Speed": "이동 속도", "Skill Damage": "스킬 데미지",
    "Spell Damage": "주문 데미지", "Skills": "스킬", "Skill": "스킬",
    "Subskills": "하위 스킬", "Sub Skills": "하위 스킬",
    "Chance": "확률", "Duration": "지속시간", "Radius": "반경",
    "Area of Effect": "광역", "AoE": "광역", "Aoe": "광역",
    "Critical Strike": "치명타", "Critical Strike Damage": "치명타 데미지",
    "Critical Chance": "치명타 확률", "Critical Damage": "치명타 데미지",
    "Deadly Blow": "치명적 일격", "Crushing Blow": "강타",
    "Open Wound": "열상", "Open Wounds": "열상",
    "Magic Find": "매직 파인드", "Gold": "골드", "Experience": "경험치",
    "Cooldown": "재사용 대기시간", "Cooldowns": "재사용 대기시간",
    "Projectile": "투사체", "Projectiles": "투사체",
    "Summon": "소환수", "Summons": "소환수", "Guardian": "수호자",
    "Monsters": "몬스터", "Monster": "몬스터", "Bosses": "보스",
    "Enemy": "적", "Target": "대상", "Targets": "대상",
    "Block": "막기", "Block Rating": "막기 수치",
    "Dodge": "회피", "Dodge Chance": "회피 확률", "Evasion": "회피",
    "Light Radius": "광원 반경", "Corpses": "시체",
    "Stacks": "중첩", "Stack": "중첩", "Aura": "오라",
    "Absorption": "흡수", "Break": "파괴", "Mitigation": "감소",
    "Reduction": "감소", "Amplification": "증폭", "Threshold": "기준치",
    "Effectiveness": "효율", "Frequency": "빈도", "Amount": "수치",
    "Bleeding": "출혈", "Bleed": "출혈", "Burning": "화상",
    "Poisoned": "중독", "Frozen": "빙결", "Frostbite": "동상",
    "Stasis": "정체", "Stunned": "기절", "Stun": "기절",
    "Ailment": "상태이상", "Ailments": "상태이상",
    "Explosion": "폭발", "Explosions": "폭발",
    "Attacks per Second": "초당 공격", "Attacks": "공격", "Attack": "공격",
    "Hit": "타격", "Hits": "타격", "Striking": "타격",
    "Kill": "처치", "Kills": "처치", "Cast": "시전", "Casting": "시전",
    "Struck": "피격", "Level": "레벨", "Points": "포인트", "Point": "포인트",
    # slots
    "Helmet": "투구", "Gloves": "장갑", "Boots": "신발", "Belt": "허리띠",
    "Amulet": "목걸이", "Ring": "반지", "Weapon": "무기", "Offhand": "보조장비",
    "Charm": "부적", "Relic": "유물", "Relics": "유물",
    # difficulties and misc nouns
    "Hell": "지옥", "Normal": "일반", "Nightmare": "악몽",
    "Merchant Prices": "상점 가격",
    "Life Stolen per Hit": "타격당 생명력 흡수",
    "Mana Stolen per Hit": "타격당 마나 흡수",
    "Life Replenish": "생명력 재생", "Mana Replenish": "마나 재생",
    "Life Regeneration": "생명력 재생", "Mana Regeneration": "마나 재생",
    "Damage Return": "데미지 반사", "Damage Taken": "받는 데미지",
    "Damage Over Time": "지속 데미지", "Damage over Time": "지속 데미지",
    "Enhanced Damage": "강화 데미지", "Enhanced Defense": "강화 방어",
    "Multicast": "다중 시전", "Double Cast": "이중 시전",
    "Chains": "연쇄", "Chain Lightning Targets": "연쇄 번개 대상 수",
    "Homing Missile": "유도 미사일", "Homing Missiles": "유도 미사일",
    "Volleys": "일제 사격", "Trails": "자취", "Waves": "파동",
    # per-element skill damage families
    "Magic Skill": "마법 스킬", "Cold Skill": "냉기 스킬", "Fire Skill": "화염 스킬",
    "Lightning Skill": "번개 스킬", "Poison Skill": "독 스킬",
    "Arcane Skill": "비전 스킬", "Physical Skill": "물리 스킬",
    "Elemental Skill": "속성 스킬", "Shield Skill": "방패 스킬",
    "Orbiting Skill": "공전 스킬", "Spell": "주문", "Spells": "주문",
    "Spell Projectile": "주문 투사체", "Spell Projectiles": "주문 투사체",
    "Ranged Projectile": "원거리 투사체", "Ranged Attack": "원거리 공격",
    "Ranged Attacks": "원거리 공격", "Melee": "근접", "Ranged": "원거리",
    # weapons and handedness
    "Axe": "도끼", "Axes": "도끼", "Sword": "검", "Mace": "둔기",
    "Dagger": "단검", "Claw": "클로", "Polearm": "장창", "Staff": "지팡이",
    "Cane": "완드", "Shield": "방패", "Bow": "활", "Gun": "총",
    "Two Handed": "양손", "Two-Handed": "양손", "One Handed": "한손",
    "Dual Wielding": "쌍수 착용", "Dual Wield": "쌍수 착용",
    "Staff or Cane": "지팡이 또는 완드",
    # common compounds seen in stat names
    "Mana Cost": "마나 소모", "Damage Reduction": "데미지 감소",
    "Experience Gain": "경험치 획득", "Summon Life": "소환수 생명력",
    "Summon Amount": "소환수 수", "Summon Attack": "소환수 공격",
    "Sentry": "포탑", "Sentries": "포탑", "Flask": "물약", "Flasks": "물약",
    "Slow": "둔화", "Shocked": "감전", "Inferno": "지옥불",
    "Skill Haste": "스킬 가속", "Rage Stack": "분노 중첩",
    "Mage Guard Stack": "마법 보호 중첩", "Wizardry Stack": "마법 중첩",
    "Life Replenished": "생명력 회복", "Mana Replenished": "마나 회복",
    "Missiles": "투사체", "Terrain": "지형", "Portion": "일부",
    "Explosion AoE": "폭발 광역", "Serrated Chains": "톱니 사슬",
    "Shadow Burning": "암흑 연소", "Shadowburn": "암흑 연소",
    "Deep Frozen": "심층 빙결", "Frost Bitten": "동상", "Frostbitten": "동상",
    "Bosses": "보스", "Boss": "보스", "Missile": "투사체",
    "Attack Rate": "공격 빈도", "Cast Speed": "시전 속도",
    "Hit Recovery": "피격 회복", "Crowd Control": "군중 제어",
    "Immunity": "면역", "Evade": "회피", "Suppress": "억제",
    "Pull": "끌어당김", "Knockback": "밀쳐내기", "Fork": "분열",
    "Echo": "메아리", "Multishot": "다중 사격",
    "Absorbed": "흡수", "Absorb": "흡수",
    # Split as "All" + "Damage Taken" the game's standalone "All" (모두) reads
    # wrong; keep the whole phrase as one term.
    "All Damage Taken": "받는 모든 데미지",
    "All Damage": "모든 데미지",
    # Placeholder the affix templates use for the rolled target.
    "x": "x",
    # remaining stat vocabulary
    "Maximum": "최대", "Minimum": "최소", "Total": "합계", "All": "모든",
    "Added": "추가", "Additional": "추가", "Extra": "추가", "Increase": "증가",
    "Effect": "효과", "Effects": "효과", "Size": "크기", "Range": "사거리",
    "Area": "범위", "Rate": "속도", "Time": "시간", "Dmg": "데미지",
    "Taken": "받는", "Returned": "반사", "Inflicted": "적용", "Inflict": "적용",
    "Resist": "저항", "Steal": "흡수", "Gain": "획득", "Dealt": "가한",
    "Ignored": "무시", "Incoming": "들어오는", "Random": "무작위",
    "Self": "자신", "Full": "최대", "Critical": "치명타", "Critically": "치명적으로",
    "Orb": "구슬", "Orbiting": "공전", "Orbital": "궤도", "Splash": "비산",
    "Potion": "물약", "Freeze": "빙결", "Permafrost": "영구 동토",
    "Rabies": "광견병", "Colossus": "거신", "Void": "공허", "Codex": "고서",
    "Crowd Control": "군중 제어", "Movement": "이동", "Follower": "추종자",
    "Buffing": "버프", "Enhanced": "강화", "Close Combat": "근접 전투",
    "Recouped": "회수", "Attacking": "공격", "Chain": "연쇄",
    "Rest in Peace": "안식", "Sand": "모래", "Gas Cloud": "가스 구름",
    "Wound": "상처", "Wounds": "상처", "Evasion Amount": "회피량",
    "Execution": "처형", "Execute": "처형", "Immovable": "부동",
    "Bounce": "튕김", "Bounces": "튕김", "Fan": "부채꼴", "Arc": "호",
    "Volley": "일제 사격", "Shockwave": "충격파", "Ripple": "파문",
    "Branch": "분기", "Death Explosion": "사망 폭발",
    "Bone Fragment": "뼈 조각", "Sentries": "포탑",
    "Mercenary": "용병", "Merchant": "상인", "Prices": "가격",
    "Diminish": "감쇠", "Immune": "면역", "Suppressed": "억제됨",
    "Replenish": "회복", "Replenished": "회복", "Drains": "소모",
    "Missiles": "투사체", "Guard": "보호", "Haste": "가속",
    "Weakness": "약화", "Vulnerability": "취약",
    # verbs used by the verb-inversion rule
    "Absorb": "흡수", "Reflect": "반사", "Recover": "회복", "Pierce": "관통",
    "Leave": "남기기", "Unleash": "발동", "Perform": "수행",
}

# Class names appear inside "All Skills (X)"; keep them consistent with the
# class catalogue.
CLASSES = {
    "Amazon": "아마존", "Bard": "음유시인", "Butcher": "도살자",
    "Demon Slayer": "악마 사냥꾼", "Demonspawn": "마족", "Exo": "엑소",
    "Illusionist": "환술사", "Jotunn": "요툰", "Marauder": "약탈자",
    "Marksman": "명사수", "Necromancer": "네크로맨서", "Nomad": "유랑자",
    "Paladin": "팔라딘", "Pirate": "해적", "Plague Doctor": "역병 의사",
    "Prophet": "예언자", "Pyromancer": "화염술사", "Redneck": "촌뜨기",
    "Samurai": "사무라이", "Shaman": "주술사", "Shield Lancer": "방패 창병",
    "Stormweaver": "폭풍술사", "Viking": "바이킹", "White Mage": "백마법사",
    "Class": "클래스",
}

TERMS = {**GLOSSARY, **CLASSES}


def load_catalog_terms() -> int:
    """Reuse everything already translated as vocabulary.

    Item proc lines read "cast Anchor Swing Level 40" — the skill name inside is
    already in the catalogue from the game's own tables, so the line only needs
    the frame around it. Long entries are skipped: a whole sentence sitting in
    the glossary would let one description masquerade as a term inside another.
    """
    entries: dict[str, str] = {}
    # The hand-written layer is applied after composition, so read it directly:
    # otherwise a subtree blurb cannot use the skill name someone just
    # translated, and stays English for one more build.
    for path in (CATALOG, MANUAL):
        try:
            entries.update(json.load(open(path, encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    added = 0
    for english, korean in entries.items():
        if not korean or english in TERMS or len(english.split()) > 6:
            continue
        if english.endswith("."):
            continue
        TERMS[english] = korean
        added += 1
    return added


def load_game_terms() -> int:
    """Fold the game's own stat names into the glossary.

    The tree node lines ("+25 to Maximum Life") never appear verbatim in the
    shipped tables — the game assembles them from a stat name and a number — so
    they cannot be imported, only composed. Composing them from the game's own
    terms keeps the tree reading the same as the rest of the app, which is now
    filled straight from those tables.

    Only short noun phrases are taken: a sentence in the glossary would let a
    whole description masquerade as a term.
    """
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        from i18n_import_game_csv import find_game_dir, read_tables
    except ImportError:
        return 0
    game_dir = find_game_dir(None)
    if not game_dir:
        return 0
    added = 0
    for english, korean in read_tables(game_dir).items():
        if len(english.split()) > 5:
            continue
        # A trailing period means a sentence; "!" and "?" are part of skill
        # names like "Throw!" and "Land Ahoy!", which belong in the glossary.
        if english.endswith(".") or "," in english:
            continue
        # The game's wording wins over the hand-written glossary. Otherwise a
        # composed line says 피해 while every line imported straight from the
        # tables says 데미지, and the same stat reads two ways on one screen.
        TERMS[english] = korean
        added += 1
    return added

# ------------------------------------------------------------------- shapes

# A literal quantity: 25, 2.5, 10-20, [1-3]. Carried through untranslated.
NUM = r"\[?[+-]?\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\]?"

# (pattern, formatter). Groups are translated recursively, so "Increased Extra
# Fire Damage" resolves through two rules before hitting the glossary.
RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^All Skills \((.+)\)$"), "모든 스킬 ({0})"),
    # Tree and affix lines put the quantity first; Korean puts it last.
    (re.compile(rf"^\+({NUM})% to (.+)$"), "{1} +{0}%"),
    (re.compile(rf"^\+({NUM})%\s+(.+)$"), "{1} +{0}%"),
    (re.compile(rf"^\+({NUM}) to (.+)$"), "{1} +{0}"),
    (re.compile(rf"^\+({NUM})\s+(.+)$"), "{1} +{0}"),
    (re.compile(rf"^-({NUM})% to (.+)$"), "{1} -{0}%"),
    (re.compile(rf"^-({NUM})%\s+(.+)$"), "{1} -{0}%"),
    (re.compile(rf"^-({NUM})\s+(.+)$"), "{1} -{0}"),
    (re.compile(rf"^(.+) [Ii]ncreased by ({NUM})%$"), "{0} {1}% 증가"),
    (re.compile(rf"^(.+) [Rr]educed by ({NUM})%$"), "{0} {1}% 감소"),
    # Affix templates leave the number out entirely — the roll fills it in.
    (re.compile(r"^(.+) [Ii]ncreased by %$"), "{0} % 증가"),
    (re.compile(r"^(.+) [Rr]educed by %$"), "{0} % 감소"),
    (re.compile(r"^%\s+(.+)$"), "{0} %"),
    (re.compile(r"^\+%\s+(.+)$"), "{0} +%"),
    (re.compile(rf"^(.+) reduced by ({NUM})%$"), "{0} {1}% 감소"),
    (re.compile(r"^Increased (.+)$"), "{0} 증가"),
    (re.compile(r"^Decreased (.+)$"), "{0} 감소"),
    (re.compile(r"^Reduced (.+)$"), "{0} 감소"),
    (re.compile(r"^Extra (.+?) to (.+)$"), "{1}에게 추가 {0}"),
    (re.compile(r"^Extra (.+)$"), "추가 {0}"),
    (re.compile(r"^Additional (.+)$"), "추가 {0}"),
    (re.compile(r"^Additive (.+)$"), "합연산 {0}"),
    (re.compile(r"^Flat (.+)$"), "고정 {0}"),
    (re.compile(r"^Ignore (.+)$"), "{0} 무시"),
    (re.compile(r"^Chance to (.+)$"), "{0} 확률"),
    (re.compile(r"^Chance for (.+)$"), "{0} 확률"),
    (re.compile(r"^Chance on Hit to (.+)$"), "타격 시 {0} 확률"),
    (re.compile(r"^Chance when Attacking to (.+)$"), "공격 시 {0} 확률"),
    # Verb-initial phrases invert: English puts the verb first, Korean last, so
    # "Block Attacks" is "공격 막기" and not the "막기 공격" a noun-pile split
    # would produce.
    (re.compile(r"^(Block|Evade|Dodge|Suppress|Ignore|Inflict|Recover|Replenish"
                r"|Absorb|Reflect|Pierce|Leave|Unleash|Perform) (.+)$"), "{1} {0}"),
    # Sub-skill blurbs: 222 of them are this one sentence, and the subtree
    # name inside is already translated.
    (re.compile(r"^Core of the (.+) subtree\.$"), "{0} 하위 트리의 핵심입니다."),
    # Item proc lines: "cast Anchor Swing Level [60-80]".
    (re.compile(r"^cast (.+) Level (.+)$"), "{0} 레벨 {1} 시전"),
    (re.compile(r"^(.+) Converted [Tt]o (.+)$"), "{0}를 {1}로 전환"),
    (re.compile(r"^(.+) Increased$"), "{0} 증가"),
    (re.compile(r"^(.+) Reduced$"), "{0} 감소"),
    (re.compile(r"^(.+) Break$"), "{0} 파괴"),
    (re.compile(r"^(.+) Resistance$"), "{0} 저항"),
    (re.compile(r"^(.+) Absorption$"), "{0} 흡수"),
    (re.compile(r"^(.+) Duration \(s\)$"), "{0} 지속시간 (초)"),
    (re.compile(r"^(.+) Duration$"), "{0} 지속시간"),
    (re.compile(r"^(.+) Damage$"), "{0} 피해"),
    (re.compile(r"^(.+) Chance$"), "{0} 확률"),
    (re.compile(r"^(.+) Speed$"), "{0} 속도"),
    (re.compile(r"^(.+) Radius$"), "{0} 반경"),
    (re.compile(r"^Charm (\d+)$"), "부적 {0}"),
    (re.compile(r"^(.+) \(Based on Level\)$"), "{0} (레벨 비례)"),
    (re.compile(r"^(.+) with (.+)$"), "{1} 사용 시 {0}"),
    (re.compile(r"^(.+) per (.+)$"), "{1}당 {0}"),
    # "Level of Struck Skills" is "피격 스킬 레벨": the possessor leads in
    # Korean, so the halves swap rather than keeping the English order.
    (re.compile(r"^(.+) of (.+)$"), "{1} {0}"),
    (re.compile(r"^(.+) from (.+)$"), "{1}에서 오는 {0}"),
    (re.compile(r"^(.+) when (.+)$"), "{1} 시 {0}"),
    (re.compile(r"^(.+) on (.+)$"), "{1} 시 {0}"),
]

NUMERIC = re.compile(rf"^{NUM}$")


@functools.lru_cache(maxsize=None)
def translate(text: str, depth: int = 0) -> str | None:
    """Korean for `text`, or None when any fragment is unknown.

    Memoised: `compound` tries every split point and both halves recurse back
    through the whole rule set, so the same fragments come up again and again —
    without the cache a long phrase takes exponential time.
    """
    text = text.strip()
    if not text:
        return None
    if NUMERIC.match(text):
        return text
    if text in TERMS:
        return TERMS[text]
    if depth >= 6:
        return None
    for pattern, template in RULES:
        m = pattern.match(text)
        if not m:
            continue
        parts = [translate(group, depth + 1) for group in m.groups()]
        if any(part is None for part in parts):
            continue  # another rule may still split this phrase cleanly
        return template.format(*parts)
    return compound(text, depth)


def compound(text: str, depth: int) -> str | None:
    """Translate a bare noun pile by splitting it in two.

    Korean is head-final here too, so the halves keep their order. Split points
    are tried left to right, which makes the right-hand side as long as
    possible: "All Damage Taken" then resolves as "All" + "Damage Taken"
    ("모든 받는 피해") rather than "All Damage" + "Taken", which would strand
    the modifier behind its noun.
    """
    words = text.split(" ")
    if not 2 <= len(words) <= 8:
        return None
    for cut in range(1, len(words)):
        left = translate(" ".join(words[:cut]), depth + 1)
        if left is None:
            continue
        right = translate(" ".join(words[cut:]), depth + 1)
        if right is not None:
            return f"{left} {right}"
    return None


def main(write: bool) -> int:
    added = load_game_terms()
    if added:
        print(f"glossary: +{added} terms from the installed game")
    reused = load_catalog_terms()
    if reused:
        print(f"glossary: +{reused} terms reused from the catalogue")
    sources = json.load(open(SOURCES, encoding="utf-8"))
    catalog = json.load(open(CATALOG, encoding="utf-8"))

    produced = 0
    already = sum(1 for v in catalog.values() if v)
    for msgid in sources:
        if catalog.get(msgid):
            continue  # never overwrite a hand-written translation
        korean = translate(msgid)
        if korean:
            catalog[msgid] = korean
            produced += 1

    total = len(sources)
    done = already + produced
    print(f"catalogue: {total} entries")
    print(f"already translated: {already}")
    print(f"composed now: {produced}")
    print(f"coverage: {done}/{total} ({100 * done / total:.1f}%)")

    if write:
        with open(CATALOG, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({k: catalog.get(k, "") for k in sources}, fh,
                      ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"wrote {CATALOG}")
    else:
        print("(dry run — pass --write to save)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--write" in sys.argv))
