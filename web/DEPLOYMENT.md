# AWS 배포 상태 · 2026-09-29

웹 빌드: `/var/www/classy-web/releases/20260929-web-v3-01`

현재 링크: `/var/www/classy-web/current`

EC2: `classy-aws`, Elastic IP `15.165.25.7`

웹은 별도 Nginx 가상 호스트로 구성했습니다. Flutter는 수정하지 않았고,
기존 `api.classystudy.com` Nginx 설정도 그대로 유지했습니다. 추가 AWS 리소스는 생성하지 않았습니다.
Django는 `LectureListAPIView.permission_classes`만 `AllowAny`로 바꿨습니다.
판매 중지·삭제·관리자 차단 강의 제외 및 영상 재생·대여·등록의 인증 권한은 유지합니다.
웹 CSP에는 사용자가 고른 썸네일 미리보기를 위한 `img-src blob:`를 추가했습니다.

## 현재 상태

공개 배포 완료: https://classystudy.com/
회원가입, 비밀번호 재설정, 강사 스튜디오 및 서비스 관리 기능을 v3로 배포했습니다.
공개 강의 목록은 운영 데이터 2개를 반환하며 브라우저에서도 표시됨을 확인했습니다.
DNS 전환 및 Let's Encrypt 인증서 발급을 완료했습니다. 인증서 만료일은 2026-12-27이며,
certbot.timer와 Nginx reload hook으로 자동 갱신합니다.
Nginx 내부 검증 서버(127.0.0.1:8181)도 유지합니다.

가비아 DNS에서 다음 두 레코드를 변경했습니다. 네임서버, api, 메일용 MX/TXT는 유지했습니다.

| 유형 | 호스트 | 이전 값 | 현재 값 |
| --- | --- | --- | --- |
| A | @ | 216.24.57.1 | 15.165.25.7 |
| CNAME | www | classy-2s0o.onrender.com. | classystudy.com. |

현재 apex TTL은 1800초, www TTL은 600초이므로 기존 캐시는 변경 후에도 잠시 남을 수 있습니다.

## HTTPS 설정 기록

두 이름이 새 IP로 해석되는 것을 확인한 뒤 아래 스크립트로 전환했습니다:

```sh
ssh classy-aws 'bash /var/www/classy-web/deploy/enable-https.sh'
```

스크립트는 DNS가 준비되지 않으면 중단합니다. 준비되면 기존 Let's Encrypt 계정을 사용하여
두 이름의 인증서를 발급하고, HTTPS 가상 호스트를 설치한 뒤 Nginx 문법 검사와 reload를 합니다.
www 및 HTTP 요청은 `https://classystudy.com`으로 리다이렉트합니다.
갱신 후 Nginx reload hook은 `/etc/letsencrypt/renewal-hooks/deploy/classy-web-reload`에 설치했습니다.
공개 HTTPS 브라우저 검증을 통과했습니다. 실제 API 상태/과목 목록, 비로그인 접근 제한,
Pretendard 로딩, CSP 및 약관 주소 6개를 확인했고 브라우저 오류는 없었습니다.
HTTP 및 www 리다이렉트도 확인했습니다. 로그인 이후 거래 흐름은 모의 API로 검증했으며,
실제 계정의 로그인 및 거래는 이번 공개 검증에 포함하지 않았습니다.

## 검증

로컬: `http://127.0.0.1:4173` (`npm start`).

AWS 내부 검증용 터널:

```sh
ssh -L 4174:127.0.0.1:8181 -N classy-aws
```

다른 터미널에서 `node tests/aws-smoke.mjs`를 실행합니다.
`CLASSY_TEST_ORIGIN=https://classystudy.com`을 지정하면 전환 후 공개 도메인을 검사할 수 있습니다.

이용약관/개인정보처리방침은 기존 사이트 원문을 복사해 `/service-terms`, `/privacy`에 제공하며,
앱에서 사용하는 마지막 슬래시 및 `?embed=1` 주소도 유지합니다.

## 복구

v3 전환 전 백업: `/var/www/classy-web/backups/20260929-web-v3-01/`.
기존 프론트 릴리스는 `releases/20260929-web-v2-01`이며 삭제하지 않았습니다.
백업의 `lecture-views.py`는 Django `config/apps/lecture/views.py` 원본이고,
`nginx-locations.conf`는 `/etc/nginx/snippets/classy-web-locations.conf` 원본입니다.
전체 v3 롤백 시 두 파일과 current 링크를 함께 복원하고 Django restart 및 Nginx 문법 검사 후 reload합니다.
배포 중 Django 재시작 직후 일시적 502가 있었으며 재시도 후 API 정상 상태와 공개 목록을 확인했습니다.

검증: 프론트 단위 테스트 3개, Django 강의 테스트 8개, 기존 브라우저 흐름 및 신규 회원가입·업로드·서비스 작업 테스트 통과.
운영 공개 스모크 테스트는 읽기 전용입니다. 실제 SMS·회원가입·업로드·결제·정산 신청은 실행하지 않았습니다.

전환 전의 Render 사이트와 DNS 값은 위 표에 기록돼 있습니다. 기존 API Nginx 설정은
`/etc/nginx/sites-available/classy-aws`이며 변경하지 않았습니다.
웹만 비활성화하려면 정확히 `/etc/nginx/sites-enabled/classy-web` 링크만 제거한 뒤
`nginx -t` 통과 후 reload합니다. API 사이트 링크인 `classy`를 제거하지 마세요.
향후 업데이트는 새 release 디렉터리에 업로드하고 current 링크를 원자적으로 교체합니다.

## 정책 문서 개정 절차

이용약관과 개인정보처리방침은 `web/public/policies/manifest.json`과 시행일별 HTML 파일로 관리합니다. 기존 시행본은 수정하거나 삭제하지 않습니다.

1. `npm run policy:add -- privacy 2026-10-19` 또는 `npm run policy:add -- service-terms 2026-10-19`를 실행합니다.
2. 명령이 현재 시행본을 새 파일로 복사하고, manifest와 `POLICY_VERSIONS`를 같은 시행일로 갱신합니다. 적용 전 확인만 하려면 끝에 `--dry-run`을 붙입니다.
3. 생성된 새 HTML의 본문을 법무 검토본으로 수정합니다. 이전 시행본은 수정하지 않습니다.
4. `npm test`, `npm run build`, 정책 URL 스모크 테스트를 통과한 뒤 `bash deploy/aws/deploy.sh all`로 배포합니다.

빌드 과정은 manifest의 최신 시행본을 `dist/privacy.html`, `dist/service-terms.html`로 자동 복사합니다. 따라서 운영 Nginx와 Flutter 앱의 기존 `?embed=1` URL은 변경하지 않습니다. 과거 시행본은 `/policies/<document-type>/<YYYY-MM-DD>.html`의 고정 URL로 계속 공개합니다.
