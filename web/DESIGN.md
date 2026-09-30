# CLASSY 웹 디자인 기준

Flutter의 실제 화면 소스를 확인한 뒤 해당 컴포넌트를 웹에 대응시켰습니다.

| 웹 화면 | 앱 기준 | 웹 확장 |
| --- | --- | --- |
| 공통 탐색 | HomeHeader, ClassyDestination, ClassyNavigationItem | PC 상단 5개 메뉴, 모바일 하단 5개 탭. 실제 SVG 재사용 |
| 홈 | StudentHomeView, TeacherHomeView, HomeActionCard, MyLectureListButton | 앱의 2개 빠른 메뉴와 관리 버튼 유지. 지역 과외/과목 탐색을 본문에, 계정/내 강의를 우측에 배치 |
| 강의 찾기 | LectureBrowseView, LectureCard | 연보라 검색, 좌측 탐색/과목, 가로형 썸네일 목록 |
| 과외 찾기 | TutoringBrowseView, StudentPostListView, TutorCard, StudentPostCard | 회색 카드, 40px 아바타, 이름·학교·지역·과목 순서 유지. 넓은 화면 2열 |
| 로그인 | LoginView | 앱의 환영 문구, 22px 강조색 타이틀, 이메일/비밀번호 폼을 폭 제한 모달로 |
| 상세 | LecturePlayerView, TeacherProfileView, StudentPostDetailView | 영상·프로필·설명·조건·액션의 읽기 순서 유지. 웹 모달과 가로 조건표 |
| 채팅 | ChatListView, ChatDetailView | 목록과 대화를 PC에서 동시에 표시. 앱의 연보라 메시지 색상 사용 |
| 마이페이지 | MyPageHomeView | 프로필·캐시·대여 관리·메뉴를 왼쪽, 정보 수정 폼을 오른쪽에 배치 |
| 알림/등록 | NotificationView, VideoUploadView | 구분선 목록과 단일 열 폼, 원래 API 동작 유지 |
| 회원가입/계정 | SignupAccountView, SignupVerifyPhoneView, TeacherSchoolInfoView, PasswordResetView | 학생·강사 선택, 전화 인증, 학교 정보, 동의를 같은 모달 폼에 배치 |
| 강사 스튜디오 | LectureUploadView, LectureManagementView, SettlementTab | 좌측 콘텐츠 탐색과 업로드 폼, 우측 게시 체크리스트·미리보기. 원래 보라색과 얇은 구분선 유지 |
| 캐시/인증/정산 | CashManagementView, PurchaseCancelView, 강사 인증·정산 화면 | 큰 장식 카드 없이 잔액·내역·입력 폼을 구분선으로 구성 |
| 성사 등록/후기 | MatchRegistrationBasicInfoStep, MatchRegistrationProofStep, 과외 후기 | 상담 채팅에서 모달로 진입. 동일한 과목·시작일·수업료·계좌·증빙 API 사용 |

브랜드 색상 #5F65D7, 연보라 #EFEFFB, 본문 #393C41, 보조 글자 #727883,
회색 배경 #F4F5F6는 Flutter ThemeColors를 사용합니다.
Pretendard v1.3.9를 로컬 제공하며 라이선스는 public/fonts/LICENSE.txt에 있습니다.
일반 본문 14–16px, 섹션 18px, 페이지 타이틀 22–25px. 카드 8px, 버튼 6–7px.
그림자와 장식 배경은 사용하지 않으며, 모달에만 최소한의 구분용 그림자를 적용합니다.

실제 데이터가 없는 화면에 샘플 프로필이나 강의 수를 노출하지 않습니다.
스크린샷 테스트의 샘플 데이터는 브라우저 테스트에서만 사용하며 빌드에 포함되지 않습니다.
