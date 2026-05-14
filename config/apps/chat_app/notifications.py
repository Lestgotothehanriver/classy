import os
import json
import requests
from typing import Iterable, Dict, Any
from google.oauth2 import service_account
from google.auth.transport.requests import Request

from .models import UserDeviceToken

V1_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]

def _get_access_token() -> str:
    sa_path = os.getenv("FCM_SA_PATH")

    if not sa_path or not os.path.exists(sa_path):
        raise RuntimeError("FCM_SA_PATH not set or file not found")

    creds = service_account.Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    creds.refresh(Request())
    return creds.token  # Bearer 토큰

def push_to_users(user_ids: Iterable[int], title: str, body: str, username: str,
                  data: Dict[str, Any] = None) -> Dict[str, Any]:
    tokens = list(
        UserDeviceToken.objects.filter(user_id__in=user_ids, is_active=True)
        .values_list("token", flat=True)
    )
    if not tokens:
        return {"success": 0, "failure": 0, "detail": "no tokens"}

    project_id = os.getenv("FCM_PROJECT_ID")
    if not project_id:
        return {"success": 0, "failure": 0, "detail": "FCM_PROJECT_ID not set"}

    try:
        access_token = _get_access_token()
    except Exception as e:
        return {"success": 0, "failure": len(tokens), "detail": f"token_error: {e}"}

    url = V1_URL.format(project_id=project_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    # v1은 registration_ids(일괄 전송) 미지원 → 토큰별로 1건씩 전송
    ok, fail, errors = 0, 0, []
    for t in tokens:
        payload = {
            "message": {
                "token": t,
                "notification": {  # 앱이 알림 채널/권한 OK면 시스템 트레이로 뜸
                    "title": title,
                    "body": body,
                },
                "data": {  # 커스텀 필드들은 data에
                    "username": username,
                    **(data or {})
                },
                # 선택: 우선순위 높임
                "android": {"priority": "HIGH"},
                "apns": {"headers": {
                "apns-push-type": "alert",   # 사일런트면 background
                "apns-priority": "10"
            },},
            }
        }
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=5)
        if r.ok:
            ok += 1
        else:
            fail += 1
            errors.append({"token": t, "status": r.status_code, "body": r.text})

    return {"success": ok, "failure": fail, "errors": errors}
