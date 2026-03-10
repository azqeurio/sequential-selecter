# Sequential Selector

사진을 빠르게 비교·선별하고,  편집 / webp 출력/ 프레임 씌우기/ AI 노이즈 제거까지 한 곳에서 해결하는 데스크톱 사진 워크플로우 애플리케이션입니다.

A powerful all-in-one desktop photo workflow app for fast culling, editing, webp output, frame design, AI denoising, and batch export.

---

# 🇰🇷 한국어

## 소개
**Sequential Selector**는 수많은 사진(RAW 파일 및 연속촬영 결과물 포함)을 빠르게 비교·선별하고, 보정과 AI 노이즈 제거를 적용하며, 프레임과 함께 일괄 내보낼 수 있도록 설계된 올인원 사진 앱입니다.

## 핵심 기능

### 📸 초고속 브라우징 & 듀얼 뷰어
- **그리드 뷰** —  사진을 끊김 로드 (Ctrl + 휠로 썸네일 크기 조절)
- **듀얼 프리뷰 슬롯** — 상/하 두 개의 슬롯에 사진을 띄워 마우스 드래그로 세밀하게 비교
- **줌/스크롤 상태 유지** — 확대 후 다른 사진으로 넘어가도 동일한 줌·위치 유지
- **공통/독립 줌 모드** — 두 뷰어의 줌 상태를 동기화하거나 독립적으로 운용 가능
- 화살표 키 탐색 지원

###   등급분류 (Rating & Filtering)
- **1–5 Star 별점** 
- **Reject (X)** 처리로 불필요한 사진 빠르게 걸러내기
- 필터링 패널을 통해 원하는 등급의 사진만 모아보기
- 그리드 뷰에서 바로 평점 매기기 지원

###  사진 에디터 (Photo Editor)
간단한 편집 기능:

- **색보정** — 노출, 대비, 하이라이트, 섀도, 화이트, 블랙, 선명도, 채도, 활력, 색온도, 색조, 안개 제거, 비네팅, 입자, 샤프닝
- **크롭 & 회전** — 자유 크롭, ±90° 수동 회전, 회전 시 3×3 그리드 오버레이
- **자동 수평** — `HoughLinesP` 기반 수평선 감지로 자동 수평 보정
- **자동 기하 보정** — 수직/수평 원근 왜곡을 자동 분석하여 보정
- **LUT / XMP / JSON 프리셋** — `.cube` LUT, Adobe XMP, JSON 프리셋 로드/저장
- **AI 노이즈 제거** — Swin2SR, SCUNet, Real-ESRGAN 모델 (spandrel) 지원
- **일괄 적용 & 내보내기** — 현재 편집을 모든 이미지에 적용 후 일괄 내보내기 (WebP / JPG / PNG, 품질·크기 설정)


###   프레임 에디터
사진에 여백·촬영 정보를 삽입하는  프레임 :

- **자동 EXIF 추출** — 카메라 기종, 렌즈, 조리개, 셔터스피드, ISO
- **스플릿 뷰** — 가로/세로 사진을 동시에 독립적으로 디자인
- **드래그 & 스냅** — 텍스트/이미지를 캔버스 내에서 자유로이 이동, 중앙·테두리 스냅 정렬
- **독립 여백 설정** — 상/하/좌/우 여백 각각 조절
- **커스텀 디자인** — 프레임 색상, 텍스트 색상 (Hex 코드), 폰트 선택
- **프리셋 저장/불러오기** — JSON으로 레이아웃 저장 및 재사용
- **카메라 로고 추가**

###  사진 정리기 (Photo Organizer)
SD 카드나 폴더 내 사진을 자동 분류:

- 카메라 / 렌즈 / 날짜 / 파일 유형 기반 폴더 구조 생성
- RAW / JPG 분리 옵션
- 미리보기 트리 & 스캔 → 정리 워크플로우
- 중복 정책: 묻기 / 건너뛰기 / 새 이름 저장
- 복사 또는 이동 선택

###  일괄 처리 & 안전장치
- 여러 장의 사진을 선택 후 일괄 Export
- 드래그 앤 드롭 및 단축키(1, 2)로 Target 폴더에 사진 이동
- Multi-Threading으로 UI 블로킹 없는 부드러운 처리
- `Ctrl + Z`로 파일 이동 즉시 취소 가능
- 이름 충돌 시 자동 안전한 이름 부여

###  다국어 지원
- 한국어 / English 실시간 전환

## 지원 이미지 포맷
| 구분 | 확장자 |
|------|--------|
| **일반 이미지** | `.jpg` `.jpeg` `.png` `.bmp` `.gif` `.tif` `.tiff` `.webp` |
| **HEIF/HEIC** | `.heic` `.heif` |
| **RAW** | `.arw` `.cr2` `.cr3` `.nef` `.rw2` `.orf` `.raf` `.dng` |

---

##  설치 및 실행

### Windows (설치 파일)
GitHub **Releases** 탭에서 `.exe` 파일 다운로드 → Python 설치 없이 바로 실행

### macOS (설치 파일)
GitHub **Releases** 탭에서 `.zip` 파일 다운로드 → 압축 해제 후 `.app` 실행

### 직접 실행 (Python 3.10+)
```bash
# 필수 패키지 설치
pip install PySide6 Pillow rawpy pillow-heif exifread opencv-python numpy

# 프로그램 실행
python run.py
```

### 빌드 (PyInstaller)
```bash
pip install pyinstaller

# Windows
pyinstaller ssc.spec

# macOS
pyinstaller ssc_macos.spec
```

> **AI 노이즈 제거**를 사용하려면 `torch`와 `spandrel`이 필요합니다. 앱 내 "Install AI Models" 버튼으로 자동 설치되거나 수동으로 설치할 수 있습니다:
> ```bash
> pip install torch torchvision spandrel
> ```

---

## 단축키
| 키 | 기능 |
|----|------|
| `1` / `2` | Target1 / Target2 폴더로 사진 이동 |
| `0–5` | 별점 지정 |
| `X` | Reject 처리 |
| `←` `→` | 이전/다음 사진 |
| `Ctrl + Z` | 실행 취소 |
| `Ctrl + Y` | 재실행 |
| `Ctrl + Wheel` | 썸네일 크기 조절 |

---

## 라이선스
이 소프트웨어는 **MIT License**로 배포됩니다.

---
---

# 🇺🇸 English

## Overview
**Sequential Selector** is a professional all-in-one desktop photo workflow application. It combines lightning-fast photo culling, Lightroom-grade color editing, AI-powered noise reduction, a fully customizable EXIF frame editor, and intelligent photo organization — all in a single tool.

## Key Features

###  Fast Grid & Dual Viewer
- **Grid View** — Seamlessly load hundreds of photos (Ctrl + Wheel to resize thumbnails)
- **Dual Preview Slots** — Compare two images side-by-side with mouse-drag panning
- **Persistent Zoom/Pan** — Zoom position preserved across photo navigation
- **Linked / Independent Zoom** — Sync or decouple zoom across both viewers
- Arrow key navigation

###  Professional Rating & Filtering
- **1–5 Star ratings** and **Color labels** (Red, Yellow, Green, Blue, Purple)
- **Reject (X)** tagging for quick culling
- Filter panel to show only specific ratings or approved photos
- Rate directly from grid view

###  Photo Editor
Professional Lightroom-style photo editing:

- **Color Science** — Exposure, contrast, highlights, shadows, whites, blacks, clarity, saturation, vibrance, temperature, tint, dehaze, vignette, grain, sharpening
- **Crop & Rotate** — Free crop box, ±90° manual rotation with 3×3 grid overlay
- **Auto Level** — HoughLinesP-based horizon detection for automatic straightening
- **Auto Geometry** — Automatic vertical/horizontal perspective correction
- **Preset Support** — Load/save `.cube` LUT, Adobe XMP, and JSON presets
- **AI Denoising** — Swin2SR, SCUNet, Real-ESRGAN models via spandrel
  - Auto-detects CUDA · Apple MPS · CPU
  - ~15 seconds for 5220×3912 on RTX 3060 12GB
  - One-click model download & installation
- **Batch Apply & Export** — Apply current edits to all images, export as WebP/JPG/PNG with quality and size options
- **Undo / Redo** — Full Ctrl+Z / Ctrl+Y support for all edits

###  EXIF Frame Editor
Add stylish borders with shooting info to your photos:

- **Auto EXIF extraction** — Camera body, lens, aperture, shutter speed, ISO
- **Split View** — Design landscape & portrait templates simultaneously
- **Drag & Snap** — Freely move text/images on canvas with center/edge snapping
- **Independent Margins** — Top/Bottom/Left/Right margin control
- **Custom Styling** — Frame color, text color (hex), font selection
- **Preset Save/Load** — Store layouts as JSON for reuse
- **Camera Logo Support**

###  Photo Organizer
Automatically sort photos from SD cards or folders:

- Organize by camera / lens / date / file type
- Separate RAW and JPG option
- Preview tree & scan → sort workflow
- Duplicate policy: Ask / Skip / Rename
- Copy or Move mode

###  Batch Pipeline & Safety
- Batch export with EXIF frames applied
- Drag-and-drop or keyboard shortcuts (1, 2) to move to target folders
- Multi-threaded processing without UI freezing
- `Ctrl + Z` to instantly undo file moves
- Automatic safe filename on conflicts

###  Bilingual Interface
- Korean / English real-time language toggle

## Supported Formats
| Category | Extensions |
|----------|-----------|
| **Standard** | `.jpg` `.jpeg` `.png` `.bmp` `.gif` `.tif` `.tiff` `.webp` |
| **HEIF/HEIC** | `.heic` `.heif` |
| **RAW** | `.arw` `.cr2` `.cr3` `.nef` `.rw2` `.orf` `.raf` `.dng` |

---

##  Installation

### Windows (Prebuilt)
Download the `.exe` from the GitHub **Releases** tab — no Python required.

### macOS (Prebuilt)
Download the `.zip` from the GitHub **Releases** tab — extract and run the `.app` bundle.

### Run from Source (Python 3.10+)
```bash
# Install dependencies
pip install PySide6 Pillow rawpy pillow-heif exifread opencv-python numpy

# Run
python run.py
```

### Build Standalone Executable
```bash
pip install pyinstaller

# Windows
pyinstaller ssc.spec

# macOS
pyinstaller ssc_macos.spec
```

> **AI Denoising** requires `torch` and `spandrel`. The app can auto-install them via the built-in "Install AI Models" button, or install manually:
> ```bash
> pip install torch torchvision spandrel
> ```

---

## Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `1` / `2` | Move photo to Target1 / Target2 |
| `0–5` | Set star rating |
| `X` | Reject photo |
| `←` `→` | Previous / Next photo |
| `Ctrl + Z` | Undo |
| `Ctrl + Y` | Redo |
| `Ctrl + Wheel` | Resize thumbnails |

---

## License
This software is distributed under the **MIT License**. Feel free to use and contribute!

