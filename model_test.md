# TensorRT 최적화 작업 기록

MuseTalk 아바타 생성 파이프라인에 TensorRT(TRT) 8.6.1 가속을 적용하는 과정에서 시도한 것들과 결과를 기록합니다.

---

## 환경

- GPU: NVIDIA RTX 4060 (8GB VRAM, SM89 Ada Lovelace)
- TensorRT: 8.6.1.6
- PyTorch: 2.x (CUDA 11.8)
- cuDNN: 8.7.0 (TRT 링크 버전 8.9.0과 미스매치 — 빌드 시 경고 발생하지만 동작)

---

## 목표

| 단계 | 내용 |
|------|------|
| UNet 추론 | 배치 16 기준 가능한 빠르게 |
| VAE 디코딩 | 16프레임 기준 가능한 빠르게 |
| 품질 | 시각적 왜곡(픽셀 깨짐, 색상 노이즈) 없어야 함 |

---

## 해결된 문제들

### 1. TRT 추론 30~100초 → ~200ms

**원인**  
PyTorch UNet 모델이 GPU에 남아있는 상태에서 TRT가 추론 중 VRAM 부족 → 스왑 발생

**해결**  
TRT UNet 엔진 로드 후 PyTorch 모델을 CPU로 내림
```python
# ml_manager.py
if trt_unet is not None:
    unet.model = unet.model.cpu()
    torch.cuda.empty_cache()
```

---

### 2. 첫 번째 추론 3~4초 콜드스타트

**원인**  
서버 시작 후 첫 TRT 호출 시 CUDA 커널 JIT 컴파일

**해결**  
TRT 엔진 로드 직후 더미 입력으로 웜업 1회 실행
```python
# ml_manager.py
with torch.inference_mode():
    _d = torch.zeros(16, 8, 32, 32, dtype=torch.float16, device=device)
    _t = torch.tensor([0], device=device)
    _a = torch.zeros(16, 5, 384, dtype=torch.float16, device=device)
    trt_unet(_d, _t, encoder_hidden_states=_a)
torch.cuda.empty_cache()
```

---

### 3. PyTorch VAE 디코딩 후 TRT UNet 다시 느려짐 (600ms → 정상 200ms)

**원인**  
PyTorch VAE가 VRAM 캐시 ~2.9GB를 점유한 채로 반환하지 않음 → TRT 다음 추론에 공간 부족

**해결**  
VAE 디코딩 직후 캐시 반환
```python
# stream_inference.py
torch.cuda.empty_cache()
```

---

### 4. TRT VAE → 포기, PyTorch 프레임 보간으로 대체

**시도한 것들**
- Dynamic shape (min=1, opt=8, max=16): 4~5초로 여전히 느림
- FP16 GPU ONNX 내보내기: 12~18초 + GroupNorm 정밀도 문제로 영상 왜곡 발생
- FP32 CPU ONNX + 정적 shape (batch=16): 빌드는 성공, 추론 여전히 느림

**결론**  
TRT VAE는 RTX 4060에서 PyTorch 대비 이점 없음. 비활성화.

**대안**  
짝수 인덱스 프레임만 VAE 디코딩 후 홀수 프레임은 선형 보간 → 약 400ms (2배 속도 향상)
```python
# stream_inference.py
key_latents = latents[::2]
key_decoded = vae.vae.decode(key_latents.to(dtype)).sample
interp = (key_decoded[:-1] + key_decoded[1:]) / 2
```

---

### 5. 목소리 드롭다운 비어있음

**원인**  
프론트엔드에서 `/api/voices` 요청 시 인증 토큰 미전송

**해결**  
토큰 포함 + 실패 시 하드코딩 폴백 추가 (`frontend/js/app.js`)

---

## NaN 문제 — 영상 왜곡의 근본 원인

TRT UNet 추론 출력에 NaN이 포함되면 VAE 디코딩 결과에 색상 깨짐, 픽셀 노이즈가 발생.

### 시도 1 — dtype 불일치 의심
FP32 입력을 FP16 바인딩 엔진에 전달하는 문제로 의심 → dtype 맞춰도 NaN 지속

### 시도 2 — FP32 ONNX 내보내기 (model.float())
```
에러: OutOfMemory (2GB 요청 실패)
에러: Could not find any implementation for ForeignNode[attention/Transpose...]
```
실패 원인
- PyTorch 모델이 VRAM에 남은 채 TRT 빌드 → VRAM 부족
- `FP16 플래그 + FP32 ONNX` 조합: TRT 8.6이 FP32 attention 커널 미지원

### 시도 3 — SDPA 패치에서 softmax만 FP32 캐스트
```python
attn = (q.float() @ k.float().transpose(-2,-1)) * scale  # ONNX에 Cast 노드 삽입
attn = torch.softmax(attn, dim=-1).to(q.dtype)
```
TRT FP16 플래그 빌드 시 Cast 노드를 무시하고 FP16으로 통합 → NaN 지속

### 시도 4 — PREFER_PRECISION_CONSTRAINTS + Softmax FP32 강제
```python
cfg.set_flag(trt.BuilderFlag.PREFER_PRECISION_CONSTRAINTS)
layer.precision = trt.DataType.FLOAT  # Softmax 레이어
```
`PREFER`는 TRT가 선택적으로 무시 가능 → NaN 지속

### 시도 5 — OBEY_PRECISION_CONSTRAINTS + Softmax 32개 FP32
빌드 로그: `FP32 강제: Softmax=32, Normalization=0`  
Softmax 32개 강제 적용 성공, 그러나 **NaN 지속**

→ **확정**: NaN의 원인은 Softmax가 아닌 **LayerNorm**

TRT 빌드 경고 (처음부터 있었음):
```
[W] Detected layernorm nodes in FP16
[W] Running layernorm after self-attention in FP16 may cause overflow
```

LayerNorm은 TRT가 **ForeignNode**(퓨즈드 커널)로 묶어버려 `layer.precision` API 접근 불가.  
`Normalization=0`: `trt.LayerType.NORMALIZATION`으로 검색해도 아무것도 검출되지 않음.

---

## 최종 결론

### FP32 TRT — 빌드 성공, 그러나 속도 미흡

빌드 결과: 1719.7MB, NaN 없음 (`nan=False`, `range=[-6.163, 4.071]` 정상 출력)  
실제 추론 속도: **11~31초/배치** (FP16 TRT 200ms 대비 60~150배 느림)

원인: RTX 4060 FP32 처리량(15 TFLOPS, CUDA 코어) vs FP16(61 TFLOPS, 텐서 코어) — 4배 이상 차이.  
결론: **FP32 TRT는 RTX 4060에서 실사용 불가**.

---

### 최종 채택: PyTorch FP16

FP16/FP32 TRT 모두 실패 후 PyTorch FP16 + Flash Attention으로 복귀.

| 지표 | FP16 TRT | FP32 TRT | **PyTorch FP16 (채택)** |
|------|---------|---------|------------------------|
| UNet/배치 | 200ms | 11~31초 | **300~450ms** |
| VAE/배치 | 400ms | 3~6초 | **500~800ms** |
| 첫 청크 | ~5.6초 | 1299초 | **11.8초** |
| NaN 여부 | ✗ 있음 | ✓ 없음 | **✓ 없음** |
| 영상 왜곡 | ✗ 있음 | ✓ 없음 | **✓ 없음** |

**PyTorch FP16이 채택된 이유:**
- Flash Attention이 수치적으로 안정한 연산 → NaN 없음
- LayerNorm / Softmax 오버플로우 없음
- 300~450ms/배치는 실시간 스트리밍에 충분
- TRT 엔진 빌드 및 관리 불필요

**설정 (`ml_manager.py`):**
```python
trt_unet, trt_vae = _load(device, unet_path="", vae_path="")
```
UNet은 GPU FP16으로 유지, TRT 없이 PyTorch로 직접 추론.

---

## 핵심 교훈

| 항목 | 내용 |
|------|------|
| TRT FP16 플래그 | FP16 플래그 활성화 시 TRT가 LayerNorm을 FP16 ForeignNode로 퓨즈 → overflow |
| ForeignNode | TRT가 여러 op을 하나로 퓨즈한 커널, `layer.precision` API로 접근 불가 |
| OBEY_PRECISION_CONSTRAINTS | 표준 레이어(Softmax 등)에만 효과 있음, ForeignNode에는 무효 |
| VRAM 관리 | TRT 빌드 중에는 PyTorch 모델을 완전히 삭제해야 OOM 방지 |
| `torch.cuda.empty_cache()` | PyTorch 캐시를 반환하지 않으면 TRT 추론 시 VRAM 부족 발생 |
| TRT VAE | RTX 4060 기준 UNet 대비 TRT 이점 미미, 프레임 보간이 더 효율적 |

---

---

## TRT 이후 — 스트리밍 버퍼링 제거 작업

TRT 포기 후 PyTorch FP16 기반에서 실시간 스트리밍 버퍼링을 없애기 위해 진행한 작업.

---

### 문제 1 — WDDM이 GPU 메모리를 회수해 두 번째 요청이 느려짐

**원인**  
Windows WDDM(Windows Display Driver Model)은 GPU가 ~2초 이상 유휴 상태가 되면 VRAM을 OS에 반환.  
TTS 처리 중 GPU가 쉬는 동안 메모리 회수 → 다음 추론 첫 배치에서 재로딩 오버헤드 발생.

**해결**  
NVIDIA 제어판 → 3D 설정 → 전원 관리 모드 → **최대 성능 선호** 설정  
(WDDM의 공격적인 메모리 회수 억제)

---

### 문제 2 — 마지막 배치(소배치) UNet/VAE 3초 이상 느림

**원인**  
배치 크기가 16이 아닌 소배치(B=3 등)가 마지막에 오면 CUDA 알고리즘 탐색(컨볼루션 알고리즘 선택) 오버헤드 발생.  
예: B=3 마지막 배치 3083ms (정상 배치 850ms 대비 3.6배)

**해결**  
서버 시작 시 소배치 크기로도 미리 웜업 실행 → CUDA 커널 캐시에 사전 등록
```python
# ml_manager.py
for b in [4, 8, 12]:
    _w = torch.zeros(b, 5, 384, dtype=weight_dtype, device=device)
    _l = torch.zeros(b, 8, 32, 32, dtype=weight_dtype, device=device)
    _o = unet.model(_l, timesteps, encoder_hidden_states=pe(_w)).sample
    vae.vae.decode(_o[::2].to(vae.vae.dtype))
    torch.cuda.synchronize()
```
결과: B=3 마지막 배치 3083ms → **569ms**

---

### 문제 3 — CUDA 스트림 파이프라인 → 포기

**시도**  
UNet(텐서 코어)과 VAE(CUDA 코어)를 별도 CUDA 스트림에서 동시 실행하면 두 연산이 겹쳐서 처리될 것이라 기대.

**결과**  
두 스트림이 동시에 VRAM을 점유 → WDDM이 메모리 회수 → 109.5초 (정상 9초 대비 12배 느림)

**원인**  
두 스트림이 서로 다른 VRAM 블록을 동시에 보유하면서 메모리 압박 발생 → WDDM이 회수 트리거.  
최대 성능 모드에서도 동시 점유 패턴에서는 회수 발생.

**결론**  
순차 실행(현재 방식)이 유일하게 안정적.

---

### 문제 4 — 재생 시작 전 2~3초 대기 ("버퍼링 중..." 표시)

**원인**  
서버 생성 속도 = 0.75배속 (배치 840ms로 640ms 영상 생성).  
재생 중 버퍼가 드레인되므로 초기에 충분한 버퍼를 쌓아야 중간 멈춤 방지.

**최적화**
1. TTS 직후 불필요한 GPU 웜업 블록 제거 (`generation.py`) → 첫 청크 **0.4~0.5초 단축**
2. `RESUME_THRESHOLD` 4.0초 → **3.0초** 축소 → 재생 시작 ~1초 단축  
   (측정 총 드레인 2.3~2.5초, 마진 0.5~0.7초로 안전)

**결과**  
첫 청크: 11.8초 → **2.1~2.9초**  
재생 시작까지: ~7초 → **~5초**

---

### 문제 5 — 첫 글자("오") 잘림

**원인**  
HTML `<video autoplay>` 속성으로 첫 청크 도착 즉시 자동 재생 시작.  
`monitorBuffer`가 `ahead < 0.3s` 감지 → 즉시 일시정지.  
3초 버퍼 쌓인 후 재개 시 `currentTime`이 이미 첫 음절 이후로 밀려있음.

**해결**  
`index.html`에서 `autoplay` 제거. 재생 시작은 `monitorBuffer`의 `play()` 호출로만 제어.

---

### 문제 6 — 영상 끝부분에서 멈추고 완료가 안 됨

**원인**  
스트리밍이 끝날 무렵 남은 영상이 0.3초 미만 → `monitorBuffer`가 일시정지.  
재개 조건: `ahead >= RESUME_THRESHOLD(3.0초)` → 남은 영상이 3초 이하면 **영원히 재개 불가**.

**해결**  
스트림 완료(`streamDone = true`) 후에는 `ahead > 0` (1프레임이라도 있으면) 즉시 재개.
```javascript
// app.js
} else if (videoEl.paused && playAllowed && ahead > 0) {
  // 스트림 완료 후: 남은 프레임 있으면 즉시 재생
  videoEl.play().catch(() => {});
  statusEl.textContent = '완료!';
}
```
스트림 완료 순간에도 즉시 resume 시도 추가.

---

### 현재 상태 (버퍼링 없음)

| 지표 | TRT 포기 직후 | 최적화 후 (현재) |
|------|-------------|----------------|
| 첫 청크 도달 | 11.8초 | **2.1~2.9초** |
| 배치 처리 (B=16) | 800~1000ms | **730~1000ms** |
| 마지막 배치 (B=3) | 3083ms | **559~640ms** |
| 중간 버퍼링 | 있음 | **없음** |
| 끝부분 멈춤 | 있음 | **없음** |
| 첫 글자 잘림 | 있음 | **없음** |

**남은 과제**  
재생 시작 전 "버퍼링 중..." 1~2초 대기는 생성 속도(0.75배속)의 구조적 한계.  
완전 제거를 위해서는 TensorRT 재시도 필요 (예상 1.0배속 이상 달성 시 버퍼 불필요).

---

## 코덱 변환 — H264/MP4 스트리밍 vs VP9/WebM 알파 합성

채팅 응답 영상을 바 배경(`loop_bg.webm`) 위에 자연스럽게 합성하기 위해 `inference_stream`(H264/MP4) 대신 `inference_webm`(VP9 WebM + 알파)을 도입하면서 발생한 문제들과 시도 기록.

### 1. 생성 속도 9~10초 → 37초

**원인**

| 항목 | H264 (`inference_stream`) | VP9 (`inference_webm`) |
|------|---------------------------|--------------------------|
| 인코더 | `libx264 -preset ultrafast -tune zerolatency -crf 23` | `libvpx-vp9 -cpu-used 8 -deadline realtime -crf 33` |
| 채널 | 컬러만 (`yuv420p`) | 컬러 + 알파 (`yuva420p`, 듀얼 스트림) |

VP9는 H264 ultrafast 대비 원래 3~5배 이상 느린데, 알파 채널까지 함께 인코딩하면서 비용이 추가로 증가.

**참고**: 아바타 "준비"(prep, `avator_info.json` 캐시)는 1회성이라 소스 영상 포맷과 무관. 위 37초는 요청당 인코딩 비용.

---

### 2. 아바타 윤곽선에 흰색 테두리(fringe) 문제

**진단**  
출력 프레임을 픽셀 단위로 분석한 결과, 검정 배경 → 캐릭터 경계에 1~2px짜리 거의-흰색(R208 G188 B170 부근) fringe 픽셀이 색상 데이터 자체에 박혀있음을 확인.

```
x=380 R= 12 G=  0 B=  0 A=255  (배경)
x=381 R= 24 G=  8 B=  0 A=255
x=382 R=208 G=188 B=170 A=255  ← fringe
x=383 R=205 G=185 B=167 A=255  ← fringe
x=384 R=173 G=147 B=126 A=255  (캐릭터)
```

**원인 추정**  
`backend/video/*.webm` 소스(9개 전부 `alpha_mode=1` VP9)를 MuseTalk 준비 단계(`video2imgs`)에서 `cv2.VideoCapture`로 읽을 때, 알파 스트림은 무시되고 컬러 스트림만 디코딩되면서 알파 경계 부분의 색상이 왜곡되어 베이크됨.

**`-crf` 로는 해결 불가**: crf는 인코딩 품질/비트레이트만 조절 — 이미 색상 데이터에 박힌 fringe 픽셀과는 무관.

---

### 3. `_black_bg_alpha()` 알파 마스크 개선

| 버전 | 처리 | 결과 |
|------|------|------|
| 원본 | `threshold(>12) → dilate(2) → blur` | 흰 테두리 발생 (dilate가 경계를 바깥으로 확장) |
| 시도1 | `threshold → erode(1) → blur` | 테두리는 줄었지만 옷 안쪽 배경-비침 구멍이 커짐 (dilate가 옷 구멍도 같이 메워주고 있었음) |
| **채택** | `threshold → MORPH_CLOSE(2) → erode(1) → blur` | 윤곽선 위치를 유지하며 옷 안 구멍을 메우고(`MORPH_CLOSE`), 바깥 1px fringe만 제거(`erode`) |

```python
# stream_inference.py — _black_bg_alpha()
a = np.where(max_rgb > 12, np.uint8(255), np.uint8(0))
a = cv2.morphologyEx(a, cv2.MORPH_CLOSE, kernel, iterations=2)  # 옷 안 작은 구멍 메우기 (윤곽선 위치 유지)
a = cv2.erode(a, kernel, iterations=1)                          # 가장자리 흰 fringe 1px 제거
a = cv2.GaussianBlur(a, (7, 7), 0)                              # 엣지 부드럽게
```

---

### 4. VP9 webm 소스의 진짜 알파 채널 활용 (`_load_webm_alpha`)

소스가 `.webm`이면 ffmpeg `format=yuva420p,alphaextract`로 원본 알파를 직접 추출해 사용 (`_black_bg_alpha`의 임계값 방식보다 정확). 단, 알파가 전부 255(완전 불투명, black-bg 원본)이면 `None` 반환 후 `_black_bg_alpha`로 폴백.

---

### 남은 과제 / 장기 권장안

소스 아바타 영상(`backend/video/*.webm`)이 전부 VP9 `alpha_mode=1`인 것이 fringe의 근본 원인일 가능성이 높음.  
**알파 없는 불투명 mp4/mov(진짜 검정 배경)** 로 교체하면 `cv2.VideoCapture` 디코딩 왜곡이 사라질 것으로 예상.  
소스 포맷 교체는 1회성 prep에만 영향 → 요청당 37초 생성 시간에는 영향 없음 (mov로 바꿔도 느려지지 않음).

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `backend/convert_unet_trt.py` | UNet ONNX 내보내기 + TRT 엔진 빌드 |
| `backend/convert_vae_trt.py` | VAE ONNX 내보내기 + TRT 엔진 빌드 |
| `backend/build_vae_trt_only.py` | 기존 VAE ONNX에서 TRT만 재빌드 |
| `backend/MuseTalk/trt_engines.py` | TRT UNet / VAE 추론 래퍼 |
| `backend/services/ml_manager.py` | 모델 로딩, TRT 엔진 관리, 웜업 |
| `backend/MuseTalk/stream_inference.py` | 스트리밍 추론 파이프라인 |

엔진 파일 위치 (git 제외):
- `backend/MuseTalk/models/musetalkV15/unet_fp16.trt` — UNet TRT 엔진
- `backend/MuseTalk/models/sd-vae/vae_decoder.trt` — VAE TRT 엔진 (현재 미사용)

---

## 1080p `add/` 아바타 전환 이후 스트리밍 최적화

기존 `backend/video/*.webm`(검정 배경, VP9 alpha) 아바타에서 `backend/video/add/*.mp4`
(1080p, 배경 이미 합성됨) 아바타로 전환하면서 `composite_bg=False`로 분기됨
(`generation.py`의 `generate_stream`). 위 "아바타 윤곽선 fringe" 문제는 더 이상
해당되지 않지만, 풀프레임 해상도가 480p → 1080p로 커지면서 새로운 병목이 발견됨.

### 1. CPU 블렌딩 병목 — `get_image_blending` → `_blend_fast`

**원인**  
`get_image_blending`(PIL 기반)이 매 프레임마다 1080p 풀프레임 전체를 PIL Image로
변환 후 합성 → 480p에서는 무시할 만한 비용이었으나 1080p에서는 프레임당 CPU 비용이
크게 증가해 GPU 추론과 병렬로 도는 CPU 블렌딩 스레드가 병목이 될 수 있음.

**해결**  
`stream_inference.py`에 `_blend_fast()` 추가 — PIL 변환 없이 `crop_box` 영역만
numpy로 in-place 블렌딩.

```python
def _blend_fast(image, face, face_box, mask_array, crop_box):
    """get_image_blending의 PIL-free 버전.
    1080p 풀프레임 전체를 PIL로 변환하지 않고 crop_box 영역만 numpy로 합성한다."""
    x, y, x1, y1 = face_box
    x_s, y_s, x_e, y_e = crop_box
    h, w = image.shape[:2]
    if x_s < 0 or y_s < 0 or x_e > w or y_e > h:
        return get_image_blending(image, face, face_box, mask_array, crop_box)

    region = image[y_s:y_e, x_s:x_e]
    patch  = region.copy()
    patch[y - y_s:y1 - y_s, x - x_s:x1 - x_s] = face

    mask = mask_array.astype(np.float32)
    if mask.ndim == 2:
        mask = mask[:, :, np.newaxis]
    mask /= 255.0

    region[:] = (patch.astype(np.float32) * mask + region.astype(np.float32) * (1.0 - mask)).astype(np.uint8)
    return image
```

`face_box`/`crop_box`가 프레임 경계를 벗어나는 예외 케이스만 기존
`get_image_blending`으로 폴백. `get_image_blending`은 `scripts/realtime_inference.py`
(비-스트리밍 `/generate` 경로)에서도 계속 쓰이므로 공유 함수는 그대로 두고,
스트리밍 전용 경로(`_cpu_blend_write`)에서만 `_blend_fast`로 교체.

---

### 2. `_decode_fast` 프레임 누락 → 오디오/입모양 누적 드리프트

**원인**  
`_decode_fast`(VAE 디코딩 절반 + 인접 프레임 보간 최적화)에서, 배치 크기 `n`이
**짝수**일 때 출력 프레임이 `n`이 아닌 `n-1`개만 생성되는 off-by-one 버그.

- `key_latents = latents[::2]` → `k = n/2`개만 VAE 디코딩
- `interp`(인접 키프레임 평균) → `k-1`개
- 인터리브한 `merged`(`2(k-1)`개) + `key_decoded[pairs:]`(1개) = `2k-1 = n-1`개
- `torch.cat(...)[:n]`은 짧은 텐서를 `n`개로 늘려주지 못해 그대로 `n-1`개 유지

**증상**  
B=16 배치 기준, 배치 `b`에서 생성된 15개 프레임이 전체 출력 스트림의
`15b ~ 15b+14`번 자리에 위치하지만, 그 내용은 latent `16b ~ 16b+14`의 입모양임.
프레임 표시 시점(`(15b+j)/25초`)과 그 입모양에 대응하는 오디오 시점(`(16b+j)/25초`)
사이에 `b × 40ms`의 오차가 배치마다 누적됨.

17개의 B=16 배치(~11초 응답)에서는 마지막 배치 기준 **최대 ~640ms** 드리프트 +
ffmpeg `-shortest`로 인해 응답 끝부분 오디오 일부가 잘릴 수 있음.

사용자 보고: "입이 너무 못따라가 / MuseTalk의 한계인거야?" → 모델 한계가 아니라
이 최적화 코드의 인덱싱 버그였음.

**해결**  
이미 디코딩된 마지막 키프레임(`key_decoded[-1]`)을 한 번 더 채워 `n-1` → `n`으로
보정. 추가 VAE 디코딩 없이(연산 비용 0) 프레임 개수만 정확히 맞춤.

```python
# 변경 전
image = torch.cat([merged, key_decoded[pairs:]], dim=0)[:n]

# 변경 후
image = torch.cat([merged, key_decoded[pairs:], key_decoded[-1:]], dim=0)[:n]
```

**결과**  
생성 속도(성능)는 변화 없음 (배치당 UNet/VAE 시간 동일).
사용자 확인: "오 효과가 있어 확실히 잘 따라가는게 보여" — 누적 드리프트 해소로
응답 후반부 립싱크 정확도 개선.

**참고 / 남은 과제**  
`ml_manager.taesd_decoder`(TAESD 경량 디코더)가 `inference_stream(taesd=...)`로
전달되지만 `_decode_fast`에서 실제로 사용되지 않음(미구현, 항상 `None`).
향후 "보간 없이 전체 프레임을 더 빠르게 디코딩"하는 추가 속도 개선이 필요하면
TAESD 도입이 가장 유력한 후보 — 단, 실제 디코더 로딩/연결 및 버퍼링 재검증 필요.

---

### 3. 디코딩 비율 벤치마크 — 입모양 "우글우글" 개선 시도 (75% / 100%), 둘 다 보류

**배경**  
위 2번 수정(드리프트 해소) 이후에도 입 주변이 미세하게 "우글우글"거리는
현상이 남아있음. `_decode_fast`가 인접 키프레임을 평균 내 만든 보간
프레임이, 두 키프레임의 입모양이 서로 다를 때 흐릿하게 겹쳐 보이는
"고스팅" 현상이 원인으로 추정됨. 보간 비율을 줄이면(디코딩 비율을
높이면) 고스팅이 줄어들 것으로 기대되어, 50%(현재) 외에 75% / 100%
디코딩의 비용을 실측.

**측정 기준 (재생 예산)**  
`fps=25`, 배치 크기 `B=16` 기준 1배치 = 16프레임 = **640ms 분량의
영상**. `_gpu_loop`의 배치당 "합"(UNet+VAE) 시간이 640ms보다 크면,
그 차이만큼 GPU 생성이 재생을 못 따라가는 적자가 매 배치 누적됨.

---

#### 3-1. 100% 풀 디코딩 (보간 완전 제거)

**방법**  
`_decode_fast`의 `if n >= 4:` 분기를 임시로 `if False:`로 바꿔 모든
배치를 `vae.vae.decode(latents.to(dtype)).sample`(풀 디코딩) 경로로
강제한 뒤 `/api/generate_stream` 실행, 배치별 UNet/VAE 로그 비교.

**결과**

| | 50% (현재) | 100% (풀 디코딩) |
|---|---|---|
| VAE (B=16, 정상 상태) | ~450~500ms | ~700~780ms (**+250~300ms, 약 1.5배**) |
| 합 (B=16, 정상 상태) | ~550~590ms | ~790~854ms |
| 재생 예산(640ms) 대비 | 약 0.86~0.92배 (여유) | 약 1.27배 (**적자 ~175ms/배치**) |
| 첫 청크 도달 | 3.7초 | 12.6초 |

추가로 콜드스타트 스파이크 관찰: 첫 배치(B=16) VAE 5311ms, 두 번째
배치 1502ms, 마지막 배치(B=10, 처음 보는 크기) 3124ms.
`ml_manager.py`의 `_warmup_gpu`가 `_decode_fast`가 쓰는 "절반
크기"(`[::2]`) decode shape만 워밍업해두고 풀 사이즈 shape는
워밍업하지 않아 cuDNN이 처음 보는 shape마다 커널을 다시 튜닝하는
것으로 추정.

**결론**  
정상 상태만으로도 배치당 ~175ms 적자 → 17개 배치 기준 누적 ~3초.
버퍼링 재발이 거의 확정적이라 **보류**. 테스트용 임시 변경은 원복함.

---

#### 3-2. 75% 디코딩 (4프레임 중 3프레임 디코딩)

**방법**  
`_decode_fast`를 4프레임을 한 그룹으로 묶어 앞 3프레임만 VAE
디코딩하고, 마지막 1프레임은 그 그룹의 마지막 디코딩 프레임과 다음
그룹의 첫 디코딩 프레임을 평균해 보간하도록 재구현(보간 빈도
1/2 → 1/4, 보간 간격은 기존과 동일하게 2 latent step 유지). `n`이
4의 배수가 아니면 마지막 latent를 복제해 4의 배수로 맞춘 뒤 끝에서
잘라냄.

**결과** (2회 측정 — 1회차는 서버 재시작 직후, 2회차는 연속 실행)

| | 50% (현재) | 75% (1회차) | 75% (2회차) |
|---|---|---|---|
| VAE (B=16, 정상 상태) | ~450~500ms | ~569~622ms | ~527~616ms |
| 합 (B=16, 정상 상태) | ~550~590ms | ~650~697ms | ~652~702ms |
| 평균 합 (B=16) | ~570ms | ~668ms | ~670ms |
| 재생 예산(640ms) 대비 | 약 0.89배 (여유 ~70ms) | 약 **1.04배 (적자 ~28~30ms/배치)** | 동일 |
| 첫 청크 도달 | 3.7초 | 10.5초 (콜드스타트 포함) | 3.3초 |

콜드스타트 스파이크도 동일하게 재현됨:
- 1회차 배치00: VAE 3876ms (B=16 → 75%=12장 디코딩, 서버 재시작 후
  이 shape 첫 호출)
- 2회차 배치16(마지막): VAE 3009ms (B=12 → 75%=9장 디코딩, 이
  (B, 디코딩수) 조합이 처음 등장)

50%에서는 이런 스파이크가 없었던 이유는 `_warmup_gpu`가 50%
디코딩(절반 크기) shape만 워밍업해두기 때문 — 75%로 바꾸면
`ceil(B/4)*3`장 디코딩이라는 새 shape 조합마다 처음 호출 시
~2.5~3.9초 스파이크 발생. 마지막 배치 크기는 응답 길이마다 달라지므로
실제 서비스에서는 매번 다른 응답에서 무작위로 이 스파이크가 날 수 있음.

**실제 재생 확인**: 2회차 실행에서 영상 끝부분에 버퍼링이 1회
발생함. 콜드스타트(워밍업 누락)와 정상상태 적자(1.04배, 누적
~0.5초/응답) 두 요인이 모두 끝부분에 영향을 줄 수 있음 — 워밍업을
보강해도 정상상태 적자(1.04배)는 구조적으로 남음.

**결론**  
100%(1.5배, 적자 175ms/배치)보다는 훨씬 가볍지만, 정상상태 자체가
이미 재생 예산을 ~4% 초과(적자 구조)해서 응답이 길어질수록 끝부분
버퍼링 위험이 커짐. **보류**, `_decode_fast`는 50%로 원복.

---

#### 종합 비교

| 디코딩 비율 | 합 (B=16, 정상상태) | 재생 예산(640ms) 대비 | 비고 |
|---|---|---|---|
| 50% (현재, 유지) | ~570ms | 0.86~0.92배 (여유) | 버퍼링 없음 — 검증됨 |
| 약 60~65% (추정 손익분기) | ~640ms (추정) | ~1.00배 | 미검증, 선형 추정 |
| 75% | ~668~670ms | 약 1.04배 (적자 ~28ms) | 끝부분 버퍼링 발생 |
| 100% | ~790~854ms | 약 1.27배 (적자 ~175ms) | 버퍼링 거의 확정 |

**최종 결론**: 50% 디코딩(`_decode_fast` 현재 상태) 유지. "우글우글"은
당분간 감내. 추가 개선이 필요하면 위 2번에서 언급한 TAESD 경량
디코더 도입이, 보간을 줄이면서도 비용 자체를 낮출 수 있는 유일한
후보.

---

## 프론트엔드 — 응답 영상 재생(MSE) 메모리 누수

위 MuseTalk 최적화와는 별개로, 영상 재생 쪽(`frontend/js/app.js`)에서
발견된 **성능과 무관한 메모리 개선 사항**.

**원인**  
`_generateStream`은 응답마다 `new MediaSource()` + `URL.createObjectURL(mediaSource)`
로 blob URL을 만들어 `<video id="video-output">`에 연결하고, `sb.appendBuffer()`
로 그 응답의 영상 데이터(1080p, 수 MB) 전체를 버퍼에 쌓음. 응답이 끝나면
`playIdle()`이 `videoEl.src`를 `loop_bg.mp4`로 바꾸지만, 이전 blob URL을
`URL.revokeObjectURL()`로 해제하는 코드가 없었음.

브라우저의 "blob URL ↔ MediaSource" 대조표에 등록이 남아있는 한 GC가 그
MediaSource(+버퍼에 쌓인 영상 데이터)를 회수하지 못함 → 채팅을 계속할수록
응답마다 생긴 MediaSource가 누적되어 탭 메모리 사용량이 계속 증가하는 구조.

**해결**  
`playIdle()` 시작 부분에서, 현재 `videoEl.src`가 `blob:`로 시작하면
`URL.revokeObjectURL()`로 해제한 뒤 idle 영상으로 전환.

```js
function playIdle(url = VIDEO_IDLE) {
  const videoEl     = document.getElementById('video-output');
  const loadingEl   = document.getElementById('loading-video');
  const placeholder = document.getElementById('video-placeholder');

  // 이전 응답 영상의 MediaSource blob URL 해제 (버퍼 누적 방지)
  if (videoEl.src && videoEl.src.startsWith('blob:')) {
    URL.revokeObjectURL(videoEl.src);
  }

  if (loadingEl) { loadingEl.pause(); loadingEl.style.display = 'none'; }
  // ... 기존 로직(idle 영상으로 전환)
}
```

`playIdle()`은 정상 종료(`ended` → idle 복귀)와 에러 처리 양쪽 경로에서
모두 호출되므로, 한 곳만 수정해 모든 경로를 커버.

**결과**  
루프 → 첫 청크 로딩 종료 → 영상 재생 → 루프 복귀라는 기존 흐름은 그대로
유지. 응답 영상이 끝나고 idle로 돌아갈 때 그 응답의 MediaSource 참조가
해제되어 다음 GC에서 해당 영상 버퍼가 회수됨 — 대화가 길어져도 탭 메모리가
무한히 누적되지 않음.

---

## 배경 있는 영상의 "우글우글" 아티팩트 개선 시도

### 근본 원인

MuseTalk는 매 프레임마다 face parsing(BiSeNet)으로 마스크를 독립적으로 생성하고 알파블렌딩으로 합성하는 구조. 이 마스크의 경계 위치가 프레임마다 1~3px씩 달라지는 jitter가 발생하며, 단색 배경에서는 거의 보이지 않지만 복잡한 배경 텍스처 위에서는 shimmer/flickering으로 육안에 띔.

```
프레임 N:   마스크 경계가 픽셀 (100, 50)에 있음 → 배경 텍스처와 혼합
프레임 N+1: 마스크 경계가 픽셀 (102, 50)으로 이동 → 배경 픽셀 갑자기 노출 → 우글거림
```

---

### 시도 목록

#### 1. extra_margin 조정 (10 → 20 → 30 → 15)

`ml_manager.py`의 아바타 전처리 여백 픽셀.

| 값 | 결과 |
|---|---|
| 10 (기본) | 기준점 |
| 20 | "좀 덜해진 것 같다" — 약간 개선 |
| 30 | 합성 영역이 넓어져 목까지 포함 → 오히려 부자연스러움 |
| **15 (유지)** | 20과 기본 사이 균형점 |

---

#### 2. 키프레임 temporal smoothing (유지)

`stream_inference.py` `_decode_fast` 내 키프레임 간 가중 평균.

```python
# 0.15·prev + 0.70·curr + 0.15·next
prev_k = torch.cat([key_decoded[:1], key_decoded[:-1]])
next_k = torch.cat([key_decoded[1:], key_decoded[-1:]])
key_decoded = 0.15 * prev_k + 0.70 * key_decoded + 0.15 * next_k
```

VAE 추가 호출 없이 보간 프레임과의 경계 노이즈 감소. 효과 있어 유지.

---

#### 3. bbox 스무딩 window 7 → 13

`_smooth_avatar_coords`의 이동 평균 윈도우 확대. bbox 위치 지연이 오히려 더 눈에 띔 → 7로 복원.

---

#### 4. 마스크 Gaussian blur (31×31 / 51×51 / 21×21)

`_blend_fast`에서 mask_array에 GaussianBlur 추가 적용 시도. `parsing_mode="jaw"` 마스크가 좁아서 blur 적용 시 중심값까지 낮아져 **입 움직임이 사라지는** 부작용 → 완전 제거.

---

#### 5. parsing_mode "raw" 전환

`"jaw"` (입+턱 영역) → `"raw"` (얼굴 전체 피부 영역)으로 변경. 경계 위치가 얼굴 외곽선으로 이동하지만, MuseTalk가 입/턱만 학습된 모델이라 이마·눈 영역까지 VAE 재구성값으로 교체되어 품질 저하. jaw가 더 나음 → 원복.

---

#### 6. Poisson seamless cloning (cv2.seamlessClone)

`_blend_fast`의 알파블렌딩을 `cv2.seamlessClone`으로 교체. crop_box 전체 영역에서 색상이 조정되면서 마스크 외부(눈/이마)까지 영향 → 얼굴 상단에 직사각형 경계선 발생. 알파블렌딩보다 나빠짐 → 원복.

---

#### 7. distanceTransform 테두리 페더링 (8px)

마스크 중심은 1.0 유지하고 테두리 8px만 거리 기반 0→1 그라디언트 적용.

```python
dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
alpha = np.clip(dist / 8.0, 0.0, 1.0)
```

전처리 마스크에 이미 ~15px Gaussian blur가 적용돼 있어서(get_image_prepare_material) 이진화 없이 거리 변환 적용 시 효과 미미. 우글거림 지속 → 원복.

---

#### 8. 마스크 temporal smoothing (window=7)

`mask_list_cycle`을 인접 프레임 마스크 평균으로 교체 (`_smooth_avatar_masks`). bbox 스무딩과 달리 마스크는 서로 다른 얼굴 위치에서 계산된 값을 평균 내므로, 마스크 경계가 방향성 있는 상하 이동 패턴으로 바뀜 → "우글우글" 대신 "덜덜 떨리는" 현상으로 변형. 더 나빠짐 → 원복.

---

#### 9. 배경 고정 레이어 (static_bg)

아바타 프레임들의 평균값을 정적 배경으로 저장하고, `_blend_fast`의 비-face 영역에 animated frame 대신 static_bg 사용. 아바타 영상이 동적(바텐더 움직임)이라 30프레임 평균이 완전히 흐릿한 유령 이미지가 됨 → 원복.

---

#### 10. 마스크 erode(3px) + 재블러(15×15)

마스크 이진화 후 침식으로 경계를 배경 텍스처가 아닌 얼굴 안쪽으로 이동. Gemini 제안 방식.

```python
binary = (m > 20).astype(np.uint8) * 255
eroded  = cv2.erode(binary, kernel_7x7, iterations=1)
blurred = cv2.GaussianBlur(eroded, (15, 15), 0)
```

경계 위치 자체는 약간 이동하지만 마스크 jitter(프레임마다 다른 위치)는 해결 안 됨. 우글거림 지속 → 원복.

---

#### 11. 출력 프레임 temporal 블렌딩 (0.85 / 0.15)

`_cpu_blend_write`에서 최종 출력 프레임에 이전 프레임 15% 혼합.

```python
frame = frame * 0.85 + prev_frame * 0.15
```

flickering 진폭을 약간 줄이지만 경계 위치 자체의 변동은 그대로라 효과 미미. 우글거림 지속 → 원복.

---

### 원인 분석 결론

| 구분 | 원인 |
|---|---|
| 단색 배경 영상 (test.mp4) | 1~3px 경계 변동이 균일한 색상 위에서 눈에 안 띔 → 부드러움 |
| 원본 배경 포함 영상 (bartender_cocktail 등) | 배경과 캐릭터가 하나의 렌더링으로 통합 → face parsing 안정 → 부드러움 |
| CapCut AI 합성 영상 | CapCut AI 배경 삭제도 프레임 독립 추론 → 엣지 픽셀이 프레임마다 달라짐 → MuseTalk face parsing jitter와 이중으로 겹쳐 우글거림 심화 |

**최종 결론**: 소프트웨어 파이프라인 수정으로는 구조적 한계 이상 개선 어려움.
추천 방향: 원본 배경 포함 영상 또는 단색 배경 영상 + 프론트엔드 배경 합성.

---

## 후속 조치 — 영상 교체 및 안정화

### 1. 아바타 영상 교체 (원본 배경 포함 영상)

위 결론에 따라 CapCut AI 합성 영상 대신 **처음부터 배경이 포함된 영상** 8개로 교체.

| 항목 | 이전 | 이후 |
|------|------|------|
| 파일명 | 한글 (예: `바텐더_칵테일_...mp4`) | 영어 (예: `bartender_smile.mp4`) |
| 배경 | CapCut AI 배경 제거 후 합성 | 원본 배경 포함 (3D 렌더링) |
| 우글거림 | 심함 (이중 jitter) | 거의 없음 |

**한글 파일명 문제**: Python `re.sub(r"[^\w]", "_", stem)`이 한글을 `\w`로 포함시켜 `avatar_id`에 한글이 들어가 내부 파일 처리 실패. 파일명을 영어로 변경하여 해결.

---

### 2. 프론트엔드 영상 파일 용량 최적화

`loop_bg.mp4`가 192MB (비트레이트 25Mbps CBR)로 브라우저 Range Request 시 소켓 연결이 중간에 끊겨 서버 로그에 `socket.send() raised exception`이 대량 발생.

**원인**: 25Mbps CBR로 내보낸 192MB 파일 → 브라우저가 조각(Range Request)으로 가져오다가 연결 끊김 → uvicorn이 이미 닫힌 소켓에 데이터 전송 시도 → 예외 로그 폭발.

**압축 결과** (FFmpeg CRF 26, preset slow, 25fps):

| 파일 | 원본 | 압축 후 |
|------|------|---------|
| loop_bg.mp4 | 192MB | 7.3MB |
| loading_start.mp4 | 30MB | 753KB |
| loading_finish.mp4 | 12MB | 415KB |

**CapCut 내보내기 권장 설정** (이후 영상 제작 기준):

| 항목 | 권장값 |
|------|--------|
| 해상도 | 1080P (1920×1080, 16:9) |
| 비트 전송률 | 4000~5000 Kbps VBR |
| 코덱 | H.264 / mp4 |
| 프레임 속도 | 25fps (MuseTalk 출력과 동일) |

---

### 3. 영상 표시 비율 통일 (object-fit: contain)

모든 영상(아바타 응답 영상, loop_bg, loading_start/finish)을 16:9로 통일하고 CSS를 `object-fit: contain`으로 변경. 영상과 컨테이너 비율이 일치하면 여백 없이 꽉 차게 표시됨.

```css
/* stage.css */
#video-output       { object-fit: contain; }
#video-output.idle  { object-fit: contain; }
#loading-video      { object-fit: contain; }
```

---

### 4. bbox 스무딩 — 이동 평균 → EMA 전환

배경 포함 영상에서 우글거림은 해소됐지만 **상하 미세 떨림(bbox Y좌표 jitter)** 이 남아있어 스무딩 방식을 개선.

#### 이동 평균 window 조정 시도

| window | 결과 |
|--------|------|
| 7 (기존) | 잔여 jitter 있음 |
| 15 | jitter 감소, 고개 추적 약간 느려짐 |
| 19 | 입 위치 벗어나는 현상 발생 |
| 23 | 입 위치 많이 벗어남 |

**한계**: 이동 평균은 window 크기와 무관하게 과거 프레임을 동일하게 가중 → window가 커질수록 실제 머리 움직임을 느리게 따라가 합성 위치가 벗어남.

#### EMA(지수 이동 평균) 전환 — 채택

```python
def _smooth_avatar_coords(av, alpha: float = 0.35):
    # alpha: 최신 프레임 가중치 (낮을수록 강한 스무딩, 높을수록 빠른 추적)
    # 루프 영상 경계 처리: 1차 패스 워밍업 후 2차 패스 실제 적용
    _, warm_state = run_ema(coords, init)
    smoothed, _ = run_ema(coords, warm_state)
```

최근 프레임에 35%, 이전 값에 65% 가중치 → 실제 머리 움직임은 빠르게 추적하면서 1~2px 랜덤 jitter는 필터링. 이동 평균 대비 추적 지연 없이 스무딩 효과 유지.

**조정 기준**:
- 떨림이 남으면 alpha를 낮춤 (예: 0.25)
- 입 위치가 벗어나면 alpha를 높임 (예: 0.5)
