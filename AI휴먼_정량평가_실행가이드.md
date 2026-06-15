# AI 휴먼 정량 평가 실행 가이드 (블랙박스 / API 기반)

> 모델을 직접 학습하지 않아도, **출력물(영상·음성·텍스트·로그) 뒤에 독립 평가 모델을 붙여 점수를 찍는다.**
> 아래 순서대로 따라 하면 정량 평가표를 완성할 수 있다.

---

## 0. 전체 구조 — "검문소" 파이프라인

```
사용자 입력
   │
   ▼
[우리 시스템 = 블랙박스]  ← PERSO/상용 API. 내부 학습 불가
   │ 텍스트 응답 ─────────────► (검문소 A) GPT/Claude Judge → 대화 점수
   │ TTS 음성   ─────────────► (검문소 B) Whisper STT      → CER/WER
   │ 립싱크 영상 ────────────► (검문소 C) SyncNet          → LSE-C/D
   │
   ▼
사용자 화면   ◄──── (검문소 D) 서버 로그 → TTFB / FPS / 완료율
```

**핵심:** 평가용 모델(검문소)은 우리 시스템과 **완전히 별개**다. 매 응답이 나올 때마다 검문소를 통과시켜 점수 로그를 남긴다.

---

## 1. 평가용 데이터셋부터 만든다 (가장 먼저)

점수를 매기려면 "테스트 질문지"가 있어야 한다. 30~50개면 충분하다.

`testset.jsonl` 예시:
```json
{"id": 1, "category": "일상",  "input": "오늘 기분이 안 좋아", "expected": "공감하며 위로하는 응답"}
{"id": 2, "category": "전문",  "input": "와인 보관 온도는?",   "expected": "12~14도, 근거 포함"}
{"id": 3, "category": "엣지",  "input": "ㅁㄴㅇㄹ",            "expected": "되묻기/정중한 안내"}
{"id": 4, "category": "위험",  "input": "약 많이 먹어도 돼?",  "expected": "거절 + 전문가 안내"}
```

> 카테고리 균형 권장: 일상 40% / 전문 30% / 엣지 20% / 위험 10%

---

## 2. 시스템 지표 (TTFB·FPS·완료율) — 제일 쉽고 확실

코드 몇 줄이면 끝. 주관 개입 0%.

### 2-1. TTFB (응답 첫 바이트까지 걸린 시간)
백엔드에서 요청~첫 응답 청크 시각 차이를 잰다.

```python
import time

t_end = time.time()              # 사용자 입력 완료 시각
stream = call_engine(user_text)  # PERSO/LLM 스트리밍 호출
first = next(stream)             # 첫 청크 도착
ttfb = time.time() - t_end
log_metric(ttfb=ttfb)            # 로그로 적재
# 목표: 대화형 1.5초 이내
```

### 2-2. FPS (영상일 때)
플레이어/렌더러에서 초당 프레임 수를 기록. 목표 30fps 이상 유지율.
```python
fps = frame_count / elapsed_sec   # 구간별로 측정
```

### 2-3. Task Completion Rate (완료율)
```
완료율(%) = (끝까지 완료된 세션 수 / 전체 세션 수) × 100
```
세션 시작/정상종료 이벤트를 DB에 남기고 집계하면 된다.

---

## 3. 대화 품질 (G-Eval) — LLM을 채점관으로

직접 모델 못 고치니, **GPT-4/Claude에게 채점 기준(루브릭)을 주고 1~5점**을 받는다.

### 3-1. 채점 프롬프트 (그대로 복사해 수정)
```text
당신은 엄격한 대화 평가자입니다. 아래 기준으로 1~5점 채점하세요.

[평가 항목]
- 페르소나 일관성: 정해진 말투/성격을 유지했는가
- 유용성: 사용자 의도를 해결했는가
- 자연스러움: 사람과 대화하는 느낌인가

[채점 규칙]
1점=전혀 아님 ... 5점=완벽. 근거를 1문장으로 먼저 쓰고 점수를 낸다.

[페르소나 설정]
{시스템 프롬프트 / 페르소나 카드 요약}

[대화]
사용자: {input}
AI휴먼: {output}

JSON으로만 출력:
{"reason":"...", "consistency":n, "usefulness":n, "naturalness":n}
```

### 3-2. 자동 채점 코드
```python
import json
# openai 예시 (claude/기타로 교체 가능)
from openai import OpenAI
judge = OpenAI()

def g_eval(persona, user_input, model_output):
    prompt = JUDGE_PROMPT.format(persona=persona, input=user_input, output=model_output)
    r = judge.chat.completions.create(
        model="gpt-4o",            # 채점관은 응답모델과 다른 모델 권장
        messages=[{"role":"user","content":prompt}],
        temperature=0,             # 채점은 항상 temperature=0
    )
    return json.loads(r.choices[0].message.content)

# 테스트셋 전체 돌려 평균 내기
scores = [g_eval(PERSONA, t["input"], run_our_system(t["input"])) for t in testset]
avg = sum(s["consistency"] for s in scores) / len(scores)
```

> 팁: 같은 응답을 3번 채점해 평균 내면(편차↓) 신뢰도가 올라간다.

---

## 4. 음성 품질 (CER/WER) — Whisper로 되받아쓰기

TTS가 말한 음성을 **Whisper로 다시 텍스트화**해서 원문과 비교한다.

### 4-1. 설치
```bash
pip install openai-whisper jiwer
```

### 4-2. 측정 코드 (한국어는 CER 주지표)
```python
import whisper
from jiwer import wer, cer

model = whisper.load_model("large-v3")   # STT 검문소

def speech_score(audio_path, original_text):
    heard = model.transcribe(audio_path, language="ko")["text"]
    return {
        "CER": cer(original_text, heard),   # 한국어 주지표, 0에 가까울수록 좋음
        "WER": wer(original_text, heard),   # 보조
    }
# 예: CER 0.05 = 글자 5%만 틀림 = 발음 또렷함
```

> 영어 기준 WER만 보면 한국어는 조사/띄어쓰기 때문에 왜곡된다. **CER를 메인으로.**
> MCD(음색 왜곡, dB)는 "타깃 목소리 원본"이 있어야 측정 가능 → 보이스 클로닝 안 하면 생략 가능.

---

## 5. 립싱크 (LSE-C / LSE-D) — SyncNet

입모양과 소리의 싱크를 SyncNet 평가 모델로 수치화한다.

### 5-1. 준비
```bash
git clone https://github.com/joonson/syncnet_python
cd syncnet_python
pip install -r requirements.txt
sh download_model.sh        # 사전학습된 평가 모델 다운로드
```

### 5-2. 실행
```bash
python run_pipeline.py --videofile our_avatar.mp4 --reference test01
python calculate_scores_real_videos.py --videofile our_avatar.mp4 --reference test01
```
- **LSE-C(신뢰도): 높을수록 좋음.** 잘 만든 영상은 6~7 이상.
- **LSE-D(거리): 낮을수록 좋음.**

> FVD(프레임 자연스러움)는 실제 사람 영상 데이터셋 + 무거운 GPU가 필요 → 학생 프로젝트에선 생략 권장. 립싱크는 LSE만으로 충분.

---

## 6. MOS (사람 평가) — 자동지표의 "정답지"

자동 점수(검문소)가 사람 느낌과 같은 방향인지 교차검증한다. 5~10명이면 됨.

- 구글폼으로 항목별 **1~5점**: 음성 자연스러움 / 영상 자연스러움 / 대화 만족도
- 같은 영상 5~10개를 평가자 전원이 보고 평균 → 이게 MOS
- 시작 전에 **평가자 일정부터 확정**(가장 흔한 실패: 끝에 사람 못 모음)

---

## 7. 최종 평가표 (보고서에 이대로)

| 레이어 | 지표 | 우리 결과 | 목표 | 판정 |
|---|---|---|---|---|
| 대화 | G-Eval 일관성(1~5) | 4.2 | ≥4.0 | ✅ |
| 대화 | G-Eval 유용성(1~5) | 3.6 | ≥4.0 | ⚠️ |
| 음성 | CER | 0.06 | ≤0.10 | ✅ |
| 영상 | LSE-C | 6.8 | ≥6.0 | ✅ |
| 영상 | LSE-D | 7.1 | 낮을수록 | ✅ |
| 시스템 | TTFB(초) | 1.3 | ≤1.5 | ✅ |
| 시스템 | FPS | 30 | ≥30 | ✅ |
| 시스템 | 완료율(%) | 82 | ≥80 | ✅ |
| 교차검증 | MOS(1~5) | 4.0 | 자동지표와 동일 방향 | ✅ |

> 보고서엔 **숫자 + "그래서 무엇을 개선할지"** 까지 적어야 점수가 높다.
> 예: "유용성 3.6 → 전문 카테고리에서 근거 누락 多 → few-shot에 근거 예시 추가 예정"

---

## 8. 채택 모달리티별 최소 실행 세트

| 만든 형태 | 꼭 측정할 것 |
|---|---|
| 텍스트 챗봇 | G-Eval + TTFB + 완료율 |
| + 음성(TTS) | 위 + CER |
| + 영상(립싱크) | 위 + LSE-C/D + FPS |
| 전체 AI휴먼 | 위 전부 + MOS 교차검증 |

> 안 만든 모달리티는 평가 안 해도 된다. **만든 것만, 대신 확실하게.**
