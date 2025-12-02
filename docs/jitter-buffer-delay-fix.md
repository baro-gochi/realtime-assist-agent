# WebRTC jitterBufferDelay 선형 증가 문제 해결

## 문제 현상

### 증상
- 클라이언트의 `inbound-rtp` 통계에서 `jitterBufferDelay`가 시간이 지남에 따라 **직선으로 계속 증가**
- 오디오 품질 자체는 괜찮지만, 지연이 계속 누적됨
- `jitterBufferTargetDelay`, `jitterBufferMinimumDelay`도 동일하게 증가

### 그래프 특성 (문제 진단의 핵심 증거)

| 지표 | 값 | 의미 |
|------|-----|------|
| `jitter` | 0.005 ~ 0.015 | 네트워크 품질 매우 양호 |
| `packetsLost` | ≈ 0 | 패킷 손실 없음 |
| `packetsSent/s` | ≈ 50 | 정상 (48kHz, 20ms = 50 packets/s) |
| `totalPacketSendDelay` | ≈ 0 | 서버가 패킷을 즉시 전송 |
| `jitterBufferDelay` | 직선 증가 | **RTP timestamp drift** |

### 결론
> 네트워크 문제가 아니라 **서버가 보내는 RTP 패킷의 timestamp 또는 송출 간격이 불규칙**

---

## 원인 분석

### 1차 원인: MediaRelay 미사용

**문제 코드 (수정 전)**
```python
@pc.on("track")
async def on_track(track):
    # 같은 트랙을 여러 소비자에게 직접 전달
    relay_track = AudioRelayTrack(track, stt_queue, elevenlabs_queue)
    self.audio_tracks[peer_id] = relay_track  # 다른 피어 전달용
    consumer_task = asyncio.create_task(self._consume_audio_track(peer_id, relay_track))  # STT용
    await self._relay_to_room_peers(peer_id, room_name, relay_track)  # 릴레이용
```

**문제점**
- 같은 `AudioRelayTrack`을 여러 소비자(STT, 다른 피어들)가 공유
- `recv()` 호출 시 프레임이 분산되어 일부 소비자는 프레임 건너뜀
- RTP timestamp 불연속 발생

**1차 수정: MediaRelay.subscribe() 사용**
```python
@pc.on("track")
async def on_track(track):
    # STT용 트랙 (별도 구독)
    stt_track_source = self.relay.subscribe(track)
    stt_relay_track = AudioRelayTrack(stt_track_source, stt_queue, elevenlabs_queue)

    # 원본 트랙 저장 (릴레이 시 새로 구독)
    self.audio_tracks[peer_id] = track

    # 각 피어에게 별도 구독 트랙 전달
    await self._relay_to_room_peers(peer_id, room_name, track)

async def _relay_to_room_peers(self, source_peer_id, room_name, track):
    for peer_id, pc in self.peers.items():
        # 각 피어에게 독립적인 트랙 복사본 전달
        relayed_track = self.relay.subscribe(track)
        pc.addTrack(relayed_track)
```

**결과**: 음질 개선, 하지만 jitterBufferDelay는 여전히 증가

---

### 2차 원인: 프레임 Pacing 불규칙

**문제점**
- `MediaRelay`는 프레임을 복제하지만 **전달 타이밍(pacing)을 보장하지 않음**
- 원본 트랙에서 프레임이 불규칙하게 도착하면 그대로 전달
- RTP timestamp는 유지되지만, 실제 송출 시간과 drift 발생

**정상적인 RTP 스트림**
```
패킷 1: timestamp=0,    송출 시간=0ms    ✓
패킷 2: timestamp=960,  송출 시간=20ms   ✓
패킷 3: timestamp=1920, 송출 시간=40ms   ✓
```

**drift가 발생한 RTP 스트림**
```
패킷 1: timestamp=0,    송출 시간=0ms
패킷 2: timestamp=960,  송출 시간=22ms   (2ms drift)
패킷 3: timestamp=1920, 송출 시간=45ms   (5ms drift, 누적)
```

→ 브라우저가 이를 보정하려고 jitterBuffer를 계속 늘림

---

## 최종 해결책: PacedRelayTrack

### 핵심 아이디어
1. `MediaRelay.subscribe()`로 프레임을 받음
2. 받은 프레임을 버퍼에 저장
3. **정확히 20ms 간격**으로 프레임을 꺼내서 반환
4. **timestamp도 960씩 정확히 증가**하도록 재설정

### 구현 코드

```python
class PacedRelayTrack(MediaStreamTrack):
    """정확한 20ms 간격으로 오디오 프레임을 pacing하는 릴레이 트랙."""
    kind = "audio"

    def __init__(self, source, sample_rate=48000, frame_duration_ms=20):
        super().__init__()
        self.source = source
        self.sample_rate = sample_rate
        self.samples_per_frame = int(sample_rate * frame_duration_ms / 1000)  # 960

        self._buffer = asyncio.Queue(maxsize=50)  # ~1초 버퍼
        self._pts = 0
        self._time_base = Fraction(1, sample_rate)
        self._start_time = None
        self._frame_index = 0
        self._consumer_task = None

    async def _consume_source(self):
        """백그라운드에서 소스 트랙의 프레임을 버퍼에 저장"""
        while True:
            frame = await self.source.recv()
            try:
                self._buffer.put_nowait(frame)
            except asyncio.QueueFull:
                # 버퍼 오버플로우 시 오래된 프레임 제거
                self._buffer.get_nowait()
                self._buffer.put_nowait(frame)

    async def recv(self):
        # 소비 태스크 시작 (최초 1회)
        if self._consumer_task is None:
            self._consumer_task = asyncio.create_task(self._consume_source())

        # 시작 시간 설정 (최초 1회)
        if self._start_time is None:
            self._start_time = time.perf_counter()

        # 정확한 20ms 간격 대기 (monotonic clock 기반)
        target_time = self._start_time + (self._frame_index * 20) / 1000.0
        wait = target_time - time.perf_counter()
        if wait > 0:
            await asyncio.sleep(wait)

        self._frame_index += 1

        # 버퍼에서 프레임 가져오기 (없으면 silence)
        try:
            frame = self._buffer.get_nowait()
        except asyncio.QueueEmpty:
            frame = self._create_silence_frame()

        # timestamp 정확히 960씩 증가
        frame.pts = self._pts
        frame.time_base = self._time_base
        self._pts += self.samples_per_frame

        return frame
```

### 적용 위치 (3곳)

```python
# 1. _relay_to_room_peers
async def _relay_to_room_peers(self, source_peer_id, room_name, track):
    for peer_id, pc in self.peers.items():
        relayed_track = self.relay.subscribe(track)
        paced_track = PacedRelayTrack(relayed_track)  # Pacing 적용
        pc.addTrack(paced_track)

# 2. handle_offer (renegotiation)
relayed_track = self.relay.subscribe(original_track)
paced_track = PacedRelayTrack(relayed_track)  # Pacing 적용
pc.addTrack(paced_track)

# 3. handle_offer (initial connection)
relayed_track = self.relay.subscribe(original_track)
paced_track = PacedRelayTrack(relayed_track)  # Pacing 적용
pc.addTrack(paced_track)
```

---

## 아키텍처 다이어그램

### 수정 전
```
클라이언트A → 서버 (원본 트랙)
                ↓
         AudioRelayTrack (공유)
           ├── STT 소비자 (recv)
           ├── 피어B (recv)
           └── 피어C (recv)
                ↓
         프레임 분산 → timestamp 불연속 → jitterBufferDelay 증가
```

### 수정 후
```
클라이언트A → 서버 (원본 트랙)
                ↓
         MediaRelay.subscribe() × N (독립 버퍼)
                ↓
         ┌─────────────────────────────────────────┐
         │           PacedRelayTrack               │
         │  - 백그라운드 버퍼링                      │
         │  - 정확히 20ms 간격 송출                  │
         │  - pts = 0, 960, 1920, ... (정확히 증가)  │
         └─────────────────────────────────────────┘
                ↓
         서버 → 클라이언트B (안정적인 RTP 스트림)
```

---

## 기대 효과

| 지표 | 수정 전 | 수정 후 |
|------|---------|---------|
| jitterBufferDelay | 직선 증가 | 20~50ms 근처 안정 |
| RTP timestamp | 불규칙 | 정확히 960씩 증가 |
| 프레임 pacing | 불규칙 | 정확히 20ms 간격 |
| 음질 | 괜찮음 | 유지 |

---

## 참고: Opus 코덱 표준 값

| 항목 | 값 | 설명 |
|------|-----|------|
| Sample Rate | 48000 Hz | Opus 표준 |
| Frame Duration | 20 ms | 일반적인 WebRTC 설정 |
| Samples per Frame | 960 | 48000 × 0.02 |
| Packets per Second | 50 | 1000 / 20 |

---

## 관련 파일

- `backend/peer_manager.py`: PacedRelayTrack 클래스 및 적용
- `frontend/src/webrtc.js`: 클라이언트 WebRTC 설정 (jitterBufferTarget: 150ms)

---

## 트러블슈팅 로그 확인

### 정상 동작 시 로그
```
🎵 PacedRelayTrack: First frame received from source
🎵 PacedRelayTrack: First frame sent with pts=0
🎵 PacedRelayTrack: 500 frames sent, buffer_size=2, silence=0
```

### 버퍼 부족 시 로그 (주의 필요)
```
⚠️ PacedRelayTrack: Buffer empty, generating silence
⚠️ PacedRelayTrack: 50 silence frames generated
```

→ silence 프레임이 많이 생성되면 소스 트랙의 프레임 공급이 늦는 것이므로 네트워크 또는 소스 문제 확인 필요

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2024-XX-XX | 1차 수정: MediaRelay.subscribe() 적용 - 음질 개선 |
| 2024-XX-XX | 2차 수정: PacedRelayTrack 구현 - jitterBufferDelay 안정화 |
