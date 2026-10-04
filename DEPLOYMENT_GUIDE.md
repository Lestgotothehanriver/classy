# Classy 수동 배포 가이드

이 문서는 GitHub Actions 없이 VS Code의 Git Bash에서 Classy 운영 환경을 배포하는 절차다.

- 웹 사이트: `https://classystudy.com`
- Django API: `https://api.classystudy.com`
- EC2: `ubuntu@15.165.25.7`
- 웹 운영 경로: `/var/www/classy-web`
- Django 운영 경로: `/home/ubuntu/classy-aws`

## 0. 최초 1회: 로컬 SSH 변수 설정

VS Code Git Bash에서 실행한다. `KEY`에는 본인의 EC2 개인 키 파일 경로를 넣는다. 개인 키 파일 및 `.env` 파일은 GitHub나 채팅에 올리지 않는다.

```bash
export KEY="/c/Users/woals/Downloads/본인-ec2-key.pem"
export HOST="ubuntu@15.165.25.7"

test -r "$KEY" && echo "개인 키 확인 완료"
ssh -i "$KEY" "$HOST" "whoami"
```

마지막 명령에서 `ubuntu`가 출력되어야 한다. 이 Bash 창을 닫으면 `KEY`, `HOST` 변수는 다시 설정해야 한다.

## 1. GitHub에 소스 저장

배포 전 소스 이력을 GitHub에 남긴다. GitHub 푸시 자체는 운영 반영이 아니다.

```bash
cd /c/Users/woals/AndroidStudioProjects/classy-backend

git diff --check
git status --short
git add <변경한-파일-경로>
git commit -m "설명"
git push origin "$(git branch --show-current)"
```

## 2. 웹 사이트 배포

웹 수정(`web/` 하위 파일)만 있을 때 사용한다. 웹 정적 파일은 새 릴리스 폴더에 올린 후 `current` 링크만 교체한다. Django와 Nginx를 재시작하지 않는다.

### 2-1. 로컬에서 빌드하고 EC2 임시 폴더에 업로드

```bash
cd /c/Users/woals/AndroidStudioProjects/classy-backend/web

npm ci
npm run build

export RELEASE="web-$(date +%Y%m%d-%H%M%S)"
echo "$RELEASE"

scp -i "$KEY" -r dist "$HOST:/tmp/$RELEASE"
```

`scp`가 오류 없이 끝나면 업로드가 완료된 것이다. `RELEASE` 값은 다음 단계에서도 동일해야 한다.

### 2-2. EC2에서 웹 릴리스 등록 및 전환

```bash
ssh -i "$KEY" "$HOST"
```

EC2에 접속한 뒤 아래를 실행한다. `RELEASE`에는 2-1단계에서 출력된 값을 그대로 넣는다.

```bash
export RELEASE="web-YYYYMMDD-HHMMSS"

test -f "/tmp/$RELEASE/index.html" && echo "업로드 확인 완료"

export PREVIOUS="$(readlink -f /var/www/classy-web/current)"
echo "$PREVIOUS"

sudo install -d -m 755 "/var/www/classy-web/releases/$RELEASE"
sudo cp -a "/tmp/$RELEASE/." "/var/www/classy-web/releases/$RELEASE/"
test -f "/var/www/classy-web/releases/$RELEASE/index.html" && echo "릴리스 등록 완료"

sudo ln -s "/var/www/classy-web/releases/$RELEASE" "/var/www/classy-web/.current-$RELEASE"
sudo mv -Tf "/var/www/classy-web/.current-$RELEASE" "/var/www/classy-web/current"

readlink -f /var/www/classy-web/current
curl -fsSI https://classystudy.com
exit
```

`업로드 확인 완료` 또는 `릴리스 등록 완료`가 출력되지 않으면 다음 명령을 실행하지 않는다. 마지막 `readlink` 결과가 새 릴리스 경로여야 한다. 브라우저에서 `Ctrl + F5`로 새로고침해 화면을 확인한다.

### 2-3. 웹 롤백

2-2단계에서 출력해 둔 `PREVIOUS` 경로를 사용한다. EC2에서 실행한다.

```bash
export PREVIOUS="/var/www/classy-web/releases/이전-릴리스-이름"

test -f "$PREVIOUS/index.html"
sudo ln -s "$PREVIOUS" "/var/www/classy-web/.current-rollback"
sudo mv -Tf "/var/www/classy-web/.current-rollback" "/var/www/classy-web/current"
readlink -f /var/www/classy-web/current
```

## 3. Django 서버 배포

Python/Django 코드, `requirements.txt`, 템플릿, 관리자 기능, API 변경이 있을 때 사용한다. 서버의 `.env`, 미디어 파일, 운영 DB는 덮어쓰지 않는다.

### 3-1. 로컬 소스를 EC2로 업로드

로컬 Git Bash에서 실행한다. 이 명령은 소스를 압축해 전송하고 EC2의 기존 소스 경로에 풀어쓴다. 제외 목록은 운영 비밀값·가상환경·미디어·빌드 산출물을 보호한다.

```bash
cd /c/Users/woals/AndroidStudioProjects/classy-backend

tar -czf - \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='.aws' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.sqlite3' \
  --exclude='media' \
  --exclude='staticfiles' \
  --exclude='web/node_modules' \
  --exclude='web/dist' \
  . | ssh -i "$KEY" "$HOST" 'tar -xzf - -C /home/ubuntu/classy-aws'
```

### 3-2. EC2에서 마이그레이션·정적 파일·서비스 재시작

```bash
ssh -i "$KEY" "$HOST"
```

EC2에서 실행한다.

```bash
cd /home/ubuntu/classy-aws
export DJANGO_SETTINGS_MODULE=config.settings.aws

/home/ubuntu/classy_aws_venv/bin/pip install -r requirements.txt
/home/ubuntu/classy_aws_venv/bin/python manage.py check --deploy --fail-level WARNING
/home/ubuntu/classy_aws_venv/bin/python manage.py migrate --noinput
/home/ubuntu/classy_aws_venv/bin/python manage.py seed_reference_data
/home/ubuntu/classy_aws_venv/bin/python manage.py collectstatic --noinput

sudo systemctl restart classy
systemctl is-active classy nginx redis-server
curl -fsS https://api.classystudy.com/healthz/
exit
```

`active`, `active`, `active` 및 `{"status":"ok"}`가 확인되면 서버 배포가 완료된 것이다.

### 3-3. 서버 배포 전 주의사항

- 모델 변경이 없는 경우에도 `migrate --noinput`은 안전하게 적용할 마이그레이션이 없는지 확인한다.
- 마이그레이션은 데이터베이스 구조를 바꾸므로, 운영 데이터에 영향을 주는 변경이라면 먼저 백업·복구 계획을 확인한다.
- `/home/ubuntu/classy-aws/.env`는 절대 업로드하거나 출력하지 않는다.
- `prepare-host.sh`는 최초 서버 준비용이므로 일반 배포마다 실행하지 않는다.
- Django 코드 오류로 서비스가 시작되지 않으면 아래로 로그를 확인한다.

```bash
sudo journalctl -u classy -n 100 --no-pager
```

## 4. 자주 발생하는 문제

### `Could not resolve hostname classy-aws`

`classy-aws` SSH 별칭이 로컬 `~/.ssh/config`에 등록되지 않은 상태다. 이 문서의 `ssh -i "$KEY" "$HOST"` 및 `scp -i "$KEY" ... "$HOST:..."` 형식을 사용한다.

### `Identity file not accessible` 또는 `Permission denied (publickey)`

`KEY`가 비어 있거나 개인 키 경로가 잘못됐다. 아래로 경로만 확인한다.

```bash
echo "$KEY"
test -r "$KEY" && echo "개인 키 확인 완료"
```

### 웹 배포 후 이전 화면이 보임

배포 전환 여부를 EC2에서 확인한다.

```bash
readlink -f /var/www/classy-web/current
```

새 릴리스가 맞다면 브라우저에서 `Ctrl + F5`로 강력 새로고침한다.

## 5. 배포 대상 판단

| 변경 내용 | 실행할 배포 |
| --- | --- |
| `web/src/`의 React/CSS/정적 페이지 | 2. 웹 사이트 배포 |
| Django API, 모델, 관리자, `config/`, `requirements.txt` | 3. Django 서버 배포 |
| 웹과 Django를 모두 수정 | 2번 완료 후 3번 실행 |

현재 운영 웹은 GitHub에서 자동으로 `pull`하거나 빌드하지 않는다. `git push`는 이력 저장, 2번과 3번은 실제 운영 반영 절차다.
