<img width="1600" height="360" alt="wordmark-1600" src="https://github.com/user-attachments/assets/fe4fd4b3-a475-438a-a87e-53fd8080632d" />


**Hero Siege** 빌드 플래너의 한글판입니다. 특성 트리, 장비, 스탯, 스킬을 계산합니다.

원본은 [HeroSiegePlanner/HSPlanner](https://github.com/HeroSiegePlanner/HSPlanner)이고,
이 저장소는 거기서 갈라져 나온 한글화 포크입니다.

[![Release](https://img.shields.io/github/v/release/tablet7823-beep/HSPlanner)](https://github.com/tablet7823-beep/HSPlanner/releases/latest)
[![Download](https://img.shields.io/github/v/release/tablet7823-beep/HSPlanner?label=Download)](https://github.com/tablet7823-beep/HSPlanner/releases/latest)

---

## 한글판에 대하여

용어는 **Hero Siege가 게임과 함께 배포하는 자체 번역 테이블**(`translations*.csv`)에서
그대로 가져왔습니다. 그래서 플래너에 뜨는 스킬·아이템·스탯 이름이 게임 화면의 표기와
일치합니다. 게임 테이블에 한국어가 없는 항목 — 룬 이름(`Ber`, `Eth`, `Xo` 등)과
일부 아이템 — 은 게임에서도 영문으로 나오므로 그대로 두었습니다.

게임 데이터 99.6%, 인터페이스 98.4%가 번역되어 있습니다.

### 번역 고치기

앱을 다시 설치하지 않고 번역만 바꿀 수 있습니다. 아래 위치에 JSON을 놓으면
내장 번역을 **항목 단위로** 덮어씁니다. 파일에 없는 항목은 내장 번역을 그대로 씁니다.

```
%APPDATA%\com.zium.hsplanner\gpui\i18n\ko.json      게임 데이터
%APPDATA%\com.zium.hsplanner\gpui\i18n\ui\ko.json   인터페이스
```

```json
{ "Attack Damage": "공격 데미지" }
```

앱을 업데이트하거나 다시 설치해도 이 폴더는 남습니다.

---

## 설치

1. [최신 릴리스](https://github.com/tablet7823-beep/HSPlanner/releases/latest)로 갑니다.
2. **Assets**에서 `hsplanner_<버전>_x64-setup.exe`를 받아 실행합니다.

현재 한글판은 **Windows 10/11 x64**만 제공합니다. macOS나 Linux가 필요하면
[원본 릴리스](https://github.com/HeroSiegePlanner/HSPlanner/releases/latest)의
영문판을 쓰세요.

설치 위치와 저장 폴더가 원본과 같으므로, 공식 영문판과 한글판을 **동시에 설치할 수는
없습니다.** 대신 이미 만들어 둔 빌드는 그대로 이어받습니다.

### 실행 요구사항

내려받은 앱은 그 자체로 완결되어 있습니다. Node나 Rust를 따로 설치할 필요가 없고,
예전 웹뷰 기반일 때 필요했던 WebView2도 더 이상 쓰지 않습니다.

| 플랫폼 | 필요한 것 |
|---|---|
| Windows 10/11 x64 | 없음 |
| macOS 15+ (Apple Silicon) | 없음 |
| Linux x64 | 네이티브 Wayland 세션과 Vulkan 드라이버 |

---

## 기능

플래너는 탭으로 나뉩니다.

<details>
<summary>캐릭터 — 읽기 전용 요약: 클래스, 레벨, 능력치, 현재 빌드의 데미지·방어 수치</summary>

<img width="1696" height="1037" alt="캐릭터 탭" src="docs/screenshots/character.webp" />

</details>

<details>
<summary>인카네이션 트리 — 확대·이동이 되는 특성 그래프. 자동 경로 탐색, 마우스를 올리면 경로 미리보기, 미니맵, 초기화</summary>

<img width="1696" height="1037" alt="인카네이션 트리 탭" src="docs/screenshots/tree.webp" />

</details>

<details>
<summary>에테르 트리 — 인카네이션 트리와 같은 방식이며, 자체 노드 그래프와 요약 패널을 가집니다</summary>

<img width="1696" height="1037" alt="에테르 트리 탭" src="docs/screenshots/ether.webp" />

</details>

<details>
<summary>스킬 — 선행 조건과 레벨별 상한을 지키는 포인트 분배, 하위 스킬 포함</summary>

<img width="1696" height="1037" alt="스킬 탭" src="docs/screenshots/skills.webp" />

</details>

<details>
<summary>장비 — 무기, 방어구, 부적, 장신구 슬롯. 소켓(젬·룬), 룬어 인식, 세트 보너스</summary>

<img width="1696" height="1037" alt="장비 탭" src="docs/screenshots/gear.webp" />

</details>

<details>
<summary>용병 — 자체 장비와 스탯 기여를 가진 용병 슬롯</summary>

<img width="1696" height="1037" alt="용병 탭" src="docs/screenshots/mercenary.webp" />

</details>

<details>
<summary>스탯 — 트리, 에테르, 장비, 용병, 능력치, 룬어, 세트에서 오는 보너스 합계</summary>

<img width="1696" height="1037" alt="스탯 탭" src="docs/screenshots/stats.webp" />

</details>

<details>
<summary>설정 — 클래스·레벨·능력치 분배, 조건부 토글, 진행도 슬라이더</summary>

<img width="1696" height="1037" alt="설정 탭" src="docs/screenshots/config.webp" />

</details>

<details>
<summary>노트 — 빌드마다 붙이는 위지윅 편집기. 공유 링크에도 함께 담깁니다</summary>

<img width="1696" height="1037" alt="노트 탭" src="docs/screenshots/notes.webp" />

</details>

<details>
<summary>필터 — 루트 필터 편집기. "빌드에서 생성" 기능 포함</summary>

네이티브 앱에서는 이 탭이 아직 열리지 않습니다(상단 메뉴에서 비활성 상태). 그래서
캡처를 싣지 않았습니다.

</details>

모든 탭에서 공통으로:

- [x] **접사** — 계열별로 접사를 추가하고 티어를 고른 뒤 굴림값을 드래그합니다 (아이템 부여 스킬 랭크도 굴립니다)
- [x] **사용자 지정 스탯** — 데이터 모델 밖의 항목을 직접 입력합니다
- [x] **시즌** — 시즌 10이 기본 데이터이고, 이후 시즌은 그 위에 패치 레이어로 얹힙니다
- [x] **빌드 메뉴** — 여러 빌드를 저장하고, 빌드마다 여러 프로필을 둡니다
- [x] **공유** — 빌드 전체를 압축된 URL로 내보냅니다 (lz-string)
- [x] **업데이트 확인** — GitHub 릴리스로 새 버전을 확인합니다

<img width="1696" height="1037" alt="빌드 라이브러리" src="docs/screenshots/library.webp" />

---

## 개발

안정판 Rust와 `.github/workflows/native.yml`에 적힌 플랫폼 의존성이 필요합니다.
대상은 macOS 15+ Apple Silicon, Windows 10/11 x64, 네이티브 Wayland를 쓰는 Linux x64입니다.

```bash
cargo run -p hsplanner
cargo build --release -p hsplanner
```

실행 파일은 `target/release/hsplanner`(Windows는 `.exe`)에 생깁니다.
설치 파일은 `python tools/package-native.py`로 만듭니다. 자세한 내용은
[packaging/README.md](packaging/README.md)를 보세요.

### 한글화 도구

카탈로그는 손으로 고치지 않고 스크립트로 다시 만듭니다. 쌓는 **순서가 곧 우선순위**입니다.

```bash
python tools/i18n_build.py             # 추출 → 게임 CSV → 조립 → 수작업
python tools/i18n_extract_ui.py scan   # tr()이 덮고 있는 인터페이스 문구를 센다
python tools/i18n_extract_ui.py leaks  # tr() 밖에 남은 화면 문구를 잡는다
python tools/i18n_lint.py              # 번역된 tr()이 비교에 쓰이는 곳을 잡는다
```

업스트림이 게임 데이터를 갱신하면 `i18n_build.py`만 다시 돌리면 됩니다.

`i18n_lint.py`는 반드시 돌리세요. `tr()`은 카탈로그에 없는 문자열을 그대로 돌려주기
때문에, 잘못 감싸도 당장은 멀쩡해 보이다가 그 문구에 번역이 생기는 순간 비교가
조용히 실패합니다.

`leaks`는 `wrap`이 손댈 수 없는 자리를 찾습니다. `format!`은 리터럴을 요구해서
`tr()`로 감쌀 수 없고 대문자 리터럴은 상수처럼 보이는데, 둘 다 화면에는 그대로
나옵니다. 여기 걸린 문구는 `tr("… {name}").replace("{name}", …)` 꼴로 손수
바꿔야 합니다. 번역하면 안 되는 자리(아이템 텍스트 형식, 진단 출력, 요소 id)는
`i18n_extract_ui.py`의 `ALLOWED`에 사유와 함께 적어 두었습니다.

### 프로젝트 구조

| 경로 | 내용 |
|---|---|
| `crates/` | 네이티브 GPUI 앱, 화면, 문서, 공용 UI |
| `engine/` | 공용 Rust 계산, OCR, 추천 |
| `data/` | 공용 게임 JSON. 현재 기준은 시즌 10 |
| `data/i18n/` | 번역 카탈로그 (`ko.json`, `ui/`, `manual/`, `context/`) |
| `assets/` | 공용 그래픽 (스킬, 아이템, 트리 노드) |
| `packaging/` | 설치 파일 설정과 아이콘 |
| `tools/` | 패키징과 한글화 도구 |

---

## 자주 묻는 질문

**Q:** *게임 세이브 파일을 플래너로 가져올 수 있나요?*

**A:** *할 수 없습니다. EULA/TOS 위반입니다.*

**Q:** *공식 영문판과 같이 쓸 수 있나요?*

**A:** *설치 위치와 식별자가 같아서 함께 설치되지는 않습니다. 저장해 둔 빌드는
같은 폴더를 쓰므로 어느 쪽을 설치해도 그대로 남습니다.*

**Q:** *번역이 어색한 곳을 찾았습니다.*

**A:** *위의 "번역 고치기"대로 `ko.json`을 놓으면 바로 바꿀 수 있습니다.
[이슈](https://github.com/tablet7823-beep/HSPlanner/issues)로 알려주셔도 됩니다.*

---

원작자 **zium**의 작업 위에 만들어졌습니다. Hero Siege © Panic Art Studios — 공식과 무관합니다.
