"""
알림 helper 함수 모음.

View에서 직접 호출할 때는 이 모듈의 함수만 사용합니다.
Notification 생성 → notification/signals.py가 WS 브로드캐스트를 자동 처리합니다.
"""
import logging
from config.apps.notification.models import Notification

logger = logging.getLogger(__name__)


def _create(user, ntype, role, title, body, data=None):
    """Notification 생성 단일 진입점 (WebSocket 브로드캐스트만)."""
    Notification.objects.create(
        user=user,
        type=ntype,
        role=role,
        title=title,
        body=body,
        data=data or {},
    )
    logger.info(f"*** [Notify] type={ntype} → user={user.email} ***")


def _notify_with_push(user, ntype, role, title, body, data=None):
    """FCM 푸시 + 인앱 Notification 동시 발송 진입점.

    `_create()`는 WS 브로드캐스트만 하므로 앱 종료/백그라운드에서는 도달하지 않는다.
    앱 상태와 무관하게 반드시 전달돼야 하는 알림은 이 함수를 사용한다.
    (패턴 출처: notification/signals.py notify_instructor_status_change)

    FCM data에는 프론트 라우팅을 위해 `type`을 포함하지만, 인앱 Notification의
    `type`은 별도 컬럼이므로 data에는 넣지 않는다.
    """
    data = data or {}
    from config.apps.notification.fcm import send_push_to_user
    send_push_to_user(
        user=user,
        title=title,
        body=body,
        data={'type': ntype, **data},
    )
    _create(user, ntype, role, title, body, data)


# ─────────────────────────────────────────────────────────────────────────────
# 과외 요청 / 제안
# ─────────────────────────────────────────────────────────────────────────────

def notify_tutoring_request(room):
    """
    학생이 강사에게 과외를 요청했을 때 (StudentProposeToInstructorAPIView).
    → 강사에게 'tutoring_request' 알림.
    """
    student_name = room.student.user.user_name
    _create(
        user=room.instructor.user,
        ntype='tutoring_request',
        role='instructor',
        title=f'{student_name} 학생이 과외를 요청했습니다.',
        body='채팅방에서 내용을 확인해 보세요.',
        data={
            'room_id': str(room.id),
            'post_id': str(room.post_id),
            'student_id': str(room.student_id),
        },
    )


def notify_tutoring_proposal(room):
    """
    강사가 학생에게 과외를 제안했을 때 (InstructorProposeToStudentAPIView).
    → 학생에게 'tutoring_proposal' 알림.
    """
    instructor_name = room.instructor.user.user_name
    _create(
        user=room.student.user,
        ntype='tutoring_proposal',
        role='student',
        title=f'{instructor_name} 선생님이 과외를 제안했습니다.',
        body='채팅방에서 제안서를 확인해 보세요.',
        data={
            'room_id': str(room.id),
            'post_id': str(room.post_id),
            'instructor_id': str(room.instructor_id),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 과외 수락 (커운터파티 첫 답장 시 → consumers.py에서 호출)
# ─────────────────────────────────────────────────────────────────────────────

def notify_fee_payment_confirmed(resource):
    """
    관리자가 수수료 입금을 확인하고 PAID 처리해 계약이 ACTIVE로 전환됐을 때.
    → 계약 당사자인 강사와 학생 모두에게 성사 완료 알림(FCM + 인앱).
    """
    _notify_with_push(
        user=resource.instructor.user,
        ntype='tutoring_contract_confirmed',
        role='instructor',
        title='수수료 납부가 확인되었습니다.',
        body='수업 성사가 완료되었습니다. 과외 내역에서 확인해 보세요.',
        data={
            'resource_id': str(resource.id),
        },
    )
    _notify_with_push(
        user=resource.student.user,
        ntype='tutoring_contract_confirmed',
        role='student',
        title='과외 성사 등록이 완료되었습니다.',
        body='수업 관리에서 계약 세부 정보와 리뷰 작성을 확인해 보세요.',
        data={
            'resource_id': str(resource.id),
        },
    )


def notify_fee_payment_failed(resource):
    """
    관리자가 수수료 납부를 실패(FAILED) 처리했을 때.
    → 계약 당사자인 강사와 학생 모두에게 성사 실패 알림(FCM + 인앱).
    """
    for user, role in (
        (resource.instructor.user, 'instructor'),
        (resource.student.user, 'student'),
    ):
        _notify_with_push(
            user=user,
            ntype='tutoring_contract_failed',
            role=role,
            title='성사 등록이 실패했습니다.',
            body='수수료 납부 확인에 실패했어요. 수업 관리에서 다시 확인해 주세요.',
            data={
                'resource_id': str(resource.id),
            },
        )


def notify_registration_mismatched(registration):
    """
    양측이 입력한 수업 정보가 서로 달라 MISMATCHED로 전환됐을 때.
    → 강사와 학생 모두에게 정보 확인 요청 알림(FCM + 인앱).

    호출부에서 '이전 상태 ≠ MISMATCHED' edge-guard로 전환 시 1회만 호출한다.
    """
    resource = getattr(registration, 'resource', None)
    data = {'resource_id': str(resource.id)} if resource is not None else {}
    # TutoringRegistration.student / .instructor 는 프로필이 아니라 User FK.
    for user, role in (
        (registration.instructor, 'instructor'),
        (registration.student, 'student'),
    ):
        _notify_with_push(
            user=user,
            ntype='tutoring_contract_mismatch',
            role=role,
            title='성사 정보가 일치하지 않습니다.',
            body='상대방과 입력한 수업 정보가 달라요. 수업 관리에서 다시 확인해 주세요.',
            data=data,
        )


def notify_tutoring_accept(room, acceptor):
    """
    커운터파티가 첫 답장을 보내 과외를 수락한 순간.
    알림 수신자 = 제안자 (room.initiated_by).

    acceptor: 수락한 유저 (커운터파티)
    """
    initiator = room.initiated_by
    if not initiator:
        return

    acceptor_name = getattr(acceptor, 'user_name', None) or acceptor.username
    _create(
        user=initiator,
        ntype='tutoring_accept',
        role='any',
        title=f'{acceptor_name}님이 과외를 수락했습니다.',
        body='지금부터 자유롭게 대화하세요!',
        data={
            'room_id': str(room.id),
            'acceptor_id': str(acceptor.id),
        },
    )
