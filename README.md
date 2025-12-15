# Sequential Selector
사진을 빠르게 비교·선별하기 위한 데스크톱 애플리케이션입니다.  
A desktop application for fast photo comparison and culling.

---

#  한국어 README

## 소개
**Sequential Selector** 는 연속촬영 사진을 빠르게 비교하고 정리하기 위해 설계된 데스크톱 애플리케이션입니다.  
폴더를 선택하면 이미지가 그리드 형태로 표시되며, 두 개의 프리뷰 슬롯을 통해 사진을 확대·이동하며 세밀하게 비교할 수 있습니다. 선택한 이미지는 드래그 앤 드롭 또는 단축키로 Target 폴더로 즉시 이동하여 정리 효율을 크게 높일 수 있습니다.

## 주요 기능

### • 그리드 썸네일 뷰
- 선택한 폴더의 이미지가 정사각형 썸네일로 표시됩니다.
- Ctrl + 마우스 휠 로 썸네일 크기를 80px~1600px 범위에서 확대/축소할 수 있습니다.
- 크게 확대하면 자동으로 고해상도 썸네일을 다시 로딩하여 화질을 유지합니다.

### • 듀얼 프리뷰 슬롯
- 상단 Slot1, 하단 Slot2 두 영역에서 서로 다른 사진을 동시에 비교할 수 있습니다.
- 마우스 드래그로 패닝, 마우스 휠로 확대/축소 가능(보조키 불필요).
- 줌/스크롤 상태는 다른 사진을 열어도 유지됩니다.

### • 다중 선택 및 드래그 이동
- 마우스 드래그로 러버 밴드 박스를 생성하여 여러 썸네일을 선택할 수 있습니다.
- 드래그 중 선택 개수가 표시되어 이동할 파일 수를 즉시 확인할 수 있습니다.
- 선택한 파일을 Target1 또는 Target2 라벨로 드래그하면 해당 폴더로 이동합니다.

### • 키보드 단축키
- 방향키: 썸네일 이동
- Enter: 현재 선택 이미지를 프리뷰에 표시
- 숫자키 `1` / `2`: Target1 / Target2 폴더로 이동  
  - 키를 누른 상태에서 썸네일 클릭: 단일 파일 즉시 이동  
  - 다중 선택 후 `1` 또는 `2`: 여러 파일을 한 번에 이동  
- `Ctrl + Z`: Undo  
- `Ctrl + Y`: Redo  

### • 듀얼 모드 (Dual Mode)
- `Ctrl + D` 또는 버튼으로 썸네일 창과 프리뷰 창을 분리/합치기 가능
- 듀얼 모니터 환경에서 유용함

### • Undo / Redo
- 파일 이동 실수 시 즉시 복구 가능
- 이름 충돌 시 자동으로 `_restored`, `_1` 등의 안전한 이름으로 저장

### • 언어 전환 및 도움말
- UI 언어를 한국어/영어로 즉시 전환 가능
- 프로그램 내 도움말 창 제공
- 후원 기능 제공

## 지원 이미지 포맷
- 일반 이미지: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tif`, `.tiff`
- HEIF/HEIC: `.heic`, `.heif`
- RAW: `.arw`, `.cr2`, `.cr3`, `.nef`, `.rw2`, `.orf`, `.raf`, `.dng`  
- NEF 파일은 내장 썸네일 우선 추출 후 RAW 디코딩을 시도하여 가능한 한 표시되도록 구현됨

---

## 설치 및 실행

### 1. Windows
- GitHub Releases에서 `.exe` 파일을 다운로드하여 바로 실행할 수 있습니다.
- Python 환경 없이 단일 실행 파일로 동작합니다.

### 2. macOS (직접 빌드)
macOS에서 `.app` 번들을 생성하려면 다음이 필요합니다.
- macOS 12 이상 (Apple Silicon 권장)
- Python 3.10 이상 (Homebrew 또는 python.org의 universal2 권장)

#### (1) 필수 패키지 설치
```bash
python3 -m pip install --upgrade pip
python3 -m pip install PySide6 rawpy pillow pillow-heif
python3 -m pip install pyinstaller
````

#### (2) .app 생성

`run.py` 가 있는 디렉터리에서 실행합니다:

```bash
pyinstaller \
  --name "Sequential Selector" \
  --windowed \
  run.py
```

빌드 후 `dist/Sequential Selector.app` 가 생성됩니다.

---

## 기본 사용 흐름

1. Image Folder 버튼으로 원본 폴더 선택
2. Target1 / Target2 폴더 지정
3. 더블 클릭으로 Slot1, `Ctrl + 더블블클릭` 으로 Slot2에 표시
4. `1` 또는 `2` 키, 또는 드래그 앤 드롭으로 파일 이동
5. 잘못 이동한 경우 `Ctrl + Z` 로 복구

---

## 라이선스

이 프로젝트는 MIT License를 따릅니다.
자세한 내용은 `LICENSE` 파일을 참고하십시오.

---

# English README

## Overview

**Sequential Selector** is a desktop tool designed for fast comparison and culling of similar photos.
It loads all images in a selected folder as square thumbnails and offers two independent preview slots for detailed zoom and pan comparison. Selected files can be moved to target folders using drag & drop or keyboard shortcuts.

## Features

### • Grid Thumbnail View

* Displays all images as square thumbnails.
* `Ctrl + mouse wheel` to zoom thumbnails (80px–1600px).
* High-resolution thumbnails reload automatically when zoomed in.

### • Dual Preview Slots

* Two independent preview areas (Slot1 top, Slot2 bottom).
* Pan with mouse drag, zoom with mouse wheel.
* Zoom and scroll positions persist across image changes.

### • Multi-Selection & Drag Moving

* Drag to create a rubber-band selection rectangle.
* Drag selected thumbnails onto Target1 or Target2 to move files.
* Selection count is displayed during dragging.

### • Keyboard Shortcuts

* Arrow keys: navigate thumbnails
* Enter: show selected image in preview
* Number keys:

  * `1`: move selection to Target1
  * `2`: move to Target2
  * Hold `1` or `2` while clicking: instantly move clicked image
  * Multi-select + `1` or `2`: move all at once
* `Ctrl + Z`: Undo
* `Ctrl + Y`: Redo

### • Dual Mode

* Toggle with `Ctrl + D` or button
* Splits thumbnail view and preview into separate windows
* Optimized for dual-monitor setups

### • Undo/Redo System

* Reverts mistaken moves
* Handles filename conflicts with automatic safe renaming

### • Language Toggle & Help

* Switch UI between Korean and English
* In-app help window included
* Donation link provided

## Supported Formats

* Standard: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tif`, `.tiff`
* HEIF/HEIC: `.heic`, `.heif`
* RAW: `.arw`, `.cr2`, `.cr3`, `.nef`, `.rw2`, `.orf`, `.raf`, `.dng`
* NEF files are decoded via embedded thumbnail first, then full RAW if needed

---

## Installation & Build

### Windows

Download the ready-to-use `.exe` file from GitHub Releases.
No Python environment is required.

### macOS (Build from source)

#### (1) Install dependencies

```bash
python3 -m pip install --upgrade pip
python3 -m pip install PySide6 rawpy pillow pillow-heif
python3 -m pip install pyinstaller
```

#### (2) Build the .app bundle

```bash
pyinstaller \
  --name "Sequential Selector" \
  --windowed \
  run.py
```

The generated application will be in `dist/Sequential Selector.app`.

---

## Basic Workflow

1. Choose source folder (Image Folder)
2. Set Target1 / Target2 folders
3. Double Click → Slot1, Ctrl+ Double Click → Slot2
4. Move files using keys (`1`, `2`) or drag & drop
5. Undo mistakes with `Ctrl + Z`

---

## License

This project is licensed under the MIT License.
See the `LICENSE` file for details.
