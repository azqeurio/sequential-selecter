# Deployment Guide (Windows + macOS)

This project now has a single release pipeline that builds both platforms and enforces a 2.0 GiB artifact limit.

## 1) Local build (Windows)

```bat
build_exe.bat
```

Outputs:
- `dist/SequentialSelector.exe`

The script:
- installs `requirements.txt`
- builds with `ssc.spec`
- fails if the final EXE exceeds 2.0 GiB

## 2) Local build (macOS)

```bash
chmod +x build_macos.sh
./build_macos.sh
```

Outputs:
- `dist/SequentialSelector.app`
- `SequentialSelector-macOS.zip`

The script:
- installs system deps (`libraw`, `libheif`) when Homebrew is available
- installs `requirements.txt`
- builds with `ssc_macos.spec`
- fails if the `.app` or `.zip` exceeds 2.0 GiB

## 3) CI build and release

Workflow file:
- `.github/workflows/build-release.yml`

Trigger:
- git tags that start with `v` (example: `v1.4.0`)
- manual run via `workflow_dispatch`

Pipeline behavior:
1. Builds Windows zip artifact
2. Builds macOS zip artifact
3. Validates both artifact sizes (`<= 2.0 GiB`)
4. Publishes both files to one GitHub Release for tagged builds

## 4) Notes on AI denoise package size

`torch`/`torchvision`/`spandrel` are excluded from frozen bundles by design to keep releases small.
They are installed at runtime through the app's AI setup flow.
