# Classy 수동 배포 가이드

이 문서는 GitHub Actions 없이 VS Code의 Git Bash에서 Classy 운영 환경을 배포하는 절차다.

- 웹 사이트: `https://classystudy.com`
- Django API: `https://api.classystudy.com`
- 웹 운영 경로: `/var/www/classy-web`
- Django 운영 경로: `/home/ubuntu/classy-aws`

`deploy/aws/deploy.sh`가 웹 빌드·업로드·릴리스 전환과 Django 업로드·마이그레이션·정적 파일 수집·서비스 재시작을 순서대로 수행한다. GitHub 푸시는 운영 반영이 아니다.

## 0. 최초 1회: SSH 별칭 설정

`~/.ssh/config`에 운영 서버를 별칭으로 등록한다. 아래 값은 현재 GUIDE의 운영 서버 기준이다. 실제 운영 서버·포트·계정이 다르면 그 환경의 값으로 교체한다.

```sshconfig
Host classy-aws
    HostName 15.165.25.7
    User ubuntu
    Port 22
    IdentityFile C:/Users/woals/keys/classy_keypair.pem
    IdentitiesOnly yes
```

다른 별칭을 이미 사용 중이면 실행할 때만 `DEPLOY_HOST`로 지정할 수 있다.

```bash
DEPLOY_HOST=myserver bash deploy/aws/deploy.sh all
```

연결을 한 번 확인한다.

```bash
ssh classy-aws "whoami"
```

## 1. 배포 전 소스 이력 확인

스크립트는 커밋이나 푸시를 자동 수행하지 않는다. 배포할 변경만 선택하고 GitHub에 이력을 남긴다.

```bash
cd /c/Users/woals/AndroidStudioProjects/classy-backend

git diff --check
git status --short
git add <변경한-파일-경로>
git commit -m "설명"
git push origin "$(git branch --show-current)"
```

## 2. 한 명령으로 배포

Git Bash에서 백엔드 저장소 루트로 이동한 뒤, 변경 범위에 맞는 명령 하나만 실행한다.

```bash
cd /c/Users/woals/AndroidStudioProjects/classy-backend

# React/CSS/웹 정적 파일만 수정했을 때
bash deploy/aws/deploy.sh web

# Django API, 모델, 관리자, config, requirements.txt만 수정했을 때
bash deploy/aws/deploy.sh api

# 웹과 Django를 모두 수정했을 때: 웹 배포 후 Django 배포
bash deploy/aws/deploy.sh all
```

`web`은 새 릴리스 폴더를 만든 뒤 `current` 링크를 원자적으로 교체하며 Django와 Nginx를 재시작하지 않는다. `api`는 `.env`, 미디어 파일, DB, 가상환경, 빌드 산출물을 제외하고 업로드한 후 의존성 설치, `check --deploy`, `migrate`, `seed_reference_data`, `collectstatic`, `classy` 재시작, 상태 및 헬스체크를 수행한다.

SSH 별칭이 `classy-aws`가 아닌 경우에만 다음처럼 실행한다.

```bash
DEPLOY_HOST=myserver bash deploy/aws/deploy.sh all
```

## 3. 웹 롤백

새 웹 릴리스 배포 시 출력된 `Previous web release` 경로를 사용한다.

```bash
bash deploy/aws/deploy.sh rollback-web /var/www/classy-web/releases/이전-릴리스-이름
```

## 4. 배포 완료 기준과 문제 확인

웹 배포는 마지막 출력이 새 `/var/www/classy-web/releases/...` 경로이고 요청 헤더가 정상 응답이면 완료다. Django 배포는 `classy`, `nginx`, `redis-server`가 모두 `active`이고 `https://api.classystudy.com/healthz/`가 `{"status":"ok"}`를 반환하면 완료다.

서비스가 시작하지 않으면 아래로 현재 로그만 확인한다.

```bash
ssh classy-aws "sudo journalctl -u classy -n 100 --no-pager"
```

## 5. 주의사항

- `/home/ubuntu/classy-aws/.env`는 절대 업로드하거나 출력하지 않는다.
- `migrate`는 운영 데이터 구조를 변경할 수 있으므로, 데이터 영향이 있는 마이그레이션은 백업·복구 계획을 먼저 확인한다.
- `prepare-host.sh`는 최초 서버 준비용이므로 일반 배포마다 실행하지 않는다.
- Flutter 변경은 이 스크립트의 대상이 아니다. APK/AAB를 별도로 빌드하고 Play Console에 업로드해야 한다.
