#!/usr/bin/env bash
set -euo pipefail

echo "======================================================="
echo "  Building Sequential Selector macOS App Bundle"
echo "======================================================="
echo

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[ERROR] ${PYTHON_BIN} not found."
  exit 1
fi

echo "[INFO] Upgrading pip and installing dependencies..."
"${PYTHON_BIN}" -m pip install --upgrade pip
"${PYTHON_BIN}" -m pip install -r requirements.txt
"${PYTHON_BIN}" -m pip install --upgrade pyinstaller

if command -v brew >/dev/null 2>&1; then
  echo "[INFO] Ensuring system libraries for RAW/HEIF are present..."
  brew install libraw libheif || true
fi

rm -rf build dist SequentialSelector-macOS.zip

echo "[INFO] Running PyInstaller with ssc_macos.spec..."
"${PYTHON_BIN}" -m PyInstaller --noconfirm --clean ssc_macos.spec

if [[ ! -d "dist/SequentialSelector.app" ]]; then
  echo "[ERROR] Build output not found: dist/SequentialSelector.app"
  exit 1
fi

echo "[INFO] Validating .app bundle size limit (2.0 GiB)..."
"${PYTHON_BIN}" scripts/check_artifact_size.py "dist/SequentialSelector.app" --max-gib 2.0

echo "[INFO] Compressing .app to zip..."
(
  cd dist
  ditto -c -k --sequesterRsrc --keepParent "SequentialSelector.app" "../SequentialSelector-macOS.zip"
)

echo "[INFO] Validating zip size limit (2.0 GiB)..."
"${PYTHON_BIN}" scripts/check_artifact_size.py "SequentialSelector-macOS.zip" --max-gib 2.0

echo
echo "======================================================="
echo "  BUILD SUCCESSFUL"
echo "======================================================="
echo "Outputs:"
echo " - dist/SequentialSelector.app"
echo " - SequentialSelector-macOS.zip"
