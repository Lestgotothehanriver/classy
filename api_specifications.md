# Classy API Endpoints Specification

이 문서는 Classy 프로젝트 내 각 Django 앱별 API 엔드포인트의 명세서입니다.

---

## 1. Accounts App (계정 및 인증)

| 기능 | Method | URL | Param | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| 학생 회원가입 | `POST` | `/accounts/signup/student/` | **[Body (JSON)]**<br>- `email` (str, 필수)<br>- `password` (str, 필수)<br>- `user_name` (str, 필수)<br>- `phone` (str, 필수)<br>- `studentsubject` (list[int], 선택) | 학생용 회원가입을 처리하고 자동 로그인 토큰을 발급합니다. |
| 학생 프로필 수정 | `PUT`<br>`PATCH` | `/accounts/signup/student/` | **[Body (JSON)]**<br>- `user_name` (str, 선택) 등 수정 대상 정보 | 로그인한 학생의 프로필 정보를 수정합니다. |
| 강사 회원가입 | `POST` | `/accounts/signup/instructor/` | **[Body (Multipart)]**<br>- `email` (str, 필수)<br>- `password` (str, 필수)<br>- `user_name` (str, 필수)<br>- `phone` (str, 필수)<br>- `university` (str, 필수)<br>- `department` (str, 선택)<br>- `pending_file` (file, 필수) 등 | 강사 회원가입을 처리합니다. 학력/경력 인증을 위한 서류 제출이 필수입니다. |
| 강사 프로필 수정 | `PUT`<br>`PATCH` | `/accounts/signup/instructor/` | **[Body (Multipart)]**<br>- `university` (str, 선택)<br>- `department` (str, 선택) 등 수정 대상 정보 | 로그인한 강사의 프로필 정보를 수정합니다. |
| 강사 재심사 요청 | `POST` | `/accounts/signup/instructor/retry/` | **[Body (Multipart)]**<br>- `email` (str, 필수)<br>- `pending_file` (file, 필수)<br>- `university`, `department` 등 (선택)<br>- `fcm_token`, `platform` (선택) | 강사 승인이 거절(`SUSPENDED`)된 상태에서 인증 서류를 보강하여 재인증을 요청합니다. |
| 로그인 | `POST` | `/accounts/login/` | **[Body (JSON)]**<br>- `email` (str, 필수)<br>- `password` (str, 필수) | 이메일과 비밀번호로 로그인하여 인증용 토큰과 사용 가능한 역할군 목록을 획득합니다. |
| 닉네임 중복 확인 | `GET` | `/accounts/check-username/` | **[Query]**<br>- `user_name` (str, 필수) | 회원가입 또는 정보 변경 시 닉네임 중복 여부를 조회합니다. (본인 닉네임 제외) |
| 이메일 중복 확인 | `GET` | `/accounts/check-email/` | **[Query]**<br>- `email` (str, 필수) | 회원가입 또는 정보 변경 시 이메일 중복 여부를 조회합니다. (본인 이메일 제외) |
| 휴대전화 가입 체크 | `GET` | `/accounts/check-phone/` | **[Query]**<br>- `phone` (str, 필수) | 입력한 번호로 가입된 계정이 존재하는지, 그리고 추가 가입 가능한 역할이 있는지 확인합니다. |
| 역할 추가 | `POST` | `/accounts/add-role/` | **[Body (Multipart)]**<br>- `phone` (str, 필수)<br>- `password` (str, 필수)<br>- `role` (str, student/instructor, 필수)<br>- `studentsubject` 등 역할별 추가 필드 | 기존 가입된 계정에 추가적인 학생 또는 강사 역할의 프로필을 추가로 등록합니다. |
| 로그아웃 | `POST` | `/accounts/logout/` | 없음 | 로그인 토큰을 만료시키고, 기기 푸시 알림 수신 상태를 비활성화합니다. |
| 회원 탈퇴 | `POST` | `/accounts/withdraw/` | **[Body (JSON)]**<br>- `reason` (str, 선택)<br>- `reason_detail` (str, 선택) | 계정을 비활성화(Soft delete)하고 토큰 및 푸시 설정을 초기화합니다. |
| 내 프로필 조회 | `GET` | `/accounts/me/` | 없음 | 로그인한 유저 본인의 상세 프로필 정보를 조회합니다. |
| 내 프로필 수정 | `PATCH` | `/accounts/me/` | **[Body (JSON)]**<br>- `user_name` (str, 선택)<br>- `phone` (str, 선택)<br>- `region` (str, 선택)<br>- `field` (str, 선택) | 내 기본 정보(닉네임, 번호, 거주 지역 등) 공통 필드를 수정합니다. |
| 프로필 이미지 변경 | `PATCH` | `/accounts/me/image/` | **[Body (Multipart)]**<br>- `profile_image` (file, 필수) | 프로필 이미지를 새로 등록하거나 변경합니다. |
| 번호 변경 인증 요청 | `POST` | `/accounts/me/phone/request/` | **[Body (JSON)]**<br>- `phone` (str, 필수) | 휴대전화 번호 변경을 위해 새로운 번호로 6자리 SMS 인증번호 전송을 요청합니다. |
| 번호 변경 인증 확인 | `POST` | `/accounts/me/phone/verify/` | **[Body (JSON)]**<br>- `phone` (str, 필수)<br>- `code` (str, 필수) | 인증번호 대조가 성공하면 유저의 휴대전화 번호를 최종 변경합니다. |
| SMS 인증번호 발송 | `POST` | `/accounts/send-auth-sms/` | **[Body (JSON)]**<br>- `phone_number` (str, 필수) | 입력한 번호로 6자리 SMS 인증번호를 발송합니다. |
| SMS 인증번호 확인 | `POST` | `/accounts/verify-auth-sms/` | **[Body (JSON)]**<br>- `phone_number` (str, 필수)<br>- `code` (str, 필수) | 발송된 인증번호를 검증하여 전화번호 인증을 완료합니다. |
| 유저 공개 프로필 조회 | `GET` | `/accounts/user/<int:pk>/` | **[Path]**<br>- `pk` (int, 필수) | 특정 사용자의 공개 프로필 및 학적, 활동 과목 정보를 조회합니다. |
| 전체 과목 조회 | `GET` | `/accounts/subjects/` | 없음 | 시스템 내 전체 교과 과목 리스트를 순서대로 조회합니다. |
| 프로필 확인 | `GET` | `/accounts/profile-check/` | 없음 | 로그인한 사용자의 학생/강사 프로필 보유 여부(사용 가능한 역할군 목록 및 상태, 최근 로그인 일시)와 토큰 정보를 확인합니다. |
| 역할 추가 | `POST` | `/accounts/role-add/` | **[Query]**<br>- `role` ('student'/'instructor', 필수)<br>**[Body (JSON)]**<br>- `studentsubject` (list[int], 학생 추가 시 선택)<br>- `university` (str, 강사 추가 시 필수)<br>- `department` (str, 강사 추가 시 선택)<br>- `instruction` (str, 강사 추가 시 선택)<br>- `student_number` (str, 강사 추가 시 선택)<br>- `instructorsubject` (str/list, 강사 추가 시 선택) | 로그인한 유저를 기준으로 학생 또는 강사 역할을 새로 추가하고, 업데이트된 역할 목록과 토큰 정보를 반환합니다. |

---

## 2. Pending App (강사 자격 서류 제출)

| 기능 | Method | URL | Param | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| 인증 서류 최초 제출 | `POST` | `/pending/` | **[Body (Multipart)]**<br>- `pending_file` (file, 선택)<br>- `files` (file, 선택, 다중 가능) | 로그인한 강사 회원이 자신의 학적/자격 인증 서류를 최초로 제출하여 심사를 요청합니다. |
| 인증 서류 재제출 | `POST` | `/pending/upload/` | **[Body (Multipart)]**<br>- `files` (file, 필수, 다중 가능) | 기존에 업로드된 자격 서류를 삭제하고 새로운 자격 서류로 교체하여 인증 대기 상태로 재심사를 신청합니다. |

---

## 3. Tutoring App (과외 매칭 및 소개)

| 기능 | Method | URL | Param | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| 강사 목록 조회 | `GET` | `/tutoring/instructors/` | **[Query]**<br>- `ordering` ('latest'/'likes', 선택)<br>- `liked` (bool, 선택)<br>- `subject` (콤마 구분 ID, 선택)<br>- `region` (콤마 구분 ID, 선택)<br>- `cost` (최대 수업료, 선택)<br>- `method` ('ONLINE'/'OFFLINE', 선택)<br>- `sex` ('M'/'F', 선택)<br>- `age` (나이 범위, 선택)<br>- `university` (출신 대학교, 선택)<br>- `department` (학과명, 선택)<br>- `student_id` (학번/사번 필터, 선택)<br>- `search` (통합 검색어, 선택) | 승인 완료된 강사 목록을 다양한 조건에 맞추어 필터링 조회합니다. (차단 유저 제외) |
| 강사 상세 프로필 | `GET` | `/tutoring/instructors/<int:pk>/` | **[Path]**<br>- `pk` (int, 강사 ID) | 특정 강사의 상세 프로필 정보를 조회합니다. |
| 강사 과외 소개 상세 | `GET` | `/tutoring/instructors/<int:instructor_id>/info/` | **[Path]**<br>- `instructor_id` (int, 강사 ID) | 강사가 설정한 과외 소개 탭 정보(자기소개, 평점 요약, 정산 랭킹 등)를 상세 조회합니다. (로그인한 학생 유저 기준 해당 강사와의 채팅방 생성 여부 `has_chat_room`: bool 포함) |
| 강사 리뷰 목록 | `GET` | `/tutoring/instructors/<int:instructor_id>/reviews/` | **[Path]**<br>- `instructor_id` (int, 강사 ID) | 특정 강사가 학생들에게서 받은 모든 리뷰 목록을 최신순으로 조회합니다. |
| 과외 구인 공고 목록 | `GET` | `/tutoring/posts/` | **[Query]**<br>- `ordering` ('latest'/'likes', 선택)<br>- `subject` (콤마 구분 ID, 선택)<br>- `region` (지역 ID, 선택)<br>- `cost` (최대 요금, 선택)<br>- `method` ('ONLINE'/'OFFLINE', 선택)<br>- `sex` ('M'/'F', 선택)<br>- `grade` (학년 코드, 선택)<br>- `min_rating` (최소 평점, 선택)<br>- `search` (통합 검색어, 선택) | 학생들이 등록한 활성화된 과외 구인 공고 목록을 필터 조건에 맞춰 조회합니다. (차단 유저 제외) |
| 과외 구인 공고 상세 | `GET` | `/tutoring/posts/<int:pk>/` | **[Path]**<br>- `pk` (int, 공고 ID) | 특정 과외 구인 공고의 상세 내역을 조회합니다. (조회수 1 증가 처리 포함, 로그인한 강사 유저 기준 공고 작성 학생과의 채팅방 생성 여부 `has_chat_room`: bool 포함) |
| 과외 구인 공고 작성 | `POST` | `/tutoring/posts/write/` | **[Body (JSON)]**<br>- `title` (str, 필수)<br>- `cost` (int, 필수)<br>- `method` ('ONLINE'/'OFFLINE', 필수)<br>- `subject_ids` (list[int], 선택)<br>- `region_id` (int, 선택)<br>- `grade` (str, 선택)<br>- `sex` (str, 선택)<br>- `situation` (str, 선택)<br>- `etc` (str, 선택) | 학생 회원이 새로운 과외 구인 공고를 작성합니다. |
| 과외 구인 공고 수정/삭제 | `PUT`<br>`PATCH`<br>`DELETE` | `/tutoring/posts/write/<int:pk>/` | **[Path]**<br>- `pk` (int, 공고 ID)<br>**[Body (JSON)]** (수정 시)<br>- 수정 대상 정보 | 자신이 작성한 과외 구인 공고의 내용을 변경하거나 삭제합니다. |
| 내 작성 공고 목록 | `GET` | `/tutoring/my-posts/` | 없음 | 학생 본인이 작성한 전체 과외 구인 공고 목록(비활성 포함)을 최신순으로 가져옵니다. |
| 강사 리뷰 작성 | `POST` | `/tutoring/reviews/instructor/` | **[Body (JSON)]**<br>- `instructor_id` (int, 필수)<br>- `rating` (int, 1~5, 필수)<br>- `content` (str, 필수) | 학생 회원이 특정 강사에 대해 별점과 후기를 작성합니다. |
| 강사 리뷰 수정/삭제 | `PUT`<br>`PATCH`<br>`DELETE` | `/tutoring/reviews/instructor/<int:pk>/` | **[Path]**<br>- `pk` (int, 리뷰 ID)<br>**[Body (JSON)]** (수정 시) | 본인이 작성한 강사 리뷰를 수정하거나 삭제합니다. |
| 학생 리뷰 작성 | `POST` | `/tutoring/reviews/student/` | **[Body (JSON)]**<br>- `student_id` (int, 필수)<br>- `rating` (int, 1~5, 필수)<br>- `content` (str, 필수) | 강사 회원이 특정 학생에 대해 별점과 후기를 작성합니다. |
| 학생 리뷰 수정/삭제 | `PUT`<br>`PATCH`<br>`DELETE` | `/tutoring/reviews/student/<int:pk>/` | **[Path]**<br>- `pk` (int, 리뷰 ID)<br>**[Body (JSON)]** (수정 시) | 본인이 작성한 학생 리뷰를 수정하거나 삭제합니다. |
| 특정 학생 리뷰 목록 | `GET` | `/tutoring/students/<int:student_id>/reviews/` | **[Path]**<br>- `student_id` (int, 학생 ID) | 특정 학생에 대해 다른 강사들이 작성한 리뷰 목록을 전체 조회합니다. |
| 강사 과외 정보 등록 | `POST` | `/tutoring/instructor-info/` | **[Body (JSON)]**<br>- `description` (str, 선택)<br>- `method` (str, 선택)<br>- `cost` (int, 선택)<br>- `subject_ids` (list[int], 선택)<br>- `region_ids` (list[int], 선택) | 강사 본인의 상세 과외 소개 정보를 새로 등록하거나 덮어써서 업데이트합니다. |
| 강사 과외 정보 상세 조회 | `GET` | `/tutoring/instructor-info/<int:pk>/` | **[Path]**<br>- `pk` (int, 정보 ID) | 강사 과외 정보의 상세 정보를 가져옵니다. |
| 강사 과외 정보 수정/삭제 | `PUT`<br>`PATCH`<br>`DELETE` | `/tutoring/instructor-info/<int:pk>/` | **[Path]**<br>- `pk` (int, 정보 ID)<br>**[Body (JSON)]** (수정 시) | 본인의 과외 소개 정보 내용을 변경하거나 완전히 삭제합니다. |
| 내 과외 정보 조회 | `GET` | `/tutoring/instructor-info/mine/` | 없음 | 로그인한 강사 본인의 과외 소개 정보를 원샷 조회합니다. (없을 시 `204 No Content`) |
| 학생 → 강사 제안 신청 | `POST` | `/tutoring/propose-to-instructor/` | **[Body (JSON)]**<br>- `instructor_id` (int, 필수)<br>- `post_id` (int, 필수) | 학생이 강사에게 과외 제안을 발송하여 채팅방을 신규 개설하고 자동 첫 대화를 엽니다. |
| 학생 → 강사 제안 취소 | `DELETE` | `/tutoring/propose-to-instructor/` | **[Body / Query]**<br>- `instructor_id` (int, 필수)<br>- `post_id` (int, 필수) | 발송했던 강사 제안을 취소하고 개설되었던 채팅방을 해제합니다. |
| 강사 → 학생 역제안 | `POST` | `/tutoring/propose-to-student/` | **[Body (JSON)]**<br>- `post_id` (int, 필수)<br>- `message` (str, 선택) | 강사가 학생의 공고에 역제안서와 1:1 대화방을 개설합니다. |
| 강사 → 학생 역제안 취소 | `DELETE` | `/tutoring/propose-to-student/` | **[Body / Query]**<br>- `post_id` (int, 필수) | 발송했던 학생 역제안 내역 및 대화방을 철회합니다. |
| 과외 제안서 목록 조회 | `GET` | `/tutoring/proposals/` | 없음 | 로그인한 사용자 본인과 관련된 모든 과외 제안서 내역을 조회합니다. |
| 과외 제안서 상세 조회 | `GET` | `/tutoring/proposals/<int:pk>/` | **[Path]**<br>- `pk` (int, 제안서 ID) | 특정 과외 제안서의 상세 내역을 가져옵니다. |
| 과외 계약 리소스 목록 | `GET` | `/tutoring/resources/` | 없음 | 본인이 참여한 모든 과외 수업 계약/지불 리소스 목록을 조회합니다. |
| 채팅방 성사 등록 조회 | `GET` | `/tutoring/resources/chatrooms/<int:chat_room_id>/` | **[Path]**<br>- `chat_room_id` (int, 채팅방 ID) | 공통 정보, 내 제출 정보, 양측 제출 여부, 일치 검증 상태를 조회합니다. 상대방의 수업 유형과 수업료는 반환하지 않습니다. |
| 내 성사 정보 등록/수정 | `PUT` | `/tutoring/resources/chatrooms/<int:chat_room_id>/my-registration/` | **[공통]**<br>- `subject` (str)<br>- `subjectIds` (list[int], 1~3개)<br>- `startDate` (date)<br>- `classType` (`REGULAR`/`SHORT_TERM`)<br>- `firstMonthFee` (int)<br>**[학생 JSON]**<br>- `paybackAccount.bankCode`<br>- `paybackAccount.accountNumber`<br>- `paybackAccount.accountHolder`<br>**[강사 Multipart]**<br>- `feeConfirmationFiles` (file, 1개 이상, 다중 가능) | 채팅방 참여자로 역할을 판별하여 학생/강사 제출을 독립 저장합니다. 학생은 페이백 계좌를, 강사는 개인 계좌 입금 증빙을 제출합니다. 강사 제출 시 정규 15%, 단기 7% 수수료를 계산하며 가상계좌는 발급하지 않습니다. |
| 수수료 입금 상태 조회 | `GET` | `/tutoring/resources/<int:registration_id>/commission-payment/` | **[Path]**<br>- `registration_id` (int, 성사 등록 ID) | 개인 계좌 수동 입금의 청구 금액과 운영팀 확인 상태를 조회합니다. |
| 과외 계약 리소스 생성(레거시) | `POST` | `/tutoring/resources/` | **[Body (Multipart), 강사 전용]**<br>- `student` (int, 필수)<br>- `instructor` (int, 필수)<br>- `start_date` (date)<br>- `class_type` (`단기 수업`/`장기 수업`)<br>- `subject` (int, 최대 3개)<br>- `first_month_fee` (int, 필수)<br>- `fee_confirmation_file` (file, 필수, 다중 가능) | 이전 앱 버전 호환용입니다. 신규 앱은 채팅방 단위 통합 API를 사용합니다. |
| 과외 계약 리소스 상세 | `GET` | `/tutoring/resources/<int:pk>/` | **[Path]**<br>- `pk` (int, 리소스 ID) | 특정 과외 계약 리소스의 상세 입금 상태 및 첨부파일들을 조회합니다. |
| 강사 입금 완료 접수 | `POST` | `/tutoring/resources/<int:pk>/confirm-payment/` | **[Path]**<br>- `pk` (int, 리소스 ID) | 증빙이 첨부된 계약을 `AWAITING_CONFIRMATION`으로 변경합니다. 이후 운영팀이 Django admin에서 `PAID` 또는 `FAILED`로 수동 처리합니다. |
| 강사 찜하기 토글 | `POST` | `/tutoring/instructors/<int:instructor_id>/like/` | **[Path]**<br>- `instructor_id` (int, 필수) | 학생 회원이 강사를 찜(좋아요) 목록에 추가하거나 제외합니다. |
| 과외 공고 찜하기 토글 | `POST` | `/tutoring/posts/<int:post_id>/like/` | **[Path]**<br>- `post_id` (int, 필수) | 강사 회원이 학생 구인 공고를 찜 목록에 추가하거나 제외합니다. |

---

## 4. Cash App (자산, 충전 및 환불)

| 기능 | Method | URL | Param | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| 정산 계좌 조회 | `GET` | `/cash/account/` | 없음 | 강사 본인의 수익 정산용 등록 은행 계좌 정보를 가져옵니다. |
| 정산 계좌 등록/수정 | `POST` | `/cash/account/` | **[Body (JSON)]**<br>- `bank` (str, 필수)<br>- `account_number` (str, 필수)<br>- `account_holder` (str, 필수) | 강사의 수익 정산용 계좌번호 및 예금주 정보를 신규 등록하거나 덮어씁니다. |
| 인앱 결제 캐시 충전 | `POST` | `/cash/purchase/` | **[Body (JSON)]**<br>- `platform` ('apple'/'google', 필수)<br>- `product_id` (str, 필수)<br>- `receipt_data` (str, iOS 필수)<br>- `purchase_token` (str, AOS 필수) | App Store 또는 Play Store 영수증 검증 후 실물 캐시를 계정에 충전하고 내역을 남깁니다. |
| 프로모션 쿠폰 충전 | `POST` | `/cash/coupons/redeem/` | **[Body (JSON)]**<br>- `code` (str, 필수) | 캐시가 포함된 유효한 프로모션 쿠폰을 사용하여 캐시를 적립합니다. |
| Apple 환불 웹훅 | `POST` | `/cash/webhook/apple/` | **[Body (JSON)]**<br>- `signedPayload` (str, 필수 JWS) | Apple 앱스토어 서버 알림을 수신하여 환불 건에 대해 사용자 계정 캐시를 차감 처리합니다. (인증 미필요) |
| Google 환불 웹훅 | `POST` | `/cash/webhook/google/` | **[Body (JSON)]**<br>- `message` (dict, 필수 Pub/Sub) | Google Play Real-time Developer Notifications를 수신하여 환불 완료 건에 대해 캐시를 차감합니다. (인증 미필요) |
| VOD 강의 대여 | `POST` | `/cash/rentals/` | **[Body (JSON)]**<br>- `lecture_id` (int, 필수) | 보유하고 있는 캐시를 사용하여 특정 동영상 강의의 대여 기간 시청 권한을 구매합니다. |
| 강의 대여 취소/환불 | `POST` | `/cash/rentals/<int:pk>/cancel/` | **[Path]**<br>- `pk` (int, 대여 내역 ID) | 결제(대여) 후 7일 이내의 미사용 강의에 대해 대여를 취소하고 캐시를 반환받습니다. |
| 캐시 충전 내역 목록 | `GET` | `/cash/purchase-history/` | 없음 | 본인의 인앱 결제를 통한 전체 캐시 충전 이력을 최신순으로 가져옵니다. |
| 강의 대여 내역 목록 | `GET` | `/cash/rental-history/` | 없음 | 본인이 대여한 강의 구매 내역 리스트(7일 내 환불 취소 가능 상태 정보 포함)를 가져옵니다. |

---

## 5. Lecture App (VOD 동영상 강의 및 댓글)

| 기능 | Method | URL | Param | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| 동영상 강의 업로드 | `POST` | `/lectures/write/` | **[Body (Multipart)]**<br>- `title` (str, 필수)<br>- `content` (str, 필수)<br>- `video` (file, 필수)<br>- `thumbnail` (file, 필수)<br>- `price` (int, 필수)<br>- `is_preview` (bool, 선택) | 강사 회원이 새로운 VOD 동영상 강의를 업로드합니다. 프리뷰 강의(is_preview=True) 업로드 시 기존 프리뷰는 트랜잭션 하에서 원자적으로 자동 삭제되어 강사당 1개의 프리뷰 영상만 유지됩니다. |
| 동영상 강의 수정/삭제 | `PUT`<br>`PATCH`<br>`DELETE` | `/lectures/write/<int:pk>/` | **[Path]**<br>- `pk` (int, 강의 ID)<br>**[Body (Multipart)]** (수정 시) | 자신이 업로드한 VOD 강의의 메타데이터 및 파일을 수정하거나 삭제 처리합니다. 본인이 작성한 강의만 조작할 수 있습니다. |
| 강의 판매 중지 | `POST` | `/lectures/write/<int:pk>/stop-sales/` | **[Path]**<br>- `pk` (int, 강의 ID) | 특정 강의의 판매 상태를 중지(is_active=False)하여 검색 및 전체 목록 노출을 중단합니다. |
| 판매 중 강의 목록 | `GET` | `/lectures/` | **[Query]**<br>- `q` (str, 선택)<br>- `subject` (str, 선택)<br>- `max_price` (int, 선택)<br>- `video_length` (str, 선택)<br>- `region` (str, 선택)<br>- `university` (str, 선택)<br>- `department` (str, 선택)<br>- `student_number` (str, 선택)<br>- `liked` (bool, 선택)<br>- `is_tutoring` (bool, 선택)<br>- `instructor` (str, 선택) | 판매 중인 전체 VOD 동영상 강의 목록을 다중 키워드, 과목, 가격, 영상 길이 범위, 강사의 지역 및 학적 등의 복합 조건으로 필터링하여 반환합니다. 로그인한 학생 유저의 경우 찜 여부(is_liked)를 동적 계산하여 제공합니다. |
| 강의 상세 페이지 조회 | `GET` | `/lectures/<int:pk>/` | **[Path]**<br>- `pk` (int, 강의 ID) | 특정 강의의 상세 정보를 조회합니다. 강의 기본 정보(LectureDetailSerializer), 로그인한 유저의 대여 상태, 강사의 무료 프리뷰 영상, 연관 과목 기반 추천 강의 10개를 종합 반환하며 조회수가 1 증가합니다. |
| 강의 스트리밍 URL | `GET` | `/lectures/<int:pk>/stream/` | **[Path]**<br>- `pk` (int, 강의 ID) | 로그인한 유저의 대여 권한(LectureRentalHistory)을 검증하여 유효한 대여 상태이거나, 프리뷰 강의 또는 강사 본인의 강의인 경우 시청용 동영상 스트리밍 주소를 반환합니다. |
| 강의 찜하기 토글 | `POST` | `/lectures/<int:pk>/like/` | **[Path]**<br>- `pk` (int, 강의 ID) | 학생 회원이 동영상 강의를 찜 목록에 등록하거나 취소(토글)합니다. 강사 계정 등 학생 프로필이 없는 경우 404를 반환합니다. |
| 강의 댓글 목록 조회 | `GET` | `/lectures/<int:lecture_id>/comments/` | **[Path]**<br>- `lecture_id` (int, 강의 ID) | 특정 강의에 작성된 최상위 부모 댓글 목록을 최신순 조회하며, 대댓글은 replies 필드 아래 중첩 반환합니다. 차단한 유저의 댓글은 제외됩니다. |
| 강의 댓글 작성 | `POST` | `/lectures/<int:lecture_id>/comments/` | **[Path]**<br>- `lecture_id` (int, 강의 ID)<br>**[Body (JSON)]**<br>- `content` (str, 필수)<br>- `parent` (int, 선택)<br>- `referenced_person` (int, 선택) | VOD 강의에 새로운 댓글 또는 대댓글을 작성합니다. 무료/프리뷰 강의는 로그인 사용자에게 허용하고, 유료 강의는 강의 소유자 또는 유효 대여자만 작성할 수 있습니다. |
| 댓글 수정/삭제 | `PATCH`<br>`DELETE` | `/lectures/comments/<int:pk>/` | **[Path]**<br>- `pk` (int, 댓글 ID)<br>**[Body (JSON)]** (PATCH 시)<br>- `content` (str, 필수) | 본인이 작성한 댓글만 변경(PATCH)하거나 삭제(DELETE)할 수 있습니다. 단, 유료 강의 댓글은 현재 강의 소유자 또는 유효 대여자 권한도 유지되어야 합니다. |
| 최근 검색어 조회 | `GET` | `/lectures/search-history/` | 없음 | 로그인한 학생 회원의 최근 검색 키워드 내역을 최대 5개까지 최신순으로 조회합니다. 학생 프로필이 없으면 빈 목록이 반환됩니다. |
| 최근 검색어 추가 저장 | `POST` | `/lectures/search-history/` | **[Body (JSON)]**<br>- `query` (str, 필수) | 검색한 단어를 최근 검색 이력에 저장합니다. 저장 후 최대 보관 개수인 5개를 초과하면 가장 오래된 기록을 자동으로 삭제(FIFO)합니다. |
| 최근 검색어 개별 삭제 | `DELETE` | `/lectures/search-history/<int:pk>/` | **[Path]**<br>- `pk` (int, 검색어 기록 ID) | 본인의 최근 검색어 이력 중 특정 항목 하나를 개별 삭제합니다. |

---

## 6. Report App (신고 및 1:1 고객 문의)

| 기능 | Method | URL | Param | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| 사용자 신고 | `POST` | `/report/create/` | **[Body (JSON)]**<br>- `reported_user` (int, 필수)<br>- `choices` (list[str], 필수)<br>- `evidence_image` (file/null, 선택) | 인증된 사용자가 부적절한 사용자 등을 신고합니다. |
| 1:1 고객센터 문의 | `POST` | `/report/inquiry/` | **[Body (JSON)]**<br>- `title` (str, 필수)<br>- `content` (str, 필수) | 인증된 사용자가 고객센터에 1:1 문의를 남깁니다. |

---

## 7. Main App (메인화면 대시보드)

| 기능 | Method | URL | Param | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| 학생 메인 대시보드 | `GET` | `/main/student/` | 없음 | 학생 회원의 거주 지역 맞춤 추천 강사 3인을 랜덤하게 추출하여 제공합니다. |
| 강사 메인 대시보드 | `GET` | `/main/instructor/` | 없음 | 강사 회원의 지난달 정산 순위, 이번 달의 누적 VOD 판매 수익 캐시, 지역 추천 학생 3인을 조회합니다. |

---

## 8. Mypage App (마이페이지 개인이력)

| 기능 | Method | URL | Param | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| 학생 대여 중 강의 목록 | `GET` | `/mypage/student/rented-lectures/` | 없음 | 로그인한 학생 회원이 현재 대여 중으로 시청 가능한 VOD 강의 목록을 조회합니다. |
| 학생 찜한 강의 목록 | `GET` | `/mypage/student/liked-lectures/` | 없음 | 학생 회원이 찜(좋아요) 한 동영상 강의 목록을 조회합니다. |
| 강사 업로드 강의 목록 | `GET` | `/mypage/instructor/uploaded-lectures/` | 없음 | 강사 회원이 본인이 직접 업로드한 강의 영상 목록을 조회합니다. |
| 강사 정산 신청 | `POST` | `/mypage/instructor/request-settlement/` | 없음 | 대여 판매 이력 중 정산되지 않은 누적 수익에 대한 정산 지급 신청(`PENDING`)을 접수합니다. |
| 강사 정산 정보 요약 | `GET` | `/mypage/instructor/settlement-info/` | 없음 | 총 누적 수익, 완료된 정산액, 대기 상태 금액, 정산 가능액 및 계좌 연동 정보를 통합 조회합니다. |

---

## 9. Block App (차단 관리)

| 기능 | Method | URL | Param | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| 차단 사용자 목록 조회 | `GET` | `/blocks/` | 없음 | 로그인한 사용자가 차단 등록한 상대 유저 목록을 반환합니다. |
| 차단 사용자 추가 | `POST` | `/blocks/` | **[Body (JSON)]**<br>- `blocked_user` (int, 필수 ID) | 특정 사용자를 차단 상대 목록에 새로 추가합니다. (채팅방 배제 및 차단 상대 리뷰 필터링 연동) |
| 차단 사용자 해제 | `DELETE` | `/blocks/<int:pk>/` | **[Path]**<br>- `pk` (int, 차단 기록 고유 ID) | 등록된 차단 정보를 해제(삭제)합니다. |

---

## 10. Chat App (1:1 과외 문의 채팅)

| 기능 | Method | URL | Param | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| 참여 채팅방 목록 조회 | `GET` | `/chatrooms/` | **[Query]**<br>- `role` ('student'/'instructor', 선택) | 본인이 참여자로 있는 전체 활성 채팅방 목록을 반환합니다. (차단 유저 방은 제외) |
| 채팅방 상세 조회 | `GET` | `/chatrooms/<int:pk>/` | **[Path]**<br>- `pk` (int, 채팅방 ID) | 특정 채팅방 정보 및 이전 메시지 목록 데이터를 종합 조회합니다. |
| 메시지 전송 | `POST` | `/chatrooms/<int:pk>/message/` | **[Path]**<br>- `pk` (int, 채팅방 ID)<br>**[Body (JSON)]**<br>- `text` (str, 선택)<br>- `img_ids` (list[int], 선택) | 해당 채팅방에 텍스트 또는 사전에 업로드한 이미지 ID들을 첨부하여 전송합니다. |
| 메시지 읽음 처리 | `POST` | `/chatrooms/<int:pk>/read/<int:msg_id>/` | **[Path]**<br>- `pk` (int, 채팅방 ID)<br>- `msg_id` (int, 메시지 ID) | 특정 채팅 메시지의 읽은 사람 목록에 본인을 추가하고 총 읽음 수 정보를 반환합니다. |
| 채팅방 나가기(삭제) | `DELETE` | `/chatrooms/<int:pk>/out/` | **[Path]**<br>- `pk` (int, 채팅방 ID) | 참여 중인 채팅방을 나가고 방을 완전히 삭제 처리합니다. |
| 채팅방 찜하기 토글 | `POST` | `/chatrooms/<int:pk>/like/` | **[Path]**<br>- `pk` (int, 채팅방 ID) | 특정 채팅방을 찜(즐겨찾기)하거나 취소 상태로 토글합니다. |
| 채팅방 알림 음소거 토글 | `POST` | `/chatrooms/<int:pk>/mute/` | **[Path]**<br>- `pk` (int, 채팅방 ID) | 특정 채팅방에 대한 신규 메시지 수신 알림 음소거 여부를 토글합니다. |
| 이미지 사전 업로드 | `POST` | `/images/` | **[Body (Multipart)]**<br>- `images` (file, 필수, 다중 가능) | 채팅 전송을 위해 이미지 파일을 미리 업로드하여 이후 메시지 전송 시 매핑할 이미지 ID들을 획득합니다. |
| 채팅 독립 알림 토글 | `PUT` | `/chat-notification/` | 없음 | 다른 시스템 푸시와 무관하게 순수 채팅 알림 상태(`is_chat_active`)만 토글 변경합니다. |

---

## 11. Notification App (시스템 푸시 및 매칭 알림)

| 기능 | Method | URL | Param | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| 내 알림 내역 조회 | `GET` | `/notification/` | **[Query]**<br>- `role` ('student'/'instructor', 선택) | 본인이 수신한 전체 알림 목록을 확인합니다. 특정 역할별 필터링도 지원합니다. |
| 읽은 알림 일괄 삭제 | `DELETE` | `/notification/` | 없음 | 수신된 알림 중 이미 읽음 처리(`is_read=True`)된 모든 알림을 목록에서 삭제합니다. |
| 안 읽은 알림 수 조회 | `GET` | `/notification/unread-count/` | 없음 | 본인의 역할별(학생/강사) 아직 읽지 않은 알림 카운트 수를 반환합니다. (뱃지용) |
| 특정 알림 읽음 처리 | `PATCH` | `/notification/<int:pk>/read/` | **[Path]**<br>- `pk` (int, 알림 ID) | 지정한 단일 알림을 읽음(`is_read=True`) 상태로 전환하고 변경된 정보를 반환합니다. |
| 모든 알림 일괄 읽음 | `PATCH` | `/notification/read-all/` | 없음 | 본인이 수신한 전체 미독 알림을 일괄 읽음 처리합니다. |
| FCM 디바이스 토큰 조회 | `GET` | `/device-token/` | 없음 | FCM 푸시 전송용으로 등록된 본인의 최신 디바이스 토큰 및 알림 종류별 동의 여부를 확인합니다. |
| FCM 디바이스 토큰 등록 | `POST` | `/device-token/` | **[Body (JSON)]**<br>- `token` (str, 필수)<br>- `platform` (str, 선택)<br>- `is_active` (bool, 선택)<br>- `is_chat_active` (bool, 선택) | 새 FCM 디바이스 토큰을 계정에 맵핑하며, 중복된 다른 유저의 토큰 맵핑은 자동 삭제합니다. |
| FCM 알림 상태 토글 | `PUT` | `/device-token/` | **[Body (JSON)]** (선택)<br>- `is_active` (bool)<br>- `is_chat_active` (bool) | 전체 푸시 알림 수신 상태(`is_active`) 또는 채팅 알림 수신 상태(`is_chat_active`)를 명시적으로 전달받아 수정하거나 토글합니다. |
