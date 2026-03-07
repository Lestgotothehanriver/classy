# 채팅 알림 워크플로우

## 목표/조건

* **조건 1**: 사용자가 **해당 채팅방에 웹소켓으로 연결 중**이면 알림(푸시)을 보내지 않는다.
* **조건 2**: **새 메시지 객체 생성 시**, **해당 방 참여자**에게만 알림을 보낸다(단, 현재 웹소켓 연결자는 제외).

---

## 핵심 개념

* **참여자(participants)**: 방의 구성원. `ChatRoom.participants`
* **웹소켓 연결자(online)**: 지금 그 **방 화면을 열고 웹소켓이 연결된 사용자**
* **Presence 저장소**: Redis(권장) 기반 Django cache

  * 키: `chat:room:{room_id}:online`
  * 값: 해당 방에 **현재 연결 중**인 `user_id` 집합
  * TTL: 예시 24h

---

## 사전 준비 (로그인 후 1회)

* **단말 토큰 등록 API**

  * `POST /api/device-token/`
  * Body: `{"token": "<FCM_device_token>", "platform": "ios|android|web"}`
  * 목적: **푸시를 보낼 “단말”을 식별**하기 위해 서버에 저장

---

## 동작 흐름 (타임라인)

1. **방 화면 진입**

* 클라이언트가 웹소켓 연결 시도: `/ws/chat/{room_id}/?token=<auth-token>`
* 서버 `connect()`:

  * 인증(토큰 → `self.user`) 및 `self.room_id` 파싱
  * `group_add(room_group, channel_name)`
  * Presence에 `user.id` 추가 → 이 유저는 **해당 방 온라인 상태**

2. **누군가 메시지 전송 (DB 저장)**

* `ChatMessage(room, sender, text/attachment)` 저장

3. **post\_save 시그널 작동 (새 메시지일 때만)**

* 참여자 집합: `participants = set(room.participants)`
* 온라인 집합: `online = set(cache["chat:room:{room_id}:online"])`
* 보낸 사람 제외: `{sender_id}`
* **푸시 대상 계산**

  ```
  targets = participants - {sender_id} - online
  ```
* `push_to_users(targets, title, body, data)` → FCM 발송

4. **대상 단말에서 푸시 수신**

* OS 알림 표시 → 사용자가 탭 → 앱이 `room_id` 화면 열고 **웹소켓 재연결**
* 재연결되면 Presence에 다시 추가 → **이후 이 방 푸시는 차단**

5. **방 나가기/백그라운드**

* 서버 `disconnect()`:

  * 그룹 제거
  * Presence에서 `user.id` 제거
* 이후 새 메시지 발생 시, 이 사용자는 **온라인에서 빠져 있으므로** 다시 푸시 대상 포함

---

## 컴포넌트별 역할

### Presence (consumers.py)

* `connect()`에서 온라인 집합에 `user.id` 추가
* `disconnect()`에서 제거
* 저장 위치: Django cache(권장: Redis)

### 푸시 트리거 (signals.py)

* `post_save(ChatMessage, created=True)`에서 대상 계산 및 발송

### 푸시 전송 (notifications.py)

* FCM로 `registration_ids`에 일괄 전송
* 서버키: `FCM_SERVER_KEY` (환경변수)

### 단말 토큰 저장 (models/views)

* `UserDeviceToken(user, token, platform, is_active)`
* `/api/device-token/` 으로 등록·비활성화

---

## 토큰 구분 (중요)

* **Auth Token**: REST/웹소켓 **인증**용. “누가 접속했는가”를 판별
* **FCM Device Token**: **푸시 수신**용. “어느 기기로 보낼 것인가”를 판별

---

## 엣지 케이스 & 정책

* **한 유저가 여러 기기**: 기본 구현은 **유저 단위 Presence** → 한 기기라도 방에 연결돼 있으면 **그 유저의 모든 기기에 푸시 안 보냄**

  * 기기 단위 제어가 필요하면 Presence를 `device_token` 기준으로 바꿔 운영
* **앱 포그라운드지만 해당 방이 아님**: 그 방에 웹소켓 미연결 → **푸시 보냄**
* **텍스트 없는 메시지(이미지/파일)**: `body = text or "새 이미지/파일이 도착했습니다."` 등으로 처리

---

## 체크리스트

* [ ] `ChatRoom.participants (M2M to User)` 존재
* [ ] `ChatMessage(room FK, sender FK, text/attachment)` 존재
* [ ] `consumers.py`에서 `connect()/disconnect()`로 Presence 갱신
* [ ] `signals.py`의 `post_save(ChatMessage)` 등록 및 `apps.py.ready()`에서 로딩
* [ ] `UserDeviceToken` 모델/토큰 등록 API 연결
* [ ] `FCM_SERVER_KEY` 설정
* [ ] 캐시 백엔드 Redis 구성(멀티 인스턴스 환경 권장)

---

## Presence/키 예시

```text
Key:   chat:room:42:online
Value: [7, 13, 25]  # 현재 room_id=42에 접속한 user_id 목록
TTL:   86400 (24h)  # 안전장치; 보통 disconnect 시 즉시 제거됨
```

---

## 요약

* **방에 붙어 있으면(웹소켓 연결) 푸시 X**, **붙어 있지 않으면(참여자) 푸시 O**.
* 계산식은 한 줄:

  ```
  targets = participants - {sender} - online
  ```
