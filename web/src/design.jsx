import React, { useContext, useState } from "react";
import {
  ArrowRight,
  ChevronRight,
  Search,
  Heart,
  Bell,
  BookOpen,
  MapPin,
  Play,
  SlidersHorizontal,
  RefreshCw,
  ShieldCheck,
  LogOut,
  Plus,
  Check,
  X,
  MessageCircle,
} from "lucide-react";
import {
  Ctx,
  useLoad,
  Btn,
  State,
  Empty,
  Gate,
  Subjects,
  money,
} from "./shared";
import { api, list } from "./api";

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
  studio: "강사 스튜디오",
  cash: "캐시 관리",
  settlement: "수익 및 정산",
  verification: "강사 인증",
  account: "계정 관리",
  "tutoring-manage": "나의 과외 관리",
  support: "고객지원",
};
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
  const { user, go, login } = useContext(Ctx);
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
              className="icon-button"
              aria-label="알림"
              onClick={() => go("notifications")}
            >
              <Bell size={21} />
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
        <div>
          <span className="footer-brand">CLASSY</span>
          <p>주식회사 클래씨</p>
        </div>
        <nav aria-label="서비스 안내">
          <a href="/service-terms">이용약관</a>
          <a href="/privacy">개인정보처리방침</a>
          <a
            href="https://pf.kakao.com/_YxhWxlX"
            target="_blank"
            rel="noreferrer"
          >
            고객센터
          </a>
        </nav>
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
                          detail(teacher ? "posts" : "teachers", item.id)
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
                    정보 수정
                  </button>
                </div>
                <div className="cash-line">
                  <span>보유 캐시</span>
                  <strong>
                    {money(user.cash)} <small>캐시</small>
                  </strong>
                </div>
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
                        onClick={() => detail("lectures", item.id)}
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
              href="https://pf.kakao.com/_YxhWxlX"
              target="_blank"
              rel="noreferrer"
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

// TutoringBrowseView / LectureBrowseView: lavender search, filters, list rows.
export function Catalog({ kind, mode }) {
  const { user, subjects, detail, go, login } = useContext(Ctx);
  const [search, setSearch] = useState(""),
    [query, setQuery] = useState(""),
    [subject, setSubject] = useState(""),
    [order, setOrder] = useState("latest"),
    [page, setPage] = useState(1);
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
  const endpoint =
    mode === "learning" && user?.role === "instructor"
      ? "/mypage/instructor/uploaded-lectures/"
      : endpoints[mode] || endpoints[kind];
  const params = new URLSearchParams({ page: String(page), ordering: order });
  if (mode === "expired") params.set("status", "expired");
  if (mode === "saved-teachers") params.set("liked", "true");
  if (query) params.set(kind === "lectures" ? "q" : "search", query);
  if (subject) params.set("subject", subject);
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
  const publicBrowse = mode === "lectures";
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
            : [
                ["lectures", "강의 찾기"],
                ["teachers", "선생님 찾기"],
                ["posts", "학생 찾기"],
              ]
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
                    (category || "전체") === c && !subject ? "active" : ""
                  }
                  onClick={() =>
                    reset(() => {
                      setCategory(c === "전체" ? "" : c);
                      setSubject("");
                    })
                  }
                >
                  {c}
                </button>
              ))}
            </div>
          </>
        )}
        <p className="catalog-help">
          앱과 같은 계정으로
          <br />
          강의와 과외를 이용하세요.
        </p>
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
              <label className="filter-select">
                <SlidersHorizontal size={16} />
                <select
                  aria-label="과목"
                  value={subject}
                  onChange={(e) =>
                    reset(() => {
                      setSubject(e.target.value);
                      setCategory("");
                    })
                  }
                >
                  <option value="">과목 필터</option>
                  {subjects.map((s) => (
                    <option value={s.number} key={s.number}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
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
                      onClick={() => (user ? detail(kind, item.id) : login())}
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
                  query || subject || category
                    ? "검색 결과가 없습니다."
                    : "등록된 내용이 없습니다."
                }
                text={
                  query || subject || category
                    ? "검색어 또는 필터를 변경해 보세요."
                    : "새로운 강의와 과외가 등록되면 이곳에서 확인할 수 있습니다."
                }
              />
            )}
          </State>
        </Access>
      </div>
    </div>
  );
}

// Original TutorCard/StudentPostCard anatomy: avatar, identity, location, subject.
export function Card({ item, kind, onClick }) {
  const { notify } = useContext(Ctx);
  const [liked, setLiked] = useState(item.is_liked),
    [busy, setBusy] = useState(false);
  const name =
    item.user_name || item.student_name || item.name || "CLASSY 회원";
  const region = Array.isArray(item.regions)
    ? item.regions.map((r) => r.label || r.name).join(", ")
    : item.region;
  async function like(e) {
    e.stopPropagation();
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
              {kind === "teachers" && item.university && (
                <span>{item.university}</span>
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
                  ["studio", "강사 스튜디오"],
                  ["settlement", "수익 및 정산"],
                  ["verification", "강사 인증"],
                ]
              : [["cash", "캐시 관리"]]
            )
              .concat([
                ["tutoring-manage", "나의 과외 관리"],
                ["account", "계정 관리"],
                ["support", "고객지원"],
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
            <a
              href="https://pf.kakao.com/_YxhWxlX"
              target="_blank"
              rel="noreferrer"
            >
              <MessageCircle size={18} />
              고객센터
              <ChevronRight size={16} />
            </a>
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
            <label>
              지역
              <input
                name="region"
                defaultValue={user.region || ""}
                placeholder="예: 서울 강남구"
              />
            </label>
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
