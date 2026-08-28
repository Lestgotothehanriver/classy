# Apple 인앱 결제 운영 체크리스트

환경 변수는 저장소의 `.env`가 아니라 Render 서비스의 **Environment**에만
등록해도 된다. 배포 프로세스가 해당 변수를 읽으므로 운영 비밀키를 로컬 파일이나
Git에 복사하지 않는다.

## Render 환경 변수

| 변수 | 값 |
| --- | --- |
| `APPLE_BUNDLE_ID` | `com.classystudy.app` |
| `APPLE_APP_ID` | App Store Connect의 숫자형 Apple ID |
| `APPLE_IAP_ISSUER_ID` | In-App Purchase API 키의 Issuer ID |
| `APPLE_IAP_KEY_ID` | `.p8` 키의 Key ID |
| `APPLE_IAP_PRIVATE_KEY_BASE64` | `AuthKey_*.p8` 파일 전체를 base64로 인코딩한 한 줄 값 |
| `APPLE_IAP_ENVIRONMENT` | 샌드박스 검증 중 `SANDBOX`, 출시 전 `PRODUCTION` |
| `APPLE_IAP_ENABLE_ONLINE_CHECKS` | `true` |

`APPLE_IAP_PRIVATE_KEY_BASE64` 생성 예시(macOS):

```bash
base64 < AuthKey_XXXXXXXXXX.p8 | tr -d '\n'
```

## App Store Connect

- 아래 상품을 모두 **Consumable**로 만들고 앱 코드와 정확히 같은 ID를 사용한다.
  `cash_500`, `cash_1000`, `cash_5000`, `cash_10000`, `cash_50000`
- App Store Server Notifications는 V2로 설정한다.
- Production URL은 `https://classystudy.com/cash/webhook/apple/`을 사용한다.
- Sandbox URL은 `APPLE_IAP_ENVIRONMENT=SANDBOX`인 별도 Render 스테이징
  서비스의 `/cash/webhook/apple/`을 사용한다. 별도 서비스가 없다면 샌드박스
  검증 기간에만 운영 URL을 연결하고, 운영 전환 시 Production URL만 남긴다.
- 앱의 Bundle ID가 `com.classystudy.app`인지 확인한다.

## 배포 후 검증

Render Shell에서 다음 순서로 실행한다.

```bash
python manage.py migrate
python manage.py check --deploy
python manage.py verify_apple_iap_setup --request-test-notification
```

마지막 명령은 Apple 서명 검증기와 API 키를 로드하고 Apple에 테스트 알림을
요청한다. Django Admin의 **App Store webhook events**에 `TEST` 이벤트가
`PROCESSED`로 남으면 서버 알림 경로까지 정상이다.

샌드박스 테스터로 실제 iPhone에서 각 상품을 한 번 구매한 뒤 다음을 확인한다.

1. App Store에 표시된 현지화 가격이 결제 버튼과 같다.
2. 구매 직후 캐시가 한 번만 증가하고 구매 내역이 생긴다.
3. 같은 거래가 재전송되어도 캐시가 다시 증가하지 않는다.
4. 충전한 캐시로 강의를 대여하면 잔액과 시청 권한이 즉시 반영된다.
5. App Store Connect에서 환불 테스트 후 캐시가 회수된다. 이미 사용한 캐시는
   `cash_debt`로 기록되고 다음 충전에서 먼저 상계된다.

샌드박스 확인이 끝난 뒤 Render의 `APPLE_IAP_ENVIRONMENT`를 `PRODUCTION`으로
변경하고 재배포한다. 운영 전환 후에도 `python manage.py check --deploy`를 다시
실행한다.
