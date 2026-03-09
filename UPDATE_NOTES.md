# 📋 Sequential Selector 업데이트 노트

## 🆕 새로 추가된 기능

### 🎨 사진 에디터 (Photo Editor) — **완전히 새로운 모듈**
기존에 없던 라이트룸 스타일의 전문 사진 편집 기능이 추가되었습니다.

- **16종 보정 슬라이더** — 노출, 대비, 하이라이트, 섀도, 화이트, 블랙, 선명도(Clarity), 채도, 활력(Vibrance), 색온도, 색조(Tint), 안개제거(Dehaze), 비네팅, 입자(Grain), 샤프닝
- **자유 크롭** — 드래그 가능한 8핸들 크롭 박스
- **회전** — ±90° 수동 회전 슬라이더, 회전 시 3×3 그리드 오버레이
- **자동 수평 보정 (Auto Level)** — `cv2.HoughLinesP` 기반 수평선 감지 알고리즘
- **자동 기하 보정 (Auto Geometry)** — 수직/수평 원근 왜곡 자동 분석 및 보정
- **LUT / XMP / JSON 프리셋** — `.cube` LUT, Adobe XMP, JSON 프리셋 로드 및 저장
- **실행 취소/재실행** — 모든 편집 파라미터에 대해 Undo/Redo 스택 지원
- **고해상도 렌더링** — 프록시(저해상도) 미리보기 + 슬라이더 놓을 때 풀해상도 렌더 (RenderWorker)
- **일괄 적용** — 현재 편집 설정을 로드된 모든 이미지에 일괄 적용 후 내보내기

### 🤖 AI 노이즈 제거 (AI Denoising)
- **Swin2SR / SCUNet / Real-ESRGAN** 모델 지원 (spandrel 라이브러리 활용)
- **GPU 자동 감지** — CUDA (NVIDIA) · Apple MPS · CPU 자동 선택
- **최적화된 추론** — FP16 정밀도, 타일 기반 처리, RTX 3060 12GB 기준 5220×3912 이미지 약 15초
- **원클릭 설치** — 앱 내 "Install AI Models" 버튼으로 torch + spandrel + 모델 자동 다운로드
- **GPU 진단** — AI Diagnostics 대화상자로 GPU 상태, VRAM, 모델 현황 확인
- **취소 가능** — 처리 중 언제든 중단 가능

### 📂 사진 정리기 (Photo Organizer)
- SD 카드 및 폴더 내 사진을 **카메라 / 렌즈 / 날짜 / 파일 유형** 기반으로 자동 폴더 분류
- RAW / JPG 분리 옵션
- **미리보기 트리** — 정리 실행 전 폴더 구조 확인 가능
- **중복 정책** — 묻기 / 건너뛰기 / 새 이름 저장
- 복사 또는 이동 선택 가능
- EXIF 추출 엔진: Pillow → exifread → exiftool 3단계 폴백 방식

### 🌐 다국어 지원 (i18n)
- **한국어 / English 실시간 전환** — 버튼 한 번으로 전체 UI 언어 변경

---

## 🔄 개선된 기존 기능

### 📸 브라우징 & 뷰어
- **공통/독립 줌 모드** 추가 — 두 뷰어의 줌 상태를 동기화하거나 독립적으로 운용 가능
- GPU 가속 이미지 위젯 (`QGraphicsView` 기반)으로 대폭 성능 향상

### ⭐ 등급분류
- **그리드 뷰에서 직접 평점 매기기** 지원
- XMP 사이드카 파일 파싱으로 기존 라이트룸 등급/라벨 자동 반영

### 🖼️ EXIF 프레임 에디터
- **스플릿 뷰** — 가로/세로 템플릿을 동시에 독립적으로 디자인
- **스냅 정렬** — 텍스트/이미지 드래그 시 중앙·테두리 자동 스냅
- **카메라 로고 지원** 추가
- 내보내기 대화상자에서 이미지 수 표시 및 설정 제어

### 🚀 일괄 처리
- **내보내기 설정 대화상자** — 포맷 (WebP / JPG / PNG), 화질, 크기 옵션 UI 제공

---

## 🛠️ 기술적 변경사항

### 새로 추가된 의존성
| 패키지 | 용도 |
|--------|------|
| `opencv-python` | 자동 수평, 자동 기하 보정, 이미지 처리 |
| `numpy` | 색보정 연산 (Color Science) |
| `torch` + `spandrel` | AI 노이즈 제거 (선택사항, 런타임 설치) |

### 프로젝트 구조 확장
```
src/
├── core/
│   ├── image_editor.py    ← NEW: 라이트룸 스타일 색보정 엔진
│   ├── image_loader.py    ← NEW: PIL 이미지 로더
│   ├── metadata.py        ← NEW: EXIF 메타데이터 추출 (3단계 폴백)
│   ├── rating_manager.py  ← NEW: 별점/라벨 관리 (XMP 연동)
│   ├── sorter.py          ← NEW: 사진 정리 엔진
│   ├── xmp_parser.py      ← NEW: XMP 프리셋 파싱
│   └── utils.py           ← NEW: 해시, 파일명 유틸리티
├── gui/
│   ├── photo_editor.py    ← NEW: 사진 에디터 UI + AI 디노이즈
│   ├── exif_editor.py     ← NEW: EXIF 프레임 에디터 UI
│   ├── organizer_dialog.py← NEW: 사진 정리기 UI
│   ├── filter_dialog.py   ← NEW: 필터 다이얼로그
│   ├── viewer_widget.py   ← 뷰어 위젯 (분리)
│   ├── widgets.py         ← 커스텀 위젯 (확장)
│   └── styles.py          ← 다크 테마 스타일시트
├── i18n/
│   └── translations.py   ← NEW: 한/영 번역 데이터
└── resources/
    └── logos/             ← NEW: 카메라 로고 에셋
```

### macOS 지원
- `ssc_macos.spec` 전용 빌드 스펙 추가
- GitHub Actions `build-macos.yml` 워크플로우 자동 빌드 & Release 지원
