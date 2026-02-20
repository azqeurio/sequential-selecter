# 빌드 가이드 / Build Guide

## 한국어

### 사전 요구사항
- Python 3.8 이상
- 프로젝트 의존성 설치

### 빌드 방법

1. **PyInstaller 설치**
   ```powershell
   pip install -r requirements.txt
   ```

2. **실행 파일 빌드**
   ```powershell
   pyinstaller ssc.spec
   ```

3. **빌드 결과**
   - 빌드가 완료되면 `dist/SequentialSelector.exe` 파일이 생성됩니다
   - 파일 크기: 약 100-200MB (모든 의존성 포함)

### 실행

빌드된 실행 파일을 실행하려면:
```powershell
.\dist\SequentialSelector.exe
```

또는 Windows 탐색기에서 `dist/SequentialSelector.exe`를 더블클릭합니다.

### 배포

- `dist/SequentialSelector.exe` 파일만 다른 컴퓨터로 복사하여 사용할 수 있습니다
- Python이나 다른 의존성을 설치할 필요가 없습니다
- Windows 10/11에서 동작합니다

### 문제 해결

#### Windows Defender 경고
첫 실행 시 Windows Defender나 백신 프로그램에서 경고가 나타날 수 있습니다. 이는 PyInstaller로 생성된 실행 파일의 일반적인 현상입니다.

**해결 방법:**
1. "추가 정보" 클릭
2. "실행" 버튼 클릭

#### 실행 파일이 느리게 시작됨
단일 실행 파일은 시작 시 임시 디렉토리에 압축을 풀기 때문에 첫 실행이 느릴 수 있습니다 (약 5-10초). 이는 정상적인 동작입니다.

#### 빌드 실패
- 모든 의존성이 설치되었는지 확인: `pip install -r requirements.txt`
- Python 버전 확인: `python --version` (3.8 이상 필요)
- PyInstaller 캐시 삭제 후 재시도:
  ```powershell
  Remove-Item -Recurse -Force build, dist
  pyinstaller ssc.spec
  ```

---

## English

### Prerequisites
- Python 3.8 or higher
- Project dependencies installed

### Build Instructions

1. **Install PyInstaller**
   ```powershell
   pip install -r requirements.txt
   ```

2. **Build the executable**
   ```powershell
   pyinstaller ssc.spec
   ```

3. **Build output**
   - After build completes, `dist/SequentialSelector.exe` will be created
   - File size: approximately 100-200MB (includes all dependencies)

### Running

To run the built executable:
```powershell
.\dist\SequentialSelector.exe
```

Or double-click `dist/SequentialSelector.exe` in Windows Explorer.

### Distribution

- Copy only the `dist/SequentialSelector.exe` file to other computers
- No need to install Python or other dependencies
- Works on Windows 10/11

### Troubleshooting

#### Windows Defender Warning
On first run, Windows Defender or antivirus software may display a warning. This is normal for PyInstaller-generated executables.

**Solution:**
1. Click "More info"
2. Click "Run anyway"

#### Slow startup
Single-file executables extract to a temporary directory on startup, which can take 5-10 seconds on first run. This is normal behavior.

#### Build Failures
- Verify all dependencies are installed: `pip install -r requirements.txt`
- Check Python version: `python --version` (3.8+ required)
- Clear PyInstaller cache and retry:
  ```powershell
  Remove-Item -Recurse -Force build, dist
  pyinstaller ssc.spec
  ```
