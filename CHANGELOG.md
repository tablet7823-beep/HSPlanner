## Unreleased

### 한글판 (Korean build)

- 인터페이스와 게임 데이터를 한국어로 번역했습니다. 용어는 Hero Siege가 배포하는
  자체 번역 테이블을 그대로 따르므로, 플래너와 게임 화면의 표기가 일치합니다.
- 룬 이름과 일부 아이템 이름은 게임에서도 영문으로 표시되어 그대로 두었습니다.
- 앱 옆에 `i18n/ko.json`을 놓으면 내장 번역을 항목 단위로 덮어쓸 수 있습니다
  (`%APPDATA%\com.zium.hsplanner\gpui\i18n\ko.json`).
- 장비 칸을 우클릭하면 바로 비웁니다.
- 팝업이 Esc와 바깥 클릭 양쪽으로 닫힙니다. 저장하지 않은 변경이 있으면 먼저 확인합니다.
- 앱 내 업데이트는 이 포크의 릴리스를 봅니다. 원본의 영문판으로 덮어써지지 않습니다.


- Restored the Release workflow with version/tag input and a prerelease option. It synchronizes native versions, tests and packages Windows/Linux/macOS, verifies combined checksums, and publishes the complete release using this changelog.

## Native desktop application

- HSPlanner now runs on pure `Rust`
- Incarnation and Ether trees keep their familiar design, with smooth navigation and responsive node previews.
- Net Change uses compact rows showing the absolute change and percentage and renders it aprox 4x faster
- Stats include source breakdowns and pinnable calculation details.
- Notes use Markdown with a formatted preview.

## Installing this version

Download the installer from GitHub. I can't figure it out how to update from webview to pure rust so you need to update it manually. From this version on, the native app checks GitHub for newer releases and can install them from the footer.
