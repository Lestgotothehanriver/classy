import React, { useContext, useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import {
  ArrowRight,
  ChevronRight,
  Search,
  Heart,
  Bell,
  BookOpen,
  MapPin,
  UserRound,
  Play,
  SlidersHorizontal,
  RefreshCw,
  ShieldCheck,
  LogOut,
  Plus,
  Check,
  X,
  MessageCircle,
  QrCode,
} from "lucide-react";
import {
  Ctx,
  useLoad,
  Btn,
  State,
  Empty,
  Gate,
  Modal,
  Subjects,
  money,
  RegionFields,
} from "./shared";
import { api, list } from "./api";
import regions from "./regions.json";
import { appDownloadQrUrl, appStoreUrl, playStoreUrl } from "./app_download";

export const endpoints = {
  teachers: "/tutoring/instructors/",
  posts: "/tutoring/posts/",
  lectures: "/lectures/",
  learning: "/mypage/student/rented-lectures/",
  saved: "/mypage/student/liked-lectures/",
  expired: "/mypage/student/rented-lectures/",
  "saved-teachers": "/tutoring/instructors/",
};
export const pageNames = {
  home: "홈",
  lectures: "강의 찾기",
  teachers: "과외 찾기",
  posts: "과외 찾기",
  learning: "내 강의실",
  saved: "찜한 강의",
  expired: "만료된 강의",
  "saved-teachers": "찜한 선생님",
  chat: "채팅",
  profile: "마이페이지",
  notifications: "알림",
  upload: "강의 등록",
  studio: "강의 스튜디오",
  cash: "캐시 관리",
  settlement: "수익 및 정산",
  verification: "강사 인증",
  account: "계정 관리",
  "tutoring-manage": "나의 과외 관리",
  support: "고객지원",
  notices: "공지사항",
};

const subjectCategories = [
  ["초등", 1, 8], ["중등", 9, 17], ["고등국어", 18, 31],
  ["고등영어", 32, 34], ["고등수학", 35, 53], ["고등사회", 54, 80],
  ["고등과학", 81, 107], ["제2외국어", 108, 116], ["직업탐구", 117, 122],
  ["논술", 123, 130], ["기타 국내", 131, 146], ["유학", 147, 155],
  ["영어", 156, 164], ["외국어", 165, 200], ["프로그래밍", 201, 218],
  ["개발", 219, 224], ["미술", 225, 241], ["악기", 242, 269], ["음악", 270, 282],
];

const lecturePriceOptions = ["전체", "프리뷰 강의", "무료 강의", ...Array.from({ length: 10 }, (_, index) => `${(index + 1) * 100} 캐시 이하`)];
const postPriceOptions = ["전체", "월 20만원 이하", "월 30만원 이하", "월 40만원 이하", "월 50만원 이하", "월 60만원 이하", "월 70만원 이하", "월 80만원 이하", "월 90만원 이하", "월 100만원 이하", "협의 후 결정"];
const gradeOptions = ["전체", "유치원생", "초1", "초2", "초3", "초4", "초5", "초6", "중1", "중2", "중3", "고1", "고2", "고3", "N수생", "재수생", "대학생", "사회인"];
const studentNumberOptions = () => {
  const currentYear = new Date().getFullYear() % 100;
  return [
    ...Array.from({ length: 10 }, (_, index) => `${currentYear - index}학번`),
    `${currentYear - 10}학번 이전`,
  ];
};

function formatStudentNumber(value) {
  const studentNumber = String(value || "").trim();
  return studentNumber.length >= 4 ? `${studentNumber.slice(2, 4)}학번` : "";
}

function formatTeacherSex(value) {
  if (["M", "남", "남성"].includes(value)) return "남성";
  if (["F", "여", "여성"].includes(value)) return "여성";
  return "";
}

function formatTeacherAge(value) {
  if (!value) return "";
  const birthDate = new Date(`${value}T00:00:00`);
  if (Number.isNaN(birthDate.valueOf())) return "";

  const today = new Date();
  const age =
    today.getFullYear() -
    birthDate.getFullYear() -
    (today.getMonth() < birthDate.getMonth() ||
    (today.getMonth() === birthDate.getMonth() &&
      today.getDate() < birthDate.getDate())
      ? 1
      : 0);
  return age >= 0 ? `만 ${age}세` : "";
}

function defaultFilters(kind) {
  return {
    subjects: [], subjectCategories: [], regions: [], regionStates: [], price: "전체", videoLength: "전체", isTutoring: "전체",
    methods: ["전체"], sex: "전체", ages: ["전체"], review: "전체", videoLecture: "전체",
    university: "", department: "", studentNumbers: [], grade: "전체",
  };
}

function selectedCount(filters) {
  return filters.subjects.length + filters.subjectCategories.length + filters.regions.length + filters.regionStates.length +
    filters.methods.filter((item) => item !== "전체").length + filters.ages.filter((item) => item !== "전체").length + filters.studentNumbers.length +
    [filters.price !== "전체", filters.videoLength !== "전체", filters.isTutoring !== "전체",
      filters.sex !== "전체", filters.review !== "전체", filters.videoLecture !== "전체",
      Boolean(filters.university), Boolean(filters.department), filters.grade !== "전체"].filter(Boolean).length;
}

function FilterModal({ kind, subjects, initialFilters, onApply, onClose }) {
  const [filters, setFilters] = useState(initialFilters);
  const [tab, setTab] = useState(0);
  const [subjectCategory, setSubjectCategory] = useState("전체");
  const [province, setProvince] = useState("전체");
  const [schools, setSchools] = useState([]);
  const [schoolQuery, setSchoolQuery] = useState("");
  const tabs = kind === "lectures"
    ? ["과목", "금액", "영상 길이", "과외 여부", "지역", "대학/학과", "학번"]
    : kind === "teachers"
      ? ["과목", "지역", "과외 방식", "성별", "나이", "리뷰", "영상 강의", "대학/학과", "학번"]
      : ["과목", "지역", "금액", "과외 방식", "성별", "학년"];
  const update = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  const toggle = (key, value) => {
    const values = filters[key];
    if (value === "전체") return update(key, ["전체"]);
    const withoutAll = values.filter((item) => item !== "전체");
    const next = withoutAll.includes(value)
      ? withoutAll.filter((item) => item !== value)
      : [...withoutAll, value];
    update(key, next.length ? next : ["전체"]);
  };
  const selectedSchool = schools.find((school) => school.name === filters.university);
  const subjectsForCategory = (category) => subjects.filter((subject) => {
    const definition = subjectCategories.find(([name]) => name === category);
    return definition && subject.number >= definition[1] && subject.number <= definition[2];
  });
  const categorySubjects = subjectCategory === "전체" ? [] : subjectsForCategory(subjectCategory);
  const provinces = ["전체", ...new Set(regions.map(([, name]) => name.split(" ")[0]))];
  const visibleRegions = province === "전체" ? [] : regions.filter(([, name]) => name.startsWith(`${province} `));

  useEffect(() => {
    if (tab !== tabs.indexOf("대학/학과") || schools.length) return;
    fetch("/schools.json").then((response) => response.ok ? response.json() : []).then(setSchools).catch(() => {});
  }, [tab, tabs, schools.length]);

  const selectSubject = (subject) => {
    if (subjectCategory === "전체") {
      setFilters((current) => ({ ...current, subjects: [], subjectCategories: [] }));
      return;
    }
    if (subject === null) {
      setFilters((current) => ({
        ...current,
        subjects: current.subjects.filter((number) => !subjectsForCategory(subjectCategory).some((item) => item.number === number)),
        subjectCategories: current.subjectCategories.includes(subjectCategory)
          ? current.subjectCategories.filter((category) => category !== subjectCategory)
          : [...current.subjectCategories, subjectCategory],
      }));
      return;
    }
    setFilters((current) => ({
      ...current,
      subjectCategories: current.subjectCategories.filter((category) => category !== subjectCategory),
      subjects: current.subjects.includes(subject.number)
        ? current.subjects.filter((number) => number !== subject.number)
        : [...current.subjects, subject.number],
    }));
  };
  const selectRegion = (region) => {
    if (province === "전체") {
      setFilters((current) => ({ ...current, regions: [], regionStates: [] }));
      return;
    }
    if (region === null) {
      setFilters((current) => ({
        ...current,
        regions: current.regions.filter((id) => !regions.some(([regionId, name]) => regionId === id && name.startsWith(`${province} `))),
        regionStates: current.regionStates.includes(province)
          ? current.regionStates.filter((state) => state !== province)
          : [...current.regionStates, province],
      }));
      return;
    }
    setFilters((current) => ({
      ...current,
      regionStates: current.regionStates.filter((state) => state !== province),
      regions: current.regions.includes(region[0])
        ? current.regions.filter((id) => id !== region[0])
        : [...current.regions, region[0]],
    }));
  };
  const renderSubject = () => <div className="filter-catalog">
    <nav aria-label="과목 카테고리">
      {["전체", ...subjectCategories.map(([name]) => name)].map((category) => <button type="button" key={category} className={subjectCategory === category ? "active" : ""} onClick={() => setSubjectCategory(category)}>{category}</button>)}
    </nav>
    <div className="filter-option-grid">{subjectCategory === "전체" ? <button type="button" className={!filters.subjects.length && !filters.subjectCategories.length ? "selected" : ""} onClick={() => selectSubject(null)}>전체<Check size={16} /></button> : <><button type="button" className={filters.subjectCategories.includes(subjectCategory) ? "selected" : ""} onClick={() => selectSubject(null)}>전체<Check size={16} /></button>{categorySubjects.map((subject) => <button type="button" key={subject.number} className={filters.subjects.includes(subject.number) ? "selected" : ""} onClick={() => selectSubject(subject)}>{subject.name}<Check size={16} /></button>)}</>}</div>
  </div>;
  const renderRegion = () => <div className="filter-catalog">
    <nav aria-label="지역 시도">{provinces.map((item) => <button type="button" key={item} className={province === item ? "active" : ""} onClick={() => setProvince(item)}>{item}</button>)}</nav>
    <div className="filter-option-grid">{province === "전체" ? <button type="button" className={!filters.regions.length && !filters.regionStates.length ? "selected" : ""} onClick={() => selectRegion(null)}>전체<Check size={16} /></button> : <><button type="button" className={filters.regionStates.includes(province) ? "selected" : ""} onClick={() => selectRegion(null)}>전체<Check size={16} /></button>{visibleRegions.map((region) => <button type="button" key={region[0]} className={filters.regions.includes(region[0]) ? "selected" : ""} onClick={() => selectRegion(region)}>{region[1].replace(`${province} `, "")}<Check size={16} /></button>)}</>}</div>
  </div>;
  const renderOptions = (key, options, multi = false) => <div className="filter-option-list">{options.map((option) => {
    const selected = multi ? filters[key].includes(option) : filters[key] === option;
    return <button type="button" key={option} className={selected ? "selected" : ""} onClick={() => multi ? toggle(key, option) : update(key, option)}><span>{option}</span>{selected && <Check size={19} />}</button>;
  })}</div>;
  const renderSchool = () => {
    const filteredSchools = schools.filter((school) => school.name.includes(schoolQuery.trim()));
    return <div className="filter-school">
      <section className="filter-school-column">
        <label className="filter-school-search"><span><input aria-label="대학교 검색" type="search" value={schoolQuery} placeholder="대학교 이름 검색" onChange={(event) => setSchoolQuery(event.target.value)} /><Search size={20} aria-hidden="true" /></span></label>
        <div className="filter-school-list">{filteredSchools.map((school) => <button type="button" key={school.name} className={filters.university === school.name ? "selected" : ""} onClick={() => { update("university", school.name); update("department", ""); }}><span>{school.name}</span>{filters.university === school.name && <Check size={19} />}</button>)}</div>
      </section>
      <div className="filter-school-divider" aria-hidden="true" />
      <section className="filter-school-column filter-department-column">
        {selectedSchool ? <div className="filter-school-list"><button type="button" className={!filters.department ? "selected" : ""} onClick={() => update("department", "")}><span>학과 전체</span>{!filters.department && <Check size={19} />}</button>{(selectedSchool.departments || []).map((department) => <button type="button" key={department} className={filters.department === department ? "selected" : ""} onClick={() => update("department", department)}><span>{department}</span>{filters.department === department && <Check size={19} />}</button>)}</div> : <p className="filter-school-placeholder">대학교를 먼저 선택해주세요.</p>}
      </section>
    </div>;
  };
  const content = () => {
    const label = tabs[tab];
    if (label === "과목") return renderSubject();
    if (label === "지역") return renderRegion();
    if (label === "대학/학과") return renderSchool();
    if (label === "학번") return renderOptions("studentNumbers", studentNumberOptions(), true);
    if (label === "금액") return renderOptions("price", kind === "lectures" ? lecturePriceOptions : postPriceOptions);
    if (label === "영상 길이") return renderOptions("videoLength", ["전체", "5분 이하", "10~30분", "30분 ~ 1시간", "1시간 ~ 1시간 30분", "1시간 30분 이상"]);
    if (label === "과외 여부") return renderOptions("isTutoring", ["전체", "과외 구함", "과외 구하지 않음"]);
    if (label === "과외 방식") return renderOptions("methods", ["전체", "대면", "비대면"], true);
    if (label === "성별") return renderOptions("sex", ["전체", "남자", "여자"]);
    if (label === "나이") return renderOptions("ages", ["전체", "10대", "20~25세", "25~30세", "30~35세", "35~40세", "40~45세", "45~50세", "50세 이상"], true);
    if (label === "리뷰") return renderOptions("review", ["전체", "리뷰 있음", "리뷰 없음"]);
    if (label === "영상 강의") return renderOptions("videoLecture", ["전체", "영상 강의 있음", "영상 강의 없음"]);
    return renderOptions("grade", gradeOptions);
  };
  return <Modal title="필터" onClose={onClose} wide><div className="filter-modal"><div className="filter-tabs" role="tablist">{tabs.map((name, index) => <button type="button" role="tab" aria-selected={tab === index} className={tab === index ? "active" : ""} key={name} onClick={() => setTab(index)}>{name}</button>)}</div><section className="filter-body">{content()}</section><footer className="filter-actions"><Btn type="button" onClick={() => setFilters(defaultFilters(kind))}>초기화</Btn><Btn type="button" className="primary" onClick={() => onApply(filters)}>필터 적용</Btn></footer></div></Modal>;
}
export function AppIcon({ name, selected = false }) {
  return (
    <span
      className="app-nav-icon"
      aria-hidden="true"
      style={{
        maskImage: `url(/app-icons/nav/${name}_icon_${selected ? "filled" : "outlined"}.svg)`,
      }}
    />
  );
}
function Avatar({ src, name = "", size = "" }) {
  return (
    <img
      className={"avatar " + size}
      src={src || "/app-icons/avatar.svg"}
      alt={name}
      onError={(e) => {
        e.currentTarget.onerror = null;
        e.currentTarget.src = "/app-icons/avatar.svg";
      }}
    />
  );
}

// ClassyDestination and HomeHeader: same five destinations and original SVGs.
export function Shell({ page, activeRole, setActiveRole, children }) {
  const { user, go, login, unreadNotificationCount } = useContext(Ctx);
  const tutoring = user?.role === "instructor" ? "posts" : "teachers";
  const nav = [
    ["home", "홈", "home"],
    ["lectures", "강의", "lecture"],
    [tutoring, "과외", "tutoring"],
    ["chat", "채팅", "chat"],
    ["profile", "마이", "my_page"],
  ];
  let roles = [];
  try {
    roles = JSON.parse(sessionStorage.getItem("classy_roles") || "[]");
  } catch {}
  const selected = (id) =>
    id === page ||
    (id === tutoring && ["teachers", "posts"].includes(page)) ||
    (id === "profile" && ["saved", "learning", "upload"].includes(page));
  return (
    <>
      <a
        className="skip"
        href="#main"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main").focus();
        }}
      >
        본문으로 이동
      </a>
      <header className="site-header">
        <div className="header-inner">
          <a href="#home" className="brand" aria-label="CLASSY 홈">
            <img src="/app-icons/logo.svg" alt="" />
            <span>CLASSY</span>
          </a>
          <nav className="top-nav" aria-label="주요 메뉴">
            {nav.map(([id, label, icon]) => (
              <a
                href={"#" + id}
                key={id}
                className={selected(id) ? "active" : ""}
                aria-current={selected(id) ? "page" : undefined}
              >
                <AppIcon name={icon} selected={selected(id)} />
                {label}
              </a>
            ))}
          </nav>
          <div className="header-actions">
            {roles.length > 1 && (
              <select
                aria-label="활동 계정"
                value={activeRole || user?.role}
                onChange={(e) => setActiveRole(e.target.value)}
              >
                {roles.map((r) => (
                  <option value={r.role} key={r.role}>
                    {r.role === "student" ? "학생" : "선생님"}
                  </option>
                ))}
              </select>
            )}
            <button
              className="icon-button notification-button"
              aria-label={
                unreadNotificationCount > 0
                  ? `알림, 읽지 않은 알림 ${unreadNotificationCount}개`
                  : "알림"
              }
              onClick={() => go("notifications")}
            >
              <Bell size={21} />
              {unreadNotificationCount > 0 && (
                <span className="notification-count" aria-hidden="true">
                  {unreadNotificationCount > 99
                    ? "99+"
                    : unreadNotificationCount}
                </span>
              )}
            </button>
            {user ? (
              <button
                className="header-profile"
                aria-label="내 프로필"
                onClick={() => go("profile")}
              >
                <Avatar src={user.profile_image} />
                <span>{user.nickname}</span>
              </button>
            ) : (
              <Btn className="primary small" onClick={login}>
                로그인
              </Btn>
            )}
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1} className={"page page-" + page}>
        {children}
      </main>
      <footer className="site-footer">
        <div className="footer-identity">
          <span className="footer-brand">CLASSY</span>
        </div>
        <div className="footer-details">
          <nav aria-label="서비스 안내">
            <a href="/service-terms">이용약관</a>
            <a href="/privacy">개인정보처리방침</a>
            <button type="button" className="footer-link" onClick={() => go("notices")}>공지사항</button>
            <a
              href="#support"
            >
              고객센터
            </a>
          </nav>
          <address className="footer-company-info">
            <span>주식회사 클래씨</span>
            <span>대표이사 우해강</span>
            <span>사업자등록번호 471-86-03936</span>
            <span>통신판매업 신고번호 2026-경기양주-1974</span>
            <span>주소 경기도 양주시 옥정동로7다길 74, 6층 6116호 (옥정동)</span>
            <span>대표 전화번호 010-8259-5284</span>
            <span>
              문의{" "}
              <a
                href="https://mail.google.com/mail/?view=cm&fs=1&to=classycompany%40classystudy.com"
                target="_blank"
                rel="noreferrer"
              >
                classycompany@classystudy.com
              </a>
            </span>
          </address>
        </div>
        <small>© {new Date().getFullYear()} CLASSY</small>
      </footer>
      <nav className="bottom-nav" aria-label="모바일 메뉴">
        {nav.map(([id, label, icon]) => (
          <a
            href={"#" + id}
            key={id}
            className={selected(id) ? "active" : ""}
            aria-current={selected(id) ? "page" : undefined}
          >
            <AppIcon name={icon} selected={selected(id)} />
            <span>{label}</span>
          </a>
        ))}
      </nav>
    </>
  );
}

export function PageHeading({ title, description, children }) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {children}
    </div>
  );
}

// StudentHomeView / TeacherHomeView → main content and a compact learning column.
export function HomePage() {
  const { user, go, login, signup, detail } = useContext(Ctx),
    teacher = user?.role === "instructor";
  const nearby = useLoad(
    user ? `/main/${teacher ? "instructor" : "student"}/` : null,
  );
  const rented = useLoad(
    user
      ? teacher
        ? "/mypage/instructor/uploaded-lectures/"
        : "/mypage/student/rented-lectures/"
      : null,
  );
  const items = teacher
    ? list(nearby.data?.recommended_posts)
    : list(nearby.data);
  const promotion = teacher ? nearby.data?.promotion : null;
  const thisMonthRevenue = nearby.data?.this_month_total_cash;
  const myRank = nearby.data?.lifetime_rank_info?.rank;
  return (
    <>
      <PageHeading
        title={
          user ? `${user.nickname}님, 반가워요.` : "나에게 필요한 배움, CLASSY"
        }
        description={
          teacher
            ? "학생과 만나는 새로운 방법. 강의와 과외를 한곳에서 관리하세요."
            : "필요한 강의를 골라 듣고, 나에게 맞는 과외 선생님을 만나보세요."
        }
      />
      <AppDownloadLinks />
      <section className="home-section home-notice-section">
        <div className="section-title">
          <h2>공지사항</h2>
          <button
            className="text-button"
            onClick={() => go("notices")}
          >
            전체 보기 <ChevronRight size={15} />
          </button>
        </div>
        <HomeNoticeExposure />
      </section>
      <div className="home-layout">
        <div className="home-main">
          <section className="home-actions" aria-label="빠른 메뉴">
            <button
              className="home-action"
              onClick={() => go(teacher ? "upload" : "lectures")}
            >
              <h2>{teacher ? "강의 업로드" : "강의 찾기"}</h2>
              <p>
                {teacher ? (
                  "학생들이 볼 강의를 올려보세요."
                ) : (
                  <>
                    나에게 필요한 강의만
                    <br />
                    쏙쏙 골라서 듣기
                  </>
                )}
              </p>
              <span className="action-bottom">
                <span>
                  바로가기 <ArrowRight size={15} />
                </span>
                <img src="/app-icons/video.svg" alt="" />
              </span>
            </button>
            <button
              className="home-action"
              onClick={() => go(teacher ? "posts" : "teachers")}
            >
              <h2>{teacher ? "과외 학생 찾기" : "과외 선생님 찾기"}</h2>
              <p>
                {teacher ? (
                  <>
                    학생과 함께 시작하는
                    <br />
                    1:1 맞춤 학습
                  </>
                ) : (
                  <>
                    과외 선생님과
                    <br />
                    1:1 맞춤 학습
                  </>
                )}
              </p>
              <span className="action-bottom">
                <span>
                  바로가기 <ArrowRight size={15} />
                </span>
                <img src="/app-icons/person.svg" alt="" />
              </span>
            </button>
          </section>
          <button className="rented-link" onClick={() => go("learning")}>
            <Play size={18} />
            {teacher ? "내 강의 관리" : "대여 강의 관리"}
            <ChevronRight size={18} />
          </button>
          {promotion && (
            <section
              className="promotion-summary-card"
              aria-label="출시 기념 프로모션 혜택"
            >
              <strong>🎉 클래씨 출시 기념 혜택이 적용 중이에요!</strong>
              <p>
                과외 성사 수수료{" "}
                <span className="promotion-summary-value">
                  {(promotion.tutoring_commission_rate_bps / 100).toFixed(1)}%
                </span>
                {" · "}
                <span className="promotion-summary-value">
                  {promotion.remaining_tutoring_registration_count}건
                </span>
                {" 남음"}
              </p>
              <p>
                강의 정산 수수료{" "}
                <span className="promotion-summary-value">
                  {(promotion.lecture_settlement_fee_rate_bps / 100).toFixed(1)}%
                </span>
                {" · "}
                {new Date(promotion.ends_at).toLocaleDateString("ko-KR", {
                  timeZone: "Asia/Seoul",
                })}
                까지
              </p>
            </section>
          )}
          <section className="home-section">
            <div className="section-title">
              <h2>과목별로 찾아보기</h2>
              <button className="text-button" onClick={() => go("lectures")}>
                전체 과목 <ChevronRight size={15} />
              </button>
            </div>
            <div className="subject-links">
              {[
                "국어",
                "영어",
                "수학",
                "과학",
                "사회",
                "코딩",
                "음악",
                "미술",
              ].map((name) => (
                <button
                  key={name}
                  onClick={() => {
                    sessionStorage.setItem("classy_category", name);
                    go("lectures");
                  }}
                >
                  {name}
                </button>
              ))}
            </div>
          </section>
          <section className="home-section nearby-section">
            <div className="section-title">
              <h2>{teacher ? "내 지역 학생 공고" : "내 지역 과외 선생님"}</h2>
              <button
                className="text-button"
                onClick={() => go(teacher ? "posts" : "teachers")}
              >
                전체 보기 <ChevronRight size={15} />
              </button>
            </div>
            <p className="section-description">
              {user?.region
                ? `${user.region} 지역을 기준으로 소개해 드려요.`
                : "내 지역에서 함께할 수 있는 과외를 찾아보세요."}
            </p>
            {!user ? (
              <div className="nearby-login">
                <MapPin size={24} />
                <div>
                  <h3>우리 동네 선생님을 만나보세요</h3>
                  <p>로그인하면 내 지역에 맞는 과외 정보를 볼 수 있어요.</p>
                </div>
                <button className="text-button accent" onClick={login}>
                  로그인 <ChevronRight size={15} />
                </button>
              </div>
            ) : (
              <State resource={nearby}>
                {items.length ? (
                  <div className="teacher-grid">
                    {items.slice(0, 4).map((item) => (
                      <Card
                        key={item.id}
                        item={item}
                        kind={teacher ? "posts" : "teachers"}
                        onClick={() =>
                          detail(teacher ? "posts" : "teachers", item.id, item)
                        }
                      />
                    ))}
                  </div>
                ) : (
                  <Empty
                    title={
                      teacher
                        ? "조회된 학생 공고가 없습니다."
                        : "조회된 선생님이 없습니다."
                    }
                    text="지역 설정을 확인하거나 전체 과외 목록을 살펴보세요."
                  >
                    <Btn onClick={() => go(teacher ? "posts" : "teachers")}>
                      과외 찾기
                    </Btn>
                  </Empty>
                )}
              </State>
            )}
          </section>
        </div>
        <aside className="home-aside">
          <section className="my-classy">
            <div className="aside-title">
              <h2>나의 CLASSY</h2>
              {user && (
                <span className="role-label">
                  {teacher ? "선생님" : "학생"}
                </span>
              )}
            </div>
            {user ? (
              <>
                <div className="user-summary">
                  <Avatar src={user.profile_image} />
                  <strong>{user.nickname}님</strong>
                  <button className="text-button" onClick={() => go("profile")}>
                    프로필 수정
                  </button>
                </div>
                {teacher ? (
                  <div className="teacher-summary">
                    <div className="cash-line">
                      <span>이번 달 수익</span>
                      <strong>
                        {thisMonthRevenue == null ? (
                          "—"
                        ) : (
                          <>
                            {money(thisMonthRevenue)} <small>캐시</small>
                          </>
                        )}
                      </strong>
                    </div>
                    <div className="cash-line">
                      <span>내 순위</span>
                      <strong>
                        {myRank == null
                          ? nearby.data
                            ? "순위 없음"
                            : "—"
                          : `${money(myRank)}위`}
                      </strong>
                    </div>
                  </div>
                ) : (
                  <div className="cash-line">
                    <span>보유 캐시</span>
                    <strong>
                      {money(user.cash)} <small>캐시</small>
                    </strong>
                  </div>
                )}
              </>
            ) : (
              <>
                <p>
                  앱에서 사용하던 계정으로
                  <br />
                  강의와 대화를 이어가세요.
                </p>
                <Btn className="primary full" onClick={login}>
                  로그인
                </Btn>
                <button className="text-button" onClick={signup}>
                  처음이신가요? 회원가입
                </button>
              </>
            )}
            <div className="account-shortcuts">
              {[
                ["learning", "내 강의실", BookOpen],
                ["saved", "찜한 강의", Heart],
                ["chat", "채팅", MessageCircle],
              ].map(([id, name, Icon]) => (
                <button key={id} onClick={() => go(id)}>
                  <Icon size={18} />
                  <span>{name}</span>
                  <ChevronRight size={16} />
                </button>
              ))}
            </div>
          </section>
          {user && (
            <section className="aside-section">
              <div className="section-title">
                <h2>{teacher ? "등록한 강의" : "수강 중인 강의"}</h2>
                <button
                  className="text-button"
                  onClick={() => go("learning")}
                  aria-label="내 강의실 전체 보기"
                >
                  <ChevronRight size={17} />
                </button>
              </div>
              <State resource={rented}>
                {list(rented.data).length ? (
                  list(rented.data)
                    .slice(0, 2)
                    .map((item) => (
                      <button
                        className="mini-lecture"
                        key={item.id}
                        onClick={() => detail("lectures", item.id, item)}
                      >
                        {item.thumbnail ? (
                          <img src={item.thumbnail} alt="" />
                        ) : (
                          <span>
                            <Play size={18} />
                          </span>
                        )}
                        <b>{item.title}</b>
                      </button>
                    ))
                ) : (
                  <p className="muted">
                    {teacher
                      ? "등록한 강의가 없습니다."
                      : "대여 중인 강의가 없습니다."}
                  </p>
                )}
              </State>
            </section>
          )}
          <section className="aside-section">
            <h2>CLASSY 이용 안내</h2>
            <ol className="guide-list">
              <li>
                <b>필요한 강의 찾기</b>
                <p>과목과 선생님을 확인하고 강의를 골라보세요.</p>
              </li>
              <li>
                <b>선생님과 상담하기</b>
                <p>과외 프로필을 살펴보고 상담을 제안하세요.</p>
              </li>
              <li>
                <b>내 강의실에서 학습하기</b>
                <p>대여한 강의와 진행 중인 대화를 이어가세요.</p>
              </li>
            </ol>
            <a
              className="support-link"
              href="#support"
            >
              이용 중 궁금한 점이 있나요?
              <span>
                고객센터 <ChevronRight size={14} />
              </span>
            </a>
          </section>
        </aside>
      </div>
    </>
  );
}

function AppDownloadLinks() {
  const [isQrDialogOpen, setIsQrDialogOpen] = useState(false);

  return (
    <>
      <section className="home-app-download" aria-label="클래씨 앱 다운로드">
        <div className="app-download-links">
          <a
            className="store-badge-link"
            href={appStoreUrl}
            target="_blank"
            rel="noreferrer"
            aria-label="App Store에서 클래씨 다운로드"
          >
            <img src="/app-icons/app-store-badge.png" alt="" />
          </a>
          <a
            className="store-badge-link"
            href={playStoreUrl}
            target="_blank"
            rel="noreferrer"
            aria-label="Google Play에서 클래씨 다운로드"
          >
            <img src="/app-icons/google-play-badge.png" alt="" />
          </a>
          <button
            type="button"
            className="app-download-qr-button"
            onClick={() => setIsQrDialogOpen(true)}
          >
            <QrCode size={18} aria-hidden="true" />
            QR로 다운로드
          </button>
          <a
            className="app-download-qr-button instagram-badge-link"
            href="https://www.instagram.com/classystudy_com/"
            target="_blank"
            rel="noreferrer"
            aria-label="CLASSY 인스타그램 열기"
          >
            <img src="/app-icons/instagram-badge.png" alt="Instagram" />
          </a>
        </div>
      </section>
      {isQrDialogOpen && (
        <Modal
          title="클래씨 앱 다운로드"
          onClose={() => setIsQrDialogOpen(false)}
        >
          <div className="app-download-qr-dialog">
            <QRCodeSVG
              value={appDownloadQrUrl}
              size={208}
              level="M"
              includeMargin
              aria-label="클래씨 앱 다운로드 QR 코드"
            />
            <p>QR 코드를 스캔해주세요</p>
            <Btn
              className="primary app-download-qr-confirm"
              onClick={() => setIsQrDialogOpen(false)}
            >
              확인
            </Btn>
          </div>
        </Modal>
      )}
    </>
  );
}

function kstMidnightTimestamp() {
  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  return (
    Date.UTC(kst.getUTCFullYear(), kst.getUTCMonth(), kst.getUTCDate() + 1) -
    9 * 60 * 60 * 1000
  );
}

function openNotice(go, id) {
  go(`notices/${id}`);
}

function HomeNoticeExposure() {
  const { go } = useContext(Ctx);
  const dismissalKey = "classy_notice_modal_hidden_until";
  const sessionDismissalKey = "classy_notice_modal_session_hidden";
  const exposure = useLoad("/notices/exposure/");
  const [index, setIndex] = useState(0);
  const [modalNotices, setModalNotices] = useState([]);
  const [modalIndex, setModalIndex] = useState(0);
  const banners = list(exposure.data?.banners);
  const carousel = list(exposure.data?.carousel);

  useEffect(() => {
    const hiddenUntil = Number(localStorage.getItem(dismissalKey) || 0);
    const hiddenForSession = sessionStorage.getItem(sessionDismissalKey) === "true";
    setModalNotices(hiddenUntil > Date.now() || hiddenForSession ? [] : carousel);
    setModalIndex(0);
  }, [exposure.data?.carousel]);

  useEffect(() => {
    if (index >= banners.length) setIndex(0);
  }, [banners.length, index]);

  const modal = modalNotices[modalIndex];
  const dismiss = () => {
    localStorage.setItem(dismissalKey, String(kstMidnightTimestamp()));
    sessionStorage.setItem(sessionDismissalKey, "true");
    setModalNotices([]);
  };
  const closeModal = () => {
    sessionStorage.setItem(sessionDismissalKey, "true");
    setModalNotices([]);
  };
  const banner = banners[index];
  return (
    <>
      {banner && (
        <section className="notice-carousel" aria-label="주요 공지사항">
          <button
            type="button"
            className="notice-banner"
            onClick={() => openNotice(go, banner.id)}
          >
            {(banner.home_banner_image || banner.banner_image) && <img src={banner.home_banner_image || banner.banner_image} alt="" />}
          </button>
          {banners.length > 1 && (
            <div className="notice-carousel-controls">
              <button
                type="button"
                aria-label="이전 공지"
                onClick={() => setIndex((index - 1 + banners.length) % banners.length)}
              >
                ‹
              </button>
              <span>{index + 1} / {banners.length}</span>
              <button
                type="button"
                aria-label="다음 공지"
                onClick={() => setIndex((index + 1) % banners.length)}
              >
                ›
              </button>
            </div>
          )}
        </section>
      )}
      {modal && (
        <Modal title="공지사항" onClose={closeModal}>
          <section className="notice-modal-content">
            <button
              type="button"
              className="notice-modal-link"
              onClick={() => {
                closeModal();
                openNotice(go, modal.id);
              }}
            >
              {(modal.mobile_image || modal.home_banner_image || modal.banner_image) && <img src={modal.mobile_image || modal.home_banner_image || modal.banner_image} alt="" />}
              <h3>{modal.title}</h3>
              <p>{modal.summary}</p>
            </button>
            {modalNotices.length > 1 && (
              <div className="notice-carousel-controls">
                <button
                  type="button"
                  aria-label="이전 공지"
                  onClick={() => setModalIndex((modalIndex - 1 + modalNotices.length) % modalNotices.length)}
                >
                  ‹
                </button>
                <span>{modalIndex + 1} / {modalNotices.length}</span>
                <button
                  type="button"
                  aria-label="다음 공지"
                  onClick={() => setModalIndex((modalIndex + 1) % modalNotices.length)}
                >
                  ›
                </button>
              </div>
            )}
            <div className="modal-actions notice-modal-actions">
              <Btn onClick={dismiss}>오늘 하루 보지 않기</Btn>
              <Btn className="primary" onClick={closeModal}>확인</Btn>
            </div>
          </section>
        </Modal>
      )}
    </>
  );
}

export function NoticePage() {
  const { go } = useContext(Ctx);
  const parseNoticeId = () => Number(location.hash.slice(1).split("/")[1]) || null;
  const [selectedId, setSelectedId] = useState(parseNoticeId);
  const notices = useLoad("/notices/");
  const detail = useLoad(selectedId ? `/notices/${selectedId}/` : null, [selectedId]);
  useEffect(() => {
    const syncHash = () => setSelectedId(parseNoticeId());
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);
  const closeDetail = () => go("notices");
  const select = (id) => go(`notices/${id}`);

  if (selectedId)
    return (
      <>
        <PageHeading title="공지사항" />
        <State resource={detail}>
          {detail.data && (
            <section className="notice-detail-page">
              <button className="text-button" onClick={closeDetail}>← 목록으로</button>
              <h2>{detail.data.title}</h2>
              <time>{new Date(detail.data.publish_at).toLocaleDateString("ko-KR")}</time>
              {(detail.data.home_banner_image || detail.data.banner_image) && <img src={detail.data.home_banner_image || detail.data.banner_image} alt="" />}
              <p>{detail.data.content}</p>
            </section>
          )}
        </State>
      </>
    );

  return (
    <>
      <PageHeading title="공지사항" description="CLASSY의 새로운 소식과 운영 안내를 확인하세요." />
      <State resource={notices}>
        {notices.data && (
          <section className="notice-list-page">
            {list(notices.data).length ? (
              list(notices.data).map((notice) => (
                <button
                  type="button"
                  className="notice-list-item"
                  key={notice.id}
                  onClick={() => select(notice.id)}
                >
                  <span><strong>{notice.title}</strong><small>{notice.summary}</small></span>
                  <time>{new Date(notice.publish_at).toLocaleDateString("ko-KR")}</time>
                </button>
              ))
            ) : <Empty title="등록된 공지사항이 없어요" />}
          </section>
        )}
      </State>
    </>
  );
}

// TutoringBrowseView / LectureBrowseView: lavender search, filters, list rows.
export function Catalog({ kind, mode }) {
  const { user, subjects, detail, go, login } = useContext(Ctx);
  const [search, setSearch] = useState(""),
    [query, setQuery] = useState(""),
    [order, setOrder] = useState("latest"),
    [page, setPage] = useState(1);
  const [filters, setFilters] = useState(() => defaultFilters(kind));
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [category, setCategory] = useState(() => {
    const value =
      mode === "lectures"
        ? sessionStorage.getItem("classy_category") || ""
        : "";
    sessionStorage.removeItem("classy_category");
    return value;
  });
  const isMine = ["learning", "saved", "expired", "saved-teachers"].includes(
    mode,
  );
  const browseMenu = [
    ["lectures", "강의 찾기"],
    ...(user?.role === "instructor" ? [] : [["teachers", "선생님 찾기"]]),
    ...(user?.role === "student" ? [] : [["posts", "학생 찾기"]]),
  ];
  const endpoint =
    mode === "learning" && user?.role === "instructor"
      ? "/mypage/instructor/uploaded-lectures/"
      : endpoints[mode] || endpoints[kind];
  const params = new URLSearchParams({ page: String(page), ordering: order });
  if (mode === "expired") params.set("status", "expired");
  if (mode === "saved-teachers") params.set("liked", "true");
  if (query) params.set(kind === "lectures" ? "q" : "search", query);
  const categorySubjectIds = filters.subjectCategories.flatMap((category) => {
    const definition = subjectCategories.find(([name]) => name === category);
    return definition ? subjects.filter((subject) => subject.number >= definition[1] && subject.number <= definition[2]).map((subject) => subject.number) : [];
  });
  const subjectIds = [...new Set([...filters.subjects, ...categorySubjectIds])];
  if (subjectIds.length) params.set("subject", subjectIds.join(","));
  if (kind === "lectures" && filters.subjectCategories.length) {
    params.set("filter_type", filters.subjectCategories.join(","));
  }
  else if (category) {
    const matchers = {
      코딩: (s) => s.number >= 196 && s.number <= 219,
      음악: (s) => s.number >= 237,
      미술: (s) => s.number >= 220 && s.number <= 236,
    };
    const ids = subjects
      .filter(matchers[category] || ((s) => s.name.includes(category)))
      .map((s) => s.number);
    if (ids.length) params.set("subject", ids.join(","));
  }
  const stateRegionIds = filters.regionStates.flatMap((state) => regions.filter(([, name]) => name.startsWith(`${state} `)).map(([id]) => id));
  const regionIds = [...new Set([...filters.regions, ...stateRegionIds])];
  if (kind === "lectures") {
    const lectureRegions = [
      ...filters.regionStates,
      ...filters.regions.map((id) => regions.find(([regionId]) => regionId === id)?.[1]).filter(Boolean),
    ];
    if (lectureRegions.length) params.set("region", [...new Set(lectureRegions)].join(","));
  } else if (regionIds.length) {
    params.set("region", regionIds.join(","));
  }
  if (filters.university) params.set("university", filters.university);
  if (filters.department) params.set("department", filters.department);
  if (filters.studentNumbers.length) {
    const studentNumbers = filters.studentNumbers
      .map((value) => value.match(/\d{2}/)?.[0])
      .filter(Boolean)
      .map((year) => String(2000 + Number(year)));
    params.set(kind === "teachers" ? "student_id" : "student_number", studentNumbers.join(","));
  }
  if (kind === "lectures") {
    if (filters.price === "무료 강의") params.set("max_price", "0");
    else if (filters.price !== "전체" && filters.price !== "프리뷰 강의") params.set("max_price", filters.price.match(/\d+/)?.[0] || "");
    if (filters.price === "프리뷰 강의") params.set("is_preview", "true");
    const videoLengths = { "5분 이하": "under_5", "10~30분": "10_30", "30분 ~ 1시간": "30_60", "1시간 ~ 1시간 30분": "60_90", "1시간 30분 이상": "over_90" };
    if (videoLengths[filters.videoLength]) params.set("video_length", videoLengths[filters.videoLength]);
    if (filters.isTutoring !== "전체") params.set("is_tutoring", String(filters.isTutoring === "과외 구함"));
  }
  if (kind === "teachers") {
    if (filters.methods.some((method) => method !== "전체")) params.set("method", filters.methods.filter((method) => method !== "전체").join(","));
    if (filters.sex !== "전체") params.set("sex", filters.sex === "남자" ? "남성" : "여성");
    if (filters.ages.some((age) => age !== "전체")) {
      const ages = filters.ages.map((age) => ({
        "10대": "10-19", "20~25세": "20-25", "25~30세": "25-30",
        "30~35세": "30-35", "35~40세": "35-40", "40~45세": "40-45",
        "45~50세": "45-50", "50세 이상": "50-99",
      })[age]);
      params.set("age", ages.filter(Boolean).join(","));
    }
    if (filters.review !== "전체") params.set("has_review", String(filters.review === "리뷰 있음"));
    if (filters.videoLecture !== "전체") params.set("has_lecture", String(filters.videoLecture === "영상 강의 있음"));
  }
  if (kind === "posts") {
    if (filters.price !== "전체" && filters.price !== "협의 후 결정") params.set("cost", String(Number(filters.price.match(/\d+/)?.[0]) * 10000));
    if (filters.methods.some((method) => method !== "전체")) params.set("method", filters.methods.filter((method) => method !== "전체").join(","));
    if (filters.sex !== "전체") params.set("sex", filters.sex === "남자" ? "남성" : "여성");
    if (filters.grade !== "전체") params.set("grade", filters.grade);
  }
  // 비로그인 방문자에게는 목록과 검색만 열고 상세·찜·상담은 로그인 뒤에 진행한다.
  const publicBrowse = ["lectures", "teachers", "posts"].includes(mode);
  const Access = publicBrowse ? React.Fragment : Gate;
  const resource = useLoad(
      user || publicBrowse ? endpoint + "?" + params : null,
      [user?.id, user?.role],
    ),
    items = list(resource.data);
  const reset = (fn) => {
    fn();
    setPage(1);
  };
  return (
    <div className="catalog-layout">
      <aside className="catalog-aside">
        <h2>{isMine ? "나의 학습" : "둘러보기"}</h2>
        <nav aria-label="목록 메뉴">
          {(isMine
            ? [
                ["learning", "대여 강의 관리"],
                ["saved", "찜한 강의"],
                ["expired", "만료된 강의"],
                ["saved-teachers", "찜한 선생님"],
              ]
            : browseMenu
          ).map(([id, label]) => (
            <a key={id} href={"#" + id} className={mode === id ? "active" : ""}>
              {label}
              <ChevronRight size={15} />
            </a>
          ))}
        </nav>
        {!isMine && (
          <>
            <h3>관심 과목</h3>
            <div className="side-subjects">
              {["전체", "국어", "영어", "수학", "과학", "코딩"].map((c) => (
                <button
                  key={c}
                  className={
                    (category || "전체") === c && !filters.subjects.length && !filters.subjectCategories.length ? "active" : ""
                  }
                  onClick={() =>
                    reset(() => {
                      setCategory(c === "전체" ? "" : c);
                      setFilters(defaultFilters(kind));
                    })
                  }
                >
                  {c}
                </button>
              ))}
            </div>
          </>
        )}
      </aside>
      <div className="catalog-content">
        {!isMine && (
          <form
            className="search"
            onSubmit={(e) => {
              e.preventDefault();
              reset(() => setQuery(search));
            }}
          >
            <input
              aria-label="검색"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={
                kind === "teachers"
                  ? "어떤 선생님을 찾고 있나요?"
                  : kind === "posts"
                    ? "어떤 학생을 찾고 있나요?"
                    : "어떤 강의를 찾고 있나요?"
              }
            />
            {search && (
              <button
                type="button"
                aria-label="검색어 지우기"
                onClick={() =>
                  reset(() => {
                    setSearch("");
                    setQuery("");
                  })
                }
              >
                <X size={17} />
              </button>
            )}
            <button aria-label="검색">
              <Search size={21} />
            </button>
          </form>
        )}
        <div className="catalog-toolbar">
          {!isMine ? (
            <>
              <button
                type="button"
                className={"filter-select filter-trigger" + (selectedCount(filters) ? " active" : "")}
                aria-haspopup="dialog"
                aria-expanded={isFilterOpen}
                onClick={() => setIsFilterOpen(true)}
              >
                <SlidersHorizontal size={16} />
                <span>{selectedCount(filters) ? `필터 ${selectedCount(filters)}` : "필터"}</span>
              </button>
              {category && (
                <button
                  className="filter-chip"
                  onClick={() => reset(() => setCategory(""))}
                >
                  {category}
                  <X size={13} />
                </button>
              )}
              <span className="toolbar-spacer" />
              {kind !== "lectures" && (
                <select
                  aria-label="정렬"
                  value={order}
                  onChange={(e) => reset(() => setOrder(e.target.value))}
                >
                  <option value="latest">최신순</option>
                  <option value="likes">인기순</option>
                  {kind === "teachers" && (
                    <option value="rank">랭킹순</option>
                  )}
                </select>
              )}
            </>
          ) : (
            <>
              <h2>{mode === "learning" ? "내 강의 목록" : pageNames[mode]}</h2>
              <span className="toolbar-spacer" />
              {user?.role === "instructor" && mode === "learning" && (
                <Btn onClick={() => go("upload")}>
                  <Plus size={16} />
                  강의 등록
                </Btn>
              )}
            </>
          )}
          <button
            className="icon-button"
            aria-label="새로고침"
            onClick={resource.reload}
          >
            <RefreshCw size={17} />
          </button>
        </div>
        <Access>
          <State resource={resource}>
            {items.length ? (
              <>
                <div className="results-caption">
                  {resource.data?.count ?? items.length}개의{" "}
                  {kind === "lectures"
                    ? "강의"
                    : kind === "posts"
                      ? "학생 공고"
                      : "선생님 프로필"}
                </div>
                <div
                  className={
                    kind === "lectures" ? "lecture-grid" : "teacher-grid"
                  }
                >
                  {items.map((item) => (
                    <Card
                      key={item.id}
                      item={item}
                      kind={kind}
                      onClick={() =>
                        user ? detail(kind, item.id, item) : login()
                      }
                    />
                  ))}
                </div>
                {(resource.data?.next || page > 1) && (
                  <div className="pagination">
                    <Btn
                      disabled={page === 1}
                      onClick={() => setPage((p) => p - 1)}
                    >
                      이전
                    </Btn>
                    <span>{page}</span>
                    <Btn
                      disabled={!resource.data?.next}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      다음
                    </Btn>
                  </div>
                )}
              </>
            ) : (
              <Empty
                title={
                  query || filters.subjects.length || filters.subjectCategories.length || category || selectedCount(filters)
                    ? "검색 결과가 없습니다."
                    : "등록된 내용이 없습니다."
                }
                text={
                  query || filters.subjects.length || filters.subjectCategories.length || category || selectedCount(filters)
                    ? "검색어 또는 필터를 변경해 보세요."
                    : "새로운 강의와 과외가 등록되면 이곳에서 확인할 수 있습니다."
                }
              />
            )}
          </State>
        </Access>
      </div>
      {isFilterOpen && <FilterModal kind={kind} subjects={subjects} initialFilters={filters} onClose={() => setIsFilterOpen(false)} onApply={(nextFilters) => reset(() => { setFilters(nextFilters); setCategory(""); setIsFilterOpen(false); })} />}
    </div>
  );
}

// Original TutorCard/StudentPostCard anatomy: avatar, identity, location, subject.
export function Card({ item, kind, onClick }) {
  const { user, login, notify } = useContext(Ctx);
  const [liked, setLiked] = useState(item.is_liked),
    [busy, setBusy] = useState(false);
  const name =
    item.user_name || item.student_name || item.name || "CLASSY 회원";
  const region = Array.isArray(item.regions)
    ? item.regions.map((r) => r.label || r.name).join(", ")
    : item.region;
  const studentNumberLabel = formatStudentNumber(item.student_number);
  const teacherPersonalInfo = [
    formatTeacherSex(item.sex),
    formatTeacherAge(item.birth_date),
  ]
    .filter(Boolean)
    .join(" · ");
  async function like(e) {
    e.stopPropagation();
    if (!user) {
      login();
      return;
    }
    setBusy(true);
    try {
      const result = await api(`/tutoring/instructors/${item.id}/like/`, {
        method: "POST",
      });
      setLiked(result.is_liked ?? !liked);
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  if (kind === "lectures")
    return (
      <button className="lecture-card" onClick={onClick}>
        <div className="thumbnail">
          {item.thumbnail ? (
            <img src={item.thumbnail} alt="" loading="lazy" />
          ) : (
            <Play size={24} />
          )}
        </div>
        <div className="card-body">
          <h3>{item.title}</h3>
          <p className="lecture-author">
            {item.instructor?.user_name ||
              item.instructor_name ||
              "CLASSY 선생님"}
          </p>
          <div className="lecture-meta">
            <Subjects values={item.subjects} />
            <span>
              <Heart size={13} />
              {item.like_count || 0}
            </span>
          </div>
          <strong className="lecture-price">
            {item.is_preview
              ? "프리뷰 강의"
              : Number(item.price) === 0
                ? "무료 강의"
                : money(item.price) + " 캐시"}
          </strong>
        </div>
      </button>
    );
  return (
    <article className="teacher-card">
      <button
        className="teacher-open"
        onClick={onClick}
        aria-label={
          name + (kind === "teachers" ? " 선생님 프로필" : " 학생 공고")
        }
      >
        <div className="teacher-card-top">
          <Avatar src={item.profile_image || item.student_profile_image} />
          <div className="teacher-identity">
            <div className="identity-line">
              <h3>{name}</h3>
              {item.is_certified && (
                <ShieldCheck
                  size={15}
                  className="certified"
                  aria-label="인증된 선생님"
                />
              )}
              {kind === "teachers" &&
                (item.university || studentNumberLabel) && (
                  <span>
                    {[item.university, studentNumberLabel]
                      .filter(Boolean)
                      .join(" ")}
                  </span>
                )}
            </div>
            <p>
              {kind === "teachers"
                ? item.department || "과외 선생님"
                : [
                    item.student_sex === "F"
                      ? "여"
                      : item.student_sex === "M"
                        ? "남"
                        : "",
                    item.grade,
                    item.student_field,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "과외 모집"}
            </p>
          </div>
        </div>
        <div className="teacher-details">
          {kind === "teachers" && teacherPersonalInfo && (
            <p>
              <UserRound size={15} />
              {teacherPersonalInfo}
            </p>
          )}
          {region && (
            <p>
              <MapPin size={15} />
              {region}
            </p>
          )}
          <div>
            <BookOpen size={15} />
            <Subjects values={item.subjects} />
          </div>
        </div>
      </button>
      {kind === "teachers" && (
        <button
          className={"favorite-button " + (liked ? "liked" : "")}
          aria-label={liked ? "선생님 찜 취소" : "선생님 찜하기"}
          disabled={busy}
          onClick={like}
        >
          <Heart size={20} fill={liked ? "currentColor" : "none"} />
          <span>{item.like_count || ""}</span>
        </button>
      )}
    </article>
  );
}

// MyPageHomeView: account identity and balance, flat menu, separate edit area.
export function Profile({ onLogout }) {
  const { user, refreshUser, notify, go } = useContext(Ctx);
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/accounts/me/", {
        method: "PATCH",
        body: Object.fromEntries(new FormData(e.currentTarget)),
      });
      await refreshUser();
      notify("프로필을 저장했습니다.");
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading title="마이페이지" />
      <div className="profile-grid">
        <aside className="profile-summary">
          <div className="profile-identity">
            <Avatar src={user.profile_image} />
            <div>
              <h2>{user.nickname}</h2>
              <span className="muted">
                {user.role === "instructor" ? "선생님 계정" : "학생 계정"}
              </span>
            </div>
          </div>
          <div className="balance">
            <span>보유 캐시</span>
            <strong>
              {money(user.cash)} <small>캐시</small>
            </strong>
          </div>
          <button className="rented-link" onClick={() => go("learning")}>
            <Play size={18} />
            대여 강의 관리
            <ChevronRight size={17} />
          </button>
          <nav className="profile-menu" aria-label="나의 메뉴">
            {(user.role === "instructor"
              ? [
                  ["studio", "강의 스튜디오"],
                  ["settlement", "수익 및 정산"],
                  ["verification", "강사 인증"],
                ]
              : [["cash", "캐시 관리"]]
            )
              .concat([
                ["tutoring-manage", "나의 과외 관리"],
                ["account", "계정 관리"],
                ["support", "고객지원"],
                ["notices", "공지사항"],
              ])
              .map(([id, label]) => (
                <button key={id} onClick={() => go(id)}>
                  {label}
                  <ChevronRight size={16} />
                </button>
              ))}
            <button onClick={() => go("saved")}>
              <Heart size={18} />
              찜한 강의
              <ChevronRight size={16} />
            </button>
            <button onClick={() => go("notifications")}>
              <Bell size={18} />
              알림
              <ChevronRight size={16} />
            </button>
            <button onClick={() => go("support")}>
              <MessageCircle size={18} />
              고객센터
              <ChevronRight size={16} />
            </button>
            <button onClick={onLogout}>
              <LogOut size={18} />
              로그아웃
            </button>
          </nav>
        </aside>
        <section className="profile-editor">
          <h2>내 정보 수정</h2>
          <p className="muted">변경한 정보는 CLASSY 앱에도 함께 적용됩니다.</p>
          <form onSubmit={submit} className="form">
            <label>
              닉네임
              <input
                name="user_name"
                defaultValue={user.nickname}
                required
                maxLength={30}
              />
            </label>
            <label>
              이메일
              <input value={user.email || ""} readOnly />
            </label>
            <RegionFields label="지역" value={user.region || ""} />
            <label>
              관심 분야
              <input
                name="field"
                defaultValue={user.field || ""}
                placeholder="관심 분야를 입력해 주세요"
              />
            </label>
            <Btn className="primary" disabled={busy}>
              변경사항 저장
              <Check size={16} />
            </Btn>
          </form>
        </section>
      </div>
    </>
  );
}
