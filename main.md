# MoodTender — 감정 바텐더

사용자가 텍스트로 감정을 입력하면, AI 바텐더가 공감 응답을 생성하고 아바타 영상으로 보여주는 프로젝트입니다.

```
텍스트 입력 → OpenAI(LLM) → Edge TTS → MuseTalk 립싱크 영상
                    ↑ 선택
           사진 업로드 → LivePortrait → 커스텀 아바타 생성
```

---

## 앱 구성

| 파일 | 포트 | 설명 |
|------|------|------|
| `backend/main.py` | 7862 | 메인 FastAPI 앱. OpenAI 응답 + LivePortrait + MuseTalk |
| `backend/MuseTalk/persona_app.py` | 7861 | 간단 버전. 텍스트 → TTS → MuseTalk |

---

## 사전 요구사항

- NVIDIA GPU (VRAM 8GB 이상 권장)
- Python 3.10 또는 3.11
- CUDA 11.8 이상
- [FFmpeg](https://ffmpeg.org/download.html) (bin 경로 필요)
- OpenAI API 키 (`backend/services/openai_llm.py` 전용)

---

## 설치

### 1. LivePortrait 가상환경

```powershell
cd backend\LivePortrait
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

모델 다운로드 — [KwaiVGI/LivePortrait HuggingFace](https://huggingface.co/KwaiVGI/LivePortrait) 에서 받아 아래 구조로 배치:

```
backend/LivePortrait/pretrained_weights/
├── insightface/models/buffalo_l/
└── liveportrait/
    ├── base_models/
    └── retargeting_models/
```

### 2. MuseTalk 가상환경

```powershell
cd backend\MuseTalk
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

모델 다운로드 — `download_weights.bat` 실행 또는 수동으로 아래 구조로 배치:

```
backend/MuseTalk/models/
├── musetalkV15/
│   ├── unet.pth
│   └── musetalk.json
├── whisper/
├── dwpose/
├── sd-vae/
└── face-parse-bisent/
```

### 3. config.py 생성

```powershell
cd backend\MuseTalk
copy config_example.py config.py
```

`config.py`를 열어 실제 경로로 수정:

```python
FFMPEG_PATH = r"C:\...\ffmpeg\bin"
LP_DIR      = r"C:\...\MoodTender\backend\LivePortrait"
LP_PYTHON   = r"C:\...\MoodTender\backend\LivePortrait\venv\Scripts\python.exe"
```

### 4. 환경변수 설정

```powershell
$env:OPENAI_API_KEY = "sk-..."

# 선택 사항. 기본값은 gpt-4.1-mini
$env:OPENAI_MODEL = "gpt-4.1-mini"
```

---

## 실행

```powershell
cd backend
python main.py
```

브라우저에서 `http://127.0.0.1:7862` 접속.

간단 버전만 실행하려면:

```powershell
cd backend\MuseTalk
.\venv\Scripts\Activate.ps1
python persona_app.py
```

브라우저에서 `http://127.0.0.1:7861` 접속.

---

## 데이터 구성

```
backend/MuseTalk/data/
├── audio/        # TTS 테스트용 wav 파일
└── video/        # 아바타 소스 영상 (bartender.mp4 등)
```

소스 영상은 `.gitignore`로 제외되어 있습니다. 필요 시 직접 준비 후 배치하세요.
