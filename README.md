# 🍸 MoodTender

건강 데이터와 대화 기억을 바탕으로 오늘의 감정을 읽고, 마음에 어울리는 칵테일과 감정 영수증을 건네는 AI 바텐더 서비스

Status: Prototype  
Period: 2026.06  
Core: AI Chat · RAG · Health Data · Emotion Receipt · Android Sync

---

## 📌 이게 뭔가요?

MoodTender는 사용자가 오늘의 상태를 평소처럼 말하면, AI 바텐더가 감정을 분류하고 과거 대화·장기 기억·건강 데이터·전문 지식을 함께 참고해 짧고 자연스러운 답변을 생성하는 서비스입니다.

대화가 충분히 쌓이면 현재 감정에 어울리는 칵테일을 추천하고, 대화 종료 후에는 하루의 감정을 감정 영수증으로 남깁니다.

> “오늘은 마음이 조금 무거워 보이네요. 오래 버티느라 지친 날에는, 스모키 위스키 사워 한 잔이 어울릴 것 같아요.”

| 구분 | 우리가 하는 것 | 우리가 안 하는 것 |
|---|---|---|
| 대화 | 감정 공감, 기억 기반 개인화 답변 | 전문 심리치료 대체 |
| 건강 데이터 | 수면·걸음 수·스크린 타임을 감정 맥락으로 반영 | 의료 진단 또는 질병 판단 |
| 기억 | 중요한 대화만 장기 기억으로 저장 | 모든 사적인 발화 무분별 저장 |
| 칵테일 | 감정 분위기에 맞는 상징적 칵테일 추천 | 실제 음주 권유 또는 제조 서비스 |
| 감정 영수증 | 하루 감정 요약과 회고 기록 | 임상 평가 보고서 |

---

## ✨ 핵심 기능

| # | 기능 | 설명 | 상태 |
|---:|---|---|:---:|
| ① | AI 바텐더 채팅 | 사용자 발화에 공감하고 자연스럽게 응답 | ✅ |
| ② | 2단계 감정 분류 | 주 감정 분류 후 3턴째 세부 감정 분류 | ✅ |
| ③ | RAG 개인화 | 기억, 과거 대화, 건강 데이터, 전문 지식 조회 | ✅ |
| ④ | 칵테일 추천 | 3번째 대화 이후 세부 감정 기반 칵테일 추천 | ✅ |
| ⑤ | 감정 영수증 | 대화 종료 후 감정·이유·칵테일·위로 요약 저장 | ✅ |
| ⑥ | 건강 데이터 연동 | Android에서 수면, 걸음 수, 스크린 타임 수집 | ✅ |
| ⑦ | Activity Knowledge | 감정별 행동 근거 지식 베이스 구축 | ✅ |
| ⑧ | 대시보드 분석 | 건강 데이터 변화량 기반 LLM 리포트 생성 | ✅ |
| ⑨ | 모바일 페어링 | PIN 기반 Android 기기 연동 | ✅ |
| ⑩ | 멀티모달 기반 | STT/TTS, MuseTalk, 연동 구조 | ✅ |

---

## 🧠 감정 분류 방식

감정 분류는 두 단계로 진행됩니다.

### 1단계: `classify_chain` - 매 턴 실행

현재 발화만 보고 7가지 주 감정 중 하나를 선택합니다.

- 기쁨
- 우울
- 불안
- 분노
- 지침
- 외로움
- 평온

이 결과는 `emotion_dictionary`, `activity_knowledge` 조회와 기억 저장 시 `main_category`로 사용됩니다.

### 2단계: `sub_classify_chain` - 3번째 턴, 칵테일 추천 시에만 실행

`emotion_dictionary`에서 해당 주 감정의 `sub_category` 목록을 가져오고, 현재 발화와 가장 가까운 세부 감정을 고릅니다. 이후 해당 세부 감정의 `cocktail_direction`, `cocktail_color`를 바탕으로 칵테일을 결정합니다.

```text
발화 → classify_chain → 지침
              ↓
emotion_dictionary WHERE main_category = '지침'
              ↓
[무기력감, 번아웃, 신체피로, ...]
              ↓ 3번째 턴
sub_classify_chain → 번아웃
              ↓
cocktail_chain → "스모키 위스키 사워"
```

---

## 🧱 기술 스택

| 영역 | 기술 |
|---|---|
| Backend | FastAPI, SQLAlchemy AsyncSession, Python 3.10 |
| Database | PostgreSQL, Supabase, pgvector |
| AI / LLM | LangChain, OpenAI GPT-4.1, GPT-4.1-mini |
| Embedding | text-embedding-3-small |
| RAG | user_memories, chat_messages, emotion_dictionary, activity_knowledge |
| Android | Kotlin, Jetpack Compose, WorkManager, Health Connect |
| Frontend | HTML, CSS, JavaScript |
| Auth | JWT, PIN Pairing |
| Multimodal | Whisper, MuseTalk, LivePortrait |
| Runtime | Anaconda, Windows, PowerShell |

---

## 🧩 RAG 구성

| 지식 소스 | 테이블/모듈 | 역할 |
|---|---|---|
| 장기 기억 | `user_memories` | 사용자의 반복 고민, 성향, 중요한 사건 저장 |
| 현재 세션 | `chat_messages` | 같은 대화 흐름 안의 최근 문맥 유지 |
| 과거 대화 | `chat_messages` + vector search | 현재 발화와 관련 있는 이전 대화 검색 |
| 건강 데이터 | `health_metrics` | 수면, 걸음 수, 스크린 타임 기반 컨디션 반영 |
| 감정 사전 | `emotion_dictionary` | 주 감정, 세부 감정, 칵테일 방향/색상 제공 |
| 전문 지식 | `activity_knowledge` | 감정별 행동 근거와 회복 팁 제공 |

---

## 📱 Android 연동

| 기능 | 설명 |
|---|---|
| 로그인 | 사용자 계정 인증 및 JWT 저장 |
| PIN 페어링 | 모바일 기기와 웹/서버 계정 연동 |
| 채팅 | AI 바텐더와 대화, LLM API 호출 |
| Health Connect | 걸음 수, 수면 시간 조회 |
| 앱 사용량 | 카카오톡, 유튜브 등 앱 사용 시간 집계 |
| WorkManager | 백그라운드 주기적 건강 데이터 전송 |
| 건강 화면 | 날짜별 건강 데이터 조회 |

---

## 🗄️ DB 테이블

| 테이블 | 역할 |
|---|---|
| `users` | 사용자 계정, 로그인 정보, 기기 연동 상태 |
| `chat_messages` | 사용자/AI 대화, session_id, embedding 저장 |
| `user_memories` | 장기 기억, 중요도, 기억 유형 저장 |
| `health_metrics` | 날짜별 걸음 수, 수면, 스크린 타임, 앱 사용 기록 |
| `emotion_dictionary` | 주 감정, 세부 감정, 칵테일 방향, 색상 |
| `activity_knowledge` | 감정별 전문 지식과 행동 근거 |
| `emotion_receipts` | 감정 영수증 기록 |

---

## 📁 폴더 구조

```text
MoodTender/
├── backend/                         # FastAPI 백엔드
│   ├── main.py                      # 앱 진입점, 라우터 등록
│   ├── database.py                  # SQLAlchemy AsyncSession 설정
│   ├── models/
│   │   ├── domain.py                # SQLAlchemy ORM 모델
│   │   └── schemas.py               # Pydantic 요청/응답 스키마
│   ├── routers/
│   │   ├── auth.py                  # 로그인/JWT
│   │   ├── pairing.py               # PIN 기기 연동
│   │   ├── llm.py                   # AI 바텐더 응답/영수증 API
│   │   ├── health.py                # 건강 데이터 API
│   │   ├── emotion_receipt.py       # 감정 영수증 조회/선택
│   │   ├── generation.py            # 영상 생성 API
│   │   └── stt.py                   # 음성 인식 API
│   └── services/
│       ├── rag_chain.py             # RAG/LLM 핵심 로직
│       ├── db_client.py             # DB 쿼리 함수
│       ├── analytics_service.py     # 건강 데이터 분석
│       ├── init_knowledge.py        # activity_knowledge seed
│       ├── anonymizer.py            # 비식별화 처리
│       ├── ml_manager.py            # 모델 로딩 관리
│       └── video_audio.py           # 영상/음성 처리
├── Android/                         # Android 앱
├── frontend/                        # 웹 화면
├── run.ps1                          # 서버 실행 스크립트
└── README.md                        # 프로젝트 문서
```

---

## 🚀 빠른 시작

처음 합류했다면 아래 순서대로 확인하세요.

1. `README.md` - 프로젝트 전체 구조
2. `backend/main.py` - FastAPI 라우터 연결
3. `backend/services/rag_chain.py` - AI/RAG 핵심 로직
4. `backend/services/db_client.py` - DB 조회/저장 로직
5. `Android/app/src/main/java/com/example/moodtender` - Android 앱 코드

### 백엔드 실행

```powershell
python MoodTender/backend\main.py
```

또는:

```powershell
.\run.ps1
```

기본 주소:

```text
http://127.0.0.1:7862
```

### Android 실행

Android Studio에서 `.\MoodTender\Android` 폴더를 열고 실제 기기 또는 에뮬레이터에서 실행합니다.

---

## 🎬 시연 흐름

1. 사용자가 로그인합니다.
2. PIN으로 Android 기기를 연동합니다.
3. Android 앱이 건강 데이터를 서버에 전송합니다.
4. 사용자가 AI 바텐더와 대화를 시작합니다.
5. 1~2턴은 공감 중심 답변을 제공합니다.
6. 3번째 턴에서 세부 감정을 분류하고 칵테일을 추천합니다.
7. 대화 종료 후 감정 영수증을 생성합니다.
8. 대시보드에서 건강 데이터 기반 리포트를 확인합니다.


---

## 🧭 통합 실행 방법

발표나 시연 전에는 아래 순서대로 실행하면 됩니다.

### 1. 실행 전 준비

필수 준비물:

- Python 3.10 또는 Anaconda `py310` 환경
- Android Studio
- PostgreSQL/Supabase DB
- OpenAI API Key
- 실제 Android 기기 또는 에뮬레이터


### 2. 환경 변수 확인

프로젝트 루트에 `.env` 파일이 있어야 합니다.

```text
C:\jnr_python\MoodTender\.env
```

필수 값:

```env
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
SECRET_KEY=your-secret-key
```

주의:

- `.env`는 Git에 올리지 않습니다.
- 발표 화면에 API Key나 DB 비밀번호가 노출되지 않게 합니다.

### 3. 백엔드 서버 실행

```powershell
python backend\main.py
```

또는 실행 스크립트를 사용합니다.

```powershell
.\run.ps1
```

이미 서버가 켜져 있으면 재시작합니다.

```powershell
.\run.ps1 -Restart
```

기본 접속 주소:

```text
http://127.0.0.1:7862
```

서버 확인:

```text
http://127.0.0.1:7862/api/status
```

### 4. Android BASE_URL 설정

Android 앱은 `Android/local.properties`의 `BASE_URL`을 보고 서버에 접속합니다.

파일 위치:

```text
MoodTender\Android\local.properties
```

에뮬레이터에서 실행할 때:

```properties
BASE_URL=http://127.0.0.1:7862/
```

실제 휴대폰에서 실행할 때:

```properties
BASE_URL=http://PC_IP:7862/
```

PC IP 확인:

```powershell
ipconfig
```

주의:

- 실제 휴대폰에서는 `localhost`나 `127.0.0.1`을 쓰면 안 됩니다.
- 휴대폰과 노트북이 같은 Wi-Fi에 있어야 합니다.
- 끝에 `/`를 붙입니다.

### 5. Android 앱 실행

Android Studio에서 아래 폴더를 엽니다.

```text
MoodTender\Android
```

실행 순서:

1. Gradle Sync 완료 대기
2. 실제 기기 또는 에뮬레이터 선택
3. Run 실행
4. 앱 로그인
5. PIN 페어링
6. 채팅 화면 진입

명령어로 빌드할 경우:

```powershell
cd MoodTender\Android
.\gradlew assembleDebug
```

### 6. 발표용 시연 순서

1. 백엔드 서버 실행
2. 웹 화면 접속
3. Android 앱 실행
4. 로그인
5. PIN 페어링 확인
6. 건강 데이터 전송 확인
7. AI 바텐더와 3턴 대화
8. 3번째 턴에서 칵테일 추천 확인
9. 감정 영수증 생성/조회
10. 대시보드 건강 분석 리포트 확인

### 7. 발표용 테스트 문장

```text
요즘 과제 때문에 잠을 제대로 못 잤어.
계속 해야 하는데 몸이 너무 무거워.
끝나도 마음이 편할지 모르겠어.
```

기대 흐름:

- 1번째 턴: 공감 중심 답변
- 2번째 턴: 상황을 더 들어주는 답변
- 3번째 턴: 세부 감정 분류 후 칵테일 추천

확인할 서버 로그:

```text
[RAG]
[classify]
[cocktail]
[reply]
[memory]
```

### 8. 자주 나는 문제

#### Android에서 서버 접속 실패

원인:

- 실제 기기에서 `localhost` 사용
- PC와 휴대폰이 다른 Wi-Fi
- Windows 방화벽 차단
- 서버가 꺼져 있음

해결:

```properties
BASE_URL=http://PC_IP:7862/
```

#### LLM 답변 실패

확인할 것:

- `OPENAI_API_KEY`가 `.env`에 있는지
- DB 연결이 되는지
- 서버 터미널에 500 에러가 찍히는지
- `backend/services/rag_chain.py`에서 RAG 로그가 찍히는지


#### Android 수정했는데 반영 안 됨

해결:

- 앱 삭제 후 재설치
- Android Studio `Clean Project`
- Gradle Sync 재실행
- `local.properties`의 `BASE_URL` 재확인


## 📜 안내

MoodTender는 교육 과정 팀 프로젝트입니다. 건강 데이터와 감정 분석은 사용자 이해와 회고를 돕기 위한 기능이며, 의료적 진단이나 전문 심리치료를 대체하지 않습니다.