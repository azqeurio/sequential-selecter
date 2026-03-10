# Build Guide

For full release steps, see `DEPLOYMENT.md`.

## Prerequisites

- Python 3.11 (recommended)
- macOS builds: Homebrew `libraw` and `libheif`

Install Python dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --upgrade pyinstaller
```

## Windows build

Recommended:

```bat
build_exe.bat
```

Manual:

```bash
python -m PyInstaller --noconfirm --clean ssc.spec
python scripts/check_artifact_size.py dist/SequentialSelector.exe --max-gib 2.0
```

## macOS build

Recommended:

```bash
./build_macos.sh
```

Manual:

```bash
python -m PyInstaller --noconfirm --clean ssc_macos.spec
python scripts/check_artifact_size.py dist/SequentialSelector.app --max-gib 2.0
```

## Spec files

- `ssc.spec`: Windows release spec (primary)
- `ssc_macos.spec`: macOS release spec (primary)
- `SequentialSelector.spec`: compatibility wrapper that delegates to `ssc.spec`

## Artifact size budget

Target: under **2.0 GiB** per platform artifact.

Use:

```bash
python scripts/check_artifact_size.py <artifact-path> --max-gib 2.0
```
