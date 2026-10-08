import React, {
  useState,
  useEffect,
  useRef,
  createContext,
  useContext,
} from "react";
import { createRoot } from "react-dom/client";
import {
  BookOpen,
  ArrowUpRight,
  ArrowRight,
  Search,
  Home,
  Users,
  Play,
  MessageCircle,
  Heart,
  Bell,
  Settings,
  LogOut,
  X,
  Menu,
  ChevronRight,
  GraduationCap,
  ShieldCheck,
  SlidersHorizontal,
  Send,
  RefreshCw,
  LockKeyhole,
  LoaderCircle,
  Check,
  Upload,
  Leaf,
} from "lucide-react";
import { api, list } from "./api";
import { Auth } from "./auth";
import { Studio } from "./studio";
import { Services, ReportForm } from "./services";
import { Registration, registrationStatus } from "./contracts";
import "./redesign.css";
import {
  Ctx,
  money,
  date,
  formatVideoDuration,
  useLoad,
  Btn,
  Empty,
  State,
  Gate,
  Modal,
  Subjects,
} from "./shared";
import {
  Shell,
  PageHeading,
  HomePage,
  NoticePage,
  Catalog,
  Profile,
  endpoints,
  pageNames,
} from "./design";

const chatNotificationTypes = new Set([
  "message",
  "tutoring_request",
  "tutoring_proposal",
  "tutoring_accept",
]);

const contractNotificationTypes = new Set([
  "tutoring_contract_confirmed",
  "tutoring_contract_failed",
  "tutoring_contract_mismatch",
]);

function App() {
  const uploadLock = useRef(false);
  const [activeRole, setActiveRole] = useState(
    sessionStorage.getItem("classy_role") || "",
  );
  const [user, setUser] = useState(null),
    [ready, setReady] = useState(false);
  const [page, setPage] = useState(() => {
    const root = location.hash.slice(1).split("/")[0];
    return pageNames[root] ? root : "home";
  });
  const [modal, setModal] = useState(null),
    [toast, setToast] = useState("");
  const [pendingChatRoomId, setPendingChatRoomId] = useState(null);
  const pageRef = useRef(page);
  pageRef.current = page;
  const subjects = useLoad("/accounts/subjects/");
  const unreadNotifications = useLoad(
    user ? "/notification/unread-count/" : null,
    [user?.id],
  );
  const notify = (msg) => setToast(msg);
  function logoutLocal() {
    for (const key of ["classy_token", "classy_roles", "classy_role"])
      sessionStorage.removeItem(key);
    setActiveRole("");
    setUser(null);
    setModal(null);
  }
  useEffect(() => {
    const expired = () => {
      logoutLocal();
      notify("로그인이 만료되었습니다. 다시 로그인해 주세요.");
    };
    window.addEventListener("classy:expired", expired);
    if (sessionStorage.getItem("classy_token"))
      api("/accounts/me/")
        .then(setUser)
        .catch((e) => notify(e.message))
        .finally(() => setReady(true));
    else setReady(true);
    return () => window.removeEventListener("classy:expired", expired);
  }, []);
  useEffect(() => {
    const lock = (e) => {
      uploadLock.current = !!e.detail;
    };
    window.addEventListener("classy:uploading", lock);
    return () => window.removeEventListener("classy:uploading", lock);
  }, []);
  useEffect(() => {
    const change = () => {
      if (uploadLock.current) {
        history.replaceState(null, "", "#" + pageRef.current);
        notify("강의 등록이 완료될 때까지 기다려 주세요.");
        return;
      }
      const next = location.hash.slice(1).split("/")[0];
      setPage(pageNames[next] ? next : "home");
      setModal(null);
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    document.title = (pageNames[page] || "홈") + " | CLASSY";
  }, [page]);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(""), 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  useEffect(() => {
    if (!user) return undefined;

    const refresh = () => unreadNotifications.reload();
    const timer = window.setInterval(refresh, 30000);
    window.addEventListener("focus", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [user?.id]);
  const go = (p) => {
    location.hash = p;
  };

  function openNotificationTarget(notification) {
    const targetRole = notification?.role;
    const currentRole = activeRole || user?.role;

    if (
      ["student", "instructor"].includes(targetRole) &&
      targetRole !== currentRole
    ) {
      setActiveRole(targetRole);
      sessionStorage.setItem("classy_role", targetRole);
    }

    if (chatNotificationTypes.has(notification?.type)) {
      const roomId = notification?.data?.room_id?.toString();
      if (!roomId) return false;
      setPendingChatRoomId(roomId);
      go("chat");
      return true;
    }

    if (contractNotificationTypes.has(notification?.type)) {
      go("tutoring-manage");
      return true;
    }

    if (notification?.type === "instructor_status") {
      go("verification");
      return true;
    }

    return false;
  }

  async function logout() {
    if (uploadLock.current) {
      notify("강의 등록이 완료된 후 로그아웃해 주세요.");
      return;
    }
    try {
      await api("/accounts/logout/", { method: "POST" });
      logoutLocal();
      go("home");
    } catch (e) {
      notify(e.message);
    }
  }
  const effectiveUser = user
    ? { ...user, role: activeRole || user.role }
    : null;
  const unreadNotificationCount = Number(
    unreadNotifications.data?.[effectiveUser?.role],
  ) || 0;
  const context = {
    user: effectiveUser,
    setUser,
    toast,
    subjects: list(subjects.data),
    notify,
    go,
    login: () => {
      setToast("");
      setModal({ type: "login" });
    },
    detail: (kind, id, item) => {
      setToast("");
      setModal({ type: "detail", kind, id, item });
    },
    refreshUser: () => api("/accounts/me/").then(setUser),
    unreadNotificationCount,
    refreshNotificationUnreadCount: unreadNotifications.reload,
    setRole: (role) => changeRole(role),
    openNotificationTarget,
    signup: () => setModal({ type: "signup" }),
  };
  const changeRole = (role) => {
    if (uploadLock.current) {
      notify("강의 등록이 완료된 후 계정을 전환해 주세요.");
      return;
    }
    setActiveRole(role);
    sessionStorage.setItem("classy_role", role);
    setModal(null);
    go("home");
  };
  return (
    <Ctx.Provider value={context}>
      <Shell page={page} activeRole={activeRole} setActiveRole={changeRole}>
        {!ready ? (
          <div className="loading">
            <LoaderCircle className="spin" />
            계정을 확인하고 있어요
          </div>
        ) : page === "home" ? (
          <HomePage />
        ) : page === "profile" ? (
          <Gate>
            <Profile onLogout={logout} />
          </Gate>
        ) : page === "notices" ? (
          <NoticePage />
        ) : page === "notifications" ? (
          <>
            <PageHeading title="알림" />
            <Gate>
              <Notifications />
            </Gate>
          </>
        ) : page === "chat" ? (
          <>
            <PageHeading
              title="채팅"
              description="진행 중인 상담과 수업 이야기를 확인하세요."
            />
            <Gate>
              <Chat initialRoomId={pendingChatRoomId} />
            </Gate>
          </>
        ) : ["upload", "studio"].includes(page) ? (
          <Gate>
            <Studio key={page} upload={page === "upload"} />
          </Gate>
        ) : [
            "cash",
            "settlement",
            "verification",
            "account",
            "tutoring-manage",
            "support",
          ].includes(page) ? (
          <Gate>
            <Services key={page} page={page} onLogout={logoutLocal} />
          </Gate>
        ) : (
          <>
            <PageHeading title={pageNames[page]} />
            <Catalog
              key={page + effectiveUser?.role}
              kind={
                page === "saved-teachers"
                  ? "teachers"
                  : ["teachers", "posts"].includes(page)
                    ? page
                    : "lectures"
              }
              mode={page}
            />
          </>
        )}
      </Shell>
      {toast && !modal && (
        <div className="toast" role="status">
          {toast}
          <button aria-label="알림 닫기" onClick={() => setToast("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {["login", "signup"].includes(modal?.type) && (
        <Auth initial={modal.type} onClose={() => setModal(null)} />
      )}
      {modal?.type === "detail" && (
        <Detail
          kind={modal.kind}
          id={modal.id}
          item={modal.item}
          onClose={() => setModal(null)}
        />
      )}
    </Ctx.Provider>
  );
}
function Detail({ kind, id, item, onClose }) {
  const { notify, user, refreshUser } = useContext(Ctx);
  const base = (endpoints[kind] || "/lectures/") + id + "/";
  const resource = useLoad(base);
  const [busy, setBusy] = useState(false),
    [video, setVideo] = useState(""),
    [liked, setLiked] = useState(null),
    [rented, setRented] = useState(false),
    [rentConfirm, setRentConfirm] = useState(false),
    [postTab, setPostTab] = useState("info");
  const d = resource.data?.lecture_info || resource.data || {};
  const isPost = kind === "posts";
  const isTeacher = kind === "teachers";
  const reviews = useLoad(
    isPost && postTab === "reviews" && d.student?.id
      ? `/tutoring/students/${d.student.id}/reviews/`
      : null,
    [isPost, postTab, d.student?.id],
  );
  const methodLabel =
    d.method === "ONLINE" || d.method === "비대면"
      ? "비대면"
      : d.method === "OFFLINE" || d.method === "대면"
        ? "대면"
        : d.method || "상담 후 결정";
  const textLabels = (values) =>
    (Array.isArray(values) ? values : [])
      .map((value) =>
        typeof value === "object" ? value.label || value.name : value,
      )
      .filter(Boolean)
      .join(", ");
  const studentInfo = [
    d.sex,
    d.age != null ? `만 ${d.age}세` : "",
    d.grade,
    d.field,
  ]
    .filter(Boolean)
    .join(" · ");
  const postAuthor =
    item?.student_name || d.student_name || d.student?.user_name || "학생";
  const postProfileImage =
    item?.student_profile_image ||
    d.student_profile_image ||
    d.student?.profile_image;
  async function action(fn) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={
        kind === "lectures"
          ? "강의 상세"
          : kind === "teachers"
            ? "선생님 소개"
            : "과외 모집 상세"
      }
      onClose={onClose}
      wide
    >
      <State resource={resource}>
        {video ? (
          <video
            className="video"
            controls
            autoPlay
            src={video}
            onError={() =>
              notify("영상 재생에 실패했습니다. 네트워크 상태를 확인해 주세요.")
            }
          />
        ) : kind === "lectures" && d.thumbnail ? (
          <img className="detail-cover" src={d.thumbnail} alt="강의 썸네일" />
        ) : null}
        {!isTeacher && isPost && (
          <div className="post-detail-profile">
            {postProfileImage ? (
              <img src={postProfileImage} alt="" className="avatar" />
            ) : (
              <span className="avatar">{postAuthor.slice(0, 1)}</span>
            )}
            <div>
              <b>{postAuthor}</b>
              <p className="muted">
                {[
                  d.created_at ? date(d.created_at) : "",
                  `조회 ${d.view_count || 0}회`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>
            {user?.role === "student" && (
              <span
                className={
                  "post-status " + (d.is_active === false ? "closed" : "active")
                }
              >
                {d.is_active === false ? "모집 마감" : "모집 중"}
              </span>
            )}
          </div>
        )}
        {!isTeacher && (
          <>
            <Subjects values={d.subjects} />
            <h2 className="detail-title">
              {d.title || d.user_name || d.instructor?.user_name || "수업 소개"}
            </h2>
            {isPost ? null : (
              <>
                <p className="muted">
                  {[d.university, d.department, d.instructor?.user_name]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                <p className="detail-text">
                  {d.content ||
                    d.instruction ||
                    d.situation ||
                    "등록된 상세 소개가 없습니다."}
                </p>
              </>
            )}
          </>
        )}
        {kind === "lectures" ? (
          <>
            <div className="detail-facts">
              <span>
                수강료
                <strong>
                  {Number(d.price) === 0 ? "무료" : money(d.price) + " 캐시"}
                </strong>
              </span>
              <span>
                대여 기간<strong>{d.rental_period || 30}일</strong>
              </span>
              <span>
                강의 길이
                <strong>
                  {formatVideoDuration(d.video_duration) || "확인 중"}
                </strong>
              </span>
            </div>
            <div className="actions">
              <Btn
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    const r = await api(base + "like/", { method: "POST" });
                    setLiked(r.is_liked ?? !(liked ?? d.is_liked));
                  })
                }
              >
                <Heart
                  size={17}
                  fill={(liked ?? d.is_liked) ? "currentColor" : "none"}
                />
                찜하기
              </Btn>
              <Btn
                className="primary"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    const r = await api(base + "stream/");
                    setVideo(r.video);
                  })
                }
              >
                <Play size={16} />
                강의 재생
              </Btn>
              {Number(d.price) > 0 &&
                !rented &&
                !["active", "valid"].includes(resource.data?.rental_status) && (
                  <Btn disabled={busy} onClick={() => setRentConfirm(true)}>
                    캐시로 대여
                  </Btn>
                )}
            </div>
            {resource.data?.sample_preview && Number(d.price) > 0 && (
              <Btn
                className="full"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    const preview = await api(base + "preview/");
                    setVideo(preview.video);
                  })
                }
              >
                무료 미리보기 재생
              </Btn>
            )}
            {rentConfirm && (
              <div className="confirm-box">
                <b>
                  {money(d.price)} 캐시로 {d.rental_period || 30}일 대여할까요?
                </b>
                <p>
                  보유 캐시: {money(user.cash)} 캐시. 대여하면 캐시가
                  차감됩니다.
                </p>
                <div className="actions">
                  <Btn disabled={busy} onClick={() => setRentConfirm(false)}>
                    취소
                  </Btn>
                  <Btn
                    disabled={busy}
                    className="primary"
                    onClick={() =>
                      action(async () => {
                        await api("/cash/rentals/", {
                          method: "POST",
                          body: { lecture_id: id },
                        });
                        setRented(true);
                        setRentConfirm(false);
                        await refreshUser();
                        notify("강의를 대여했습니다.");
                      })
                    }
                  >
                    대여 확정
                  </Btn>
                </div>
              </div>
            )}
            <p className="form-note">
              보유 캐시는 기존 계정과 연동됩니다. 마이페이지의 캐시 관리에서
              캐시 잔액과 이용 내역을 확인하세요.
            </p>
            <Comments id={id} />
          </>
        ) : isPost ? (
          <>
            <div
              className="registration-tabs detail-tabs"
              role="tablist"
              aria-label="학생 모집 공고 상세"
            >
              <button
                type="button"
                role="tab"
                aria-selected={postTab === "info"}
                className={postTab === "info" ? "active" : ""}
                onClick={() => setPostTab("info")}
              >
                과외 공고
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={postTab === "reviews"}
                className={postTab === "reviews" ? "active" : ""}
                onClick={() => setPostTab("reviews")}
              >
                과외 리뷰
              </button>
            </div>
            {postTab === "info" ? (
              <dl className="class-info-list post-detail-list">
                <div>
                  <dt>학생 정보</dt>
                  <dd>{studentInfo || "정보 미입력"}</dd>
                </div>
                <div>
                  <dt>수업 과목</dt>
                  <dd>{textLabels(d.subjects) || "협의"}</dd>
                </div>
                <div>
                  <dt>수업 방식</dt>
                  <dd>{methodLabel}</dd>
                </div>
                <div>
                  <dt>지역</dt>
                  <dd>{textLabels(d.regions) || "협의"}</dd>
                </div>
                <div>
                  <dt>수업료</dt>
                  <dd>{d.cost ? `${money(d.cost)}원` : "협의"}</dd>
                </div>
                <div>
                  <dt>수업 일정</dt>
                  <dd>{d.schedule || "협의 가능"}</dd>
                </div>
                {d.situation && (
                  <div>
                    <dt>학생 상황</dt>
                    <dd>{d.situation}</dd>
                  </div>
                )}
                {d.etc && (
                  <div>
                    <dt>기타</dt>
                    <dd>{d.etc}</dd>
                  </div>
                )}
              </dl>
            ) : (
              <State resource={reviews}>
                {list(reviews.data).length ? (
                  <div className="review-list">
                    {list(reviews.data).map((review) => (
                      <article className="comment" key={review.id}>
                        <b>
                          {review.instructor_nickname ||
                            review.instructor_label ||
                            "선생님"}
                          {review.rating ? ` · ${review.rating}점` : ""}
                        </b>
                        <p>{review.comment}</p>
                        {review.created_at && (
                          <small className="muted">{date(review.created_at)}</small>
                        )}
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="muted">등록된 과외 리뷰가 없습니다.</p>
                )}
              </State>
            )}
            <Proposal kind={kind} id={id} onClose={onClose} />
          </>
        ) : isTeacher ? (
          <>
            <TeacherProfile id={id} teacher={d} item={item} />
            <Proposal kind={kind} id={id} onClose={onClose} />
          </>
        ) : (
          <>
            <div className="detail-facts">
              <span>
                수업 방식
                <strong>
                  {methodLabel}
                </strong>
              </span>
              <span>
                수업료
                <strong>
                  {d.cost ? money(d.cost) + "원" : "협의 후 결정"}
                </strong>
              </span>
              <span>
                일정<strong>{d.schedule || "협의 가능"}</strong>
              </span>
            </div>
            <Proposal kind={kind} id={id} onClose={onClose} />
          </>
        )}
        <ReportForm
          source={
            kind === "lectures"
              ? "lecture"
              : kind === "teachers"
                ? "teacher_profile"
                : "tutoring_post"
          }
          id={id}
        />
      </State>
    </Modal>
  );
}
function Proposal({ kind, id, onClose }) {
  const { user, notify, go } = useContext(Ctx);
  const eligible =
    kind === "teachers" ? user.role === "student" : user.role === "instructor";
  const posts = useLoad(
    eligible && kind === "teachers" ? "/tutoring/my-posts/" : null,
  );
  const [busy, setBusy] = useState(false),
    [open, setOpen] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    const f = new FormData(e.currentTarget);
    try {
      const body =
        kind === "teachers"
          ? { instructor_id: id, post_id: Number(f.get("post_id")) }
          : { post_id: id, message: f.get("message") };
      await api(
        kind === "teachers"
          ? "/tutoring/propose-to-instructor/"
          : "/tutoring/propose-to-student/",
        { method: "POST", body },
      );
      notify("과외 제안을 보냈습니다. 채팅에서 확인해 주세요.");
      onClose();
      go("chat");
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  if (!eligible) return null;
  return (
    <div className="info-panel">
      <h3>함께 배움을 시작해 볼까요?</h3>
      {!open ? (
        <Btn className="primary" onClick={() => setOpen(true)}>
          <MessageCircle size={16} />
          과외 상담 제안하기
        </Btn>
      ) : (
        <form className="form" onSubmit={submit}>
          {kind === "teachers" ? (
            <State resource={posts}>
              {list(posts.data).filter((p) => p.is_active !== false).length ? (
                <label>
                  상담할 내 과외 공고
                  <select name="post_id" required>
                    {list(posts.data)
                      .filter((p) => p.is_active !== false)
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.title || "내 과외 공고 #" + p.id}
                        </option>
                      ))}
                  </select>
                </label>
              ) : (
                <p>
                  상담을 제안하려면 과외 공고가 필요해요.
                  <Btn
                    type="button"
                    onClick={() => {
                      onClose();
                      go("tutoring-manage");
                    }}
                  >
                    모집 공고 작성하기
                  </Btn>
                </p>
              )}
            </State>
          ) : (
            <label>
              학생에게 전할 소개
              <textarea
                name="message"
                rows={3}
                required
                maxLength={3000}
                placeholder="어떤 수업을 함께할 수 있는지 알려주세요."
              />
            </label>
          )}
          <p className="form-note">
            제안을 보내면 상대방에게 알림이 전달되고 상담 채팅방이 만들어집니다.
          </p>
          <div className="actions">
            <Btn type="button" onClick={() => setOpen(false)}>
              취소
            </Btn>
            <Btn
              className="primary"
              disabled={
                busy ||
                (kind === "teachers" &&
                  !list(posts.data).some((p) => p.is_active !== false))
              }
            >
              제안 보내기
            </Btn>
          </div>
        </form>
      )}
    </div>
  );
}
function TeacherProfile({ id, teacher, item }) {
  const { user, notify, detail } = useContext(Ctx);
  const [tab, setTab] = useState("lectures");
  const info = useLoad(`/tutoring/instructors/${id}/info/`);
  const reviews = useLoad(`/tutoring/instructors/${id}/reviews/`);
  const lectures = useLoad(`/lectures/?instructor=${id}`);
  const profile = { ...(item || {}), ...(teacher || {}) };
  const [liked, setLiked] = useState(Boolean(profile.is_liked));
  const [likeCount, setLikeCount] = useState(Number(profile.like_count || 0));

  useEffect(() => {
    setLiked(Boolean(profile.is_liked));
    setLikeCount(Number(profile.like_count || 0));
  }, [profile.id, profile.is_liked, profile.like_count]);

  const textLabels = (values) =>
    (Array.isArray(values) ? values : [])
      .map((value) =>
        typeof value === "object" ? value.label || value.name : value,
      )
      .filter(Boolean)
      .join(", ");
  const birthDate = profile.birth_date ? new Date(profile.birth_date) : null;
  const today = new Date();
  const age =
    birthDate && !Number.isNaN(birthDate.valueOf())
      ? Math.max(
          0,
          today.getFullYear() -
            birthDate.getFullYear() -
            (today.getMonth() < birthDate.getMonth() ||
            (today.getMonth() === birthDate.getMonth() &&
              today.getDate() < birthDate.getDate())
              ? 1
              : 0),
        )
      : null;
  const methodLabel = (method) =>
    method === "ONLINE" || method === "비대면"
      ? "비대면"
      : method === "OFFLINE" || method === "대면"
        ? "대면"
        : method || "협의";
  const infoData = info.data || {};
  const reviewRows = list(reviews.data);
  const ratingAverage = (field) => {
    const scores = reviewRows
      .map((review) => Number(review[field]))
      .filter((score) => Number.isFinite(score));
    return scores.length
      ? scores.reduce((total, score) => total + score, 0) / scores.length
      : 0;
  };
  const professional = ratingAverage("professionalism");
  const teaching = ratingAverage("teaching_skill");
  const punctuality = ratingAverage("punctuality");
  const averageRating = reviewRows.length
    ? (professional + teaching + punctuality) / 3
    : Number(infoData.avg_rating || profile.average_rate || 0);
  const studentNumber = profile.student_number
    ? `${String(profile.student_number).slice(2)}학번`
    : "";

  async function toggleLike() {
    try {
      const result = await api(`/tutoring/instructors/${id}/like/`, {
        method: "POST",
      });
      const next = result.is_liked ?? !liked;
      setLiked(next);
      setLikeCount((count) => Math.max(0, count + (next ? 1 : -1)));
    } catch (error) {
      notify(error.message);
    }
  }

  return (
    <section className="teacher-profile-detail">
      <div className="teacher-profile-header">
        {profile.profile_image ? (
          <img src={profile.profile_image} alt="" className="avatar profile-avatar" />
        ) : (
          <span className="avatar profile-avatar">
            {(profile.user_name || "선").slice(0, 1)}
          </span>
        )}
        <div className="teacher-profile-identity">
          <h2>
            {profile.user_name || "선생님"}
            {profile.is_certified && <ShieldCheck size={17} aria-label="인증된 선생님" />}
          </h2>
          <p>{[profile.university, profile.department, studentNumber].filter(Boolean).join(" · ")}</p>
        </div>
        {user?.role === "student" && (
          <button
            type="button"
            className={"teacher-profile-like " + (liked ? "liked" : "")}
            aria-label={liked ? "선생님 찜 취소" : "선생님 찜하기"}
            onClick={toggleLike}
          >
            <Heart size={21} fill={liked ? "currentColor" : "none"} />
            <small>{likeCount}</small>
          </button>
        )}
      </div>
      <div className="teacher-profile-meta">
        {[profile.sex, age != null ? `만 ${age}세` : "", profile.region]
          .filter(Boolean)
          .join(" · ") || "정보 미입력"}
      </div>
      <Subjects values={profile.subjects} />
      {profile.instruction && (
        <p className="teacher-profile-introduction">
          선생님 한 줄 소개: {profile.instruction}
        </p>
      )}
      <State resource={info}>
        {info.data && (
          <section className="teacher-profile-stats">
            <div>
              <span>과외 상태</span>
              <strong>{infoData.is_tutoring ? "모집 중" : "구하지 않음"}</strong>
            </div>
            {infoData.is_tutoring && (
              <>
                <div>
                  <span>클래씨에서 과외 구한 건 수</span>
                  <strong>{infoData.tutoring_count ? `${infoData.tutoring_count}건` : "-"}</strong>
                </div>
                <div>
                  <span>평균 수업료</span>
                  <strong>{infoData.average_cost ? `${money(infoData.average_cost)}원` : "-"}</strong>
                </div>
                <div>
                  <span>과외 리뷰 평점</span>
                  <strong>{averageRating ? `${averageRating.toFixed(1)} (${reviewRows.length})` : "-"}</strong>
                </div>
                <div>
                  <span>클래씨 랭킹</span>
                  <strong>{infoData.current_rank ? `${infoData.current_rank}위` : "-"}</strong>
                </div>
              </>
            )}
          </section>
        )}
      </State>
      <div
        className="registration-tabs detail-tabs"
        role="tablist"
        aria-label="선생님 프로필 상세"
      >
        <button
          type="button"
          role="tab"
          aria-selected={tab === "lectures"}
          className={tab === "lectures" ? "active" : ""}
          onClick={() => setTab("lectures")}
        >
          강의
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "info"}
          className={tab === "info" ? "active" : ""}
          onClick={() => setTab("info")}
        >
          과외 정보
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "reviews"}
          className={tab === "reviews" ? "active" : ""}
          onClick={() => setTab("reviews")}
        >
          과외 리뷰
        </button>
      </div>
      {tab === "lectures" && (
        <State resource={lectures}>
          {list(lectures.data).length ? (
            <div className="teacher-profile-lectures">
              {list(lectures.data).map((lecture) => (
                <button
                  type="button"
                  key={lecture.id}
                  className="teacher-lecture-row"
                  onClick={() => detail("lectures", lecture.id, lecture)}
                >
                  {lecture.thumbnail ? (
                    <img src={lecture.thumbnail} alt="" />
                  ) : (
                    <span className="teacher-lecture-placeholder"><Play size={22} /></span>
                  )}
                  <span>
                    <b>{lecture.title}</b>
                    <small>
                      조회 {lecture.view_count || 0}회 · 찜 {lecture.like_count || 0}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="muted">강의가 아직 없어요.</p>
          )}
        </State>
      )}
      {tab === "info" && (
        <State resource={info}>
          {info.data && (
            <dl className="class-info-list post-detail-list">
              <div>
                <dt>수업 과목</dt>
                <dd>{textLabels(infoData.subjects) || "협의"}</dd>
              </div>
              <div>
                <dt>수업 일정</dt>
                <dd>{infoData.schedule || "일정 협의 필요"}</dd>
              </div>
              <div>
                <dt>수업료</dt>
                <dd>{infoData.cost != null ? `월 ${money(infoData.cost)}원 이하` : "협의 후 결정"}</dd>
              </div>
              <div>
                <dt>수업 방식</dt>
                <dd>{methodLabel(infoData.method)}</dd>
              </div>
              <div>
                <dt>수업 가능 지역</dt>
                <dd>{textLabels(infoData.regions) || infoData.location || "협의"}</dd>
              </div>
              {infoData.etc && (
                <div>
                  <dt>기타</dt>
                  <dd>{infoData.etc}</dd>
                </div>
              )}
            </dl>
          )}
        </State>
      )}
      {tab === "reviews" && (
        <State resource={reviews}>
          {reviewRows.length ? (
            <>
              <section className="teacher-review-summary">
                <b>{averageRating.toFixed(1)} / 5</b>
                <span>({reviewRows.length})</span>
                <div>
                  <span>전문성 {professional.toFixed(1)}</span>
                  <span>강의력 {teaching.toFixed(1)}</span>
                  <span>시간 준수 {punctuality.toFixed(1)}</span>
                </div>
              </section>
              <div className="review-list">
                {reviewRows.map((review) => (
                  <article className="comment teacher-review-card" key={review.id}>
                    <div className="teacher-review-author">
                      {review.student_profile_image ? (
                        <img src={review.student_profile_image} alt="" className="avatar" />
                      ) : (
                        <span className="avatar">{(review.student_label || "학").slice(0, 1)}</span>
                      )}
                      <div>
                        <b>{review.student_label || "학생"}</b>
                        <small>{[review.class_type, review.created_at ? date(review.created_at) : ""].filter(Boolean).join(" · ")}</small>
                      </div>
                    </div>
                    <Subjects values={review.subjects} />
                    <p>{review.comment}</p>
                    <div className="teacher-review-scores">
                      <span>전문성 {review.professionalism}점</span>
                      <span>강의력 {review.teaching_skill}점</span>
                      <span>시간 준수 {review.punctuality}점</span>
                    </div>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <p className="muted">아직 리뷰가 없어요.</p>
          )}
        </State>
      )}
    </section>
  );
}
function Comments({ id }) {
  const [commentPage, setCommentPage] = useState(1);
  const resource = useLoad(`/lectures/${id}/comments/?page=${commentPage}`);
  const { notify } = useContext(Ctx);
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const content = new FormData(form).get("content").trim();
    if (!content) return;
    setBusy(true);
    try {
      await api(`/lectures/${id}/comments/`, {
        method: "POST",
        body: { content },
      });
      form.reset();
      resource.reload();
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="comments">
      <h3>강의 이야기</h3>
      <State resource={resource}>
        {list(resource.data).map((c) => (
          <CommentRow
            key={c.id}
            comment={c}
            lecture={id}
            reload={resource.reload}
          />
        ))}
      </State>
      <div className="actions">
        {commentPage > 1 && (
          <Btn onClick={() => setCommentPage((p) => p - 1)}>이전 댓글</Btn>
        )}
        {resource.data?.next && (
          <Btn onClick={() => setCommentPage((p) => p + 1)}>다음 댓글</Btn>
        )}
      </div>
      <form onSubmit={submit} className="inline-form">
        <input
          name="content"
          aria-label="댓글"
          placeholder="강의에 대한 생각을 남겨보세요"
          required
          maxLength={2000}
        />
        <Btn disabled={busy}>등록</Btn>
      </form>
    </div>
  );
}
function CommentRow({ comment: c, lecture, reload, reply = false }) {
  const { notify } = useContext(Ctx),
    [mode, setMode] = useState(""),
    [text, setText] = useState(""),
    [busy, setBusy] = useState(false);
  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api(
        mode === "edit"
          ? `/lectures/comments/${c.id}/`
          : `/lectures/${lecture}/comments/`,
        {
          method: mode === "edit" ? "PATCH" : "POST",
          body: {
            content: text,
            ...(mode === "reply"
              ? { parent: c.parent || c.id, referenced_person: c.author }
              : {}),
          },
        },
      );
      setMode("");
      reload();
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="comment">
      <b>{c.author_name || "수강생"}</b>
      <small>{date(c.created_at)}</small>
      <p>{c.content}</p>
      <div className="actions">
        <button
          className="text-button"
          onClick={() => {
            setMode("reply");
            setText("");
          }}
        >
          답글
        </button>
        {c.is_mine && (
          <>
            <button
              className="text-button"
              onClick={() => {
                setMode("edit");
                setText(c.content);
              }}
            >
              수정
            </button>
            <button
              className="text-button"
              disabled={busy}
              onClick={async () => {
                if (!window.confirm("댓글을 삭제할까요?")) return;
                setBusy(true);
                try {
                  await api(`/lectures/comments/${c.id}/`, {
                    method: "DELETE",
                  });
                  reload();
                } catch (e) {
                  notify(e.message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              삭제
            </button>
          </>
        )}
      </div>
      {mode && (
        <form className="inline-form" onSubmit={save}>
          <input
            aria-label={mode === "edit" ? "댓글 수정" : "답글 내용"}
            value={text}
            onChange={(e) => setText(e.target.value)}
            required
            maxLength={2000}
          />
          <Btn disabled={busy}>저장</Btn>
          <Btn type="button" onClick={() => setMode("")}>
            취소
          </Btn>
        </form>
      )}
      {!c.is_mine && <ReportForm source="comment" id={c.id} />}{" "}
      {!reply &&
        c.replies?.map((r) => (
          <CommentRow
            key={r.id}
            comment={r}
            lecture={lecture}
            reload={reload}
            reply
          />
        ))}
    </article>
  );
}
function Notifications() {
  const [notificationPage, setNotificationPage] = useState(1);
  const {
    notify,
    user,
    openNotificationTarget,
    refreshNotificationUnreadCount,
  } = useContext(Ctx);
  const r = useLoad(
    `/notification/?page=${notificationPage}&role=${user.role}`,
  );

  async function openNotification(notification) {
    try {
      await api(`/notification/${notification.id}/read/`, { method: "PATCH" });
      refreshNotificationUnreadCount();
      if (!openNotificationTarget(notification)) r.reload();
    } catch (e) {
      notify(e.message);
    }
  }

  return (
    <>
      <div className="actions">
        <Btn
          onClick={async () => {
            try {
              await api(`/notification/read-all/?role=${user.role}`, {
                method: "PATCH",
              });
              refreshNotificationUnreadCount();
              r.reload();
            } catch (e) {
              notify(e.message);
            }
          }}
        >
          모두 읽음
        </Btn>
        {notificationPage > 1 && (
          <Btn onClick={() => setNotificationPage((p) => p - 1)}>이전</Btn>
        )}
        {r.data?.next && (
          <Btn onClick={() => setNotificationPage((p) => p + 1)}>다음</Btn>
        )}
      </div>
      <State resource={r}>
        {list(r.data).length ? (
          <div className="notification-list">
            {list(r.data).map((n) => (
              <div key={n.id} className="notification-row">
                <button
                  key={n.id}
                  className={"notification " + (n.is_read ? "read" : "")}
                  onClick={() => openNotification(n)}
                >
                  <Bell size={20} />
                  <span>
                    <b>{n.title}</b>
                    <p>{n.body}</p>
                    <small>{date(n.created_at)}</small>
                  </span>
                  {!n.is_read && <span className="unread-dot" />}
                </button>
                <button
                  className="text-button"
                  aria-label="알림 삭제"
                  onClick={async () => {
                    try {
                      await api(`/notification/${n.id}/`, { method: "DELETE" });
                      refreshNotificationUnreadCount();
                      r.reload();
                    } catch (e) {
                      notify(e.message);
                    }
                  }}
                >
                  삭제
                </button>
              </div>
            ))}
          </div>
        ) : (
          <Empty
            icon={Bell}
            title="새로운 알림이 없어요"
            text="수업과 대화에 관한 소식을 이곳에서 알려드릴게요."
          />
        )}
      </State>
    </>
  );
}
function Chat({ initialRoomId }) {
  const { user, notify } = useContext(Ctx);
  const rooms = useLoad("/chatrooms/?role=" + user.role);
  const [selected, setSelected] = useState(null),
    [room, setRoom] = useState(null),
    [error, setError] = useState(""),
    [text, setText] = useState(""),
    [busy, setBusy] = useState(false);
  const registrationResource = useLoad(
    selected ? `/tutoring/resources/chatrooms/${selected}/` : null,
    [selected],
    { keepDataOnReload: true },
  );
  const registrationData =
    Number(registrationResource.data?.chatRoomId) === selected
      ? registrationResource.data
      : null;
  const registrationComplete = registrationData
    ? registrationStatus(registrationData).isComplete
    : false;
  const end = useRef();
  const lastRead = useRef("");
  const [registration, setRegistration] = useState(false);
  useEffect(() => {
    if (!initialRoomId) return;
    const targetRoom = list(rooms.data).find(
      (item) => String(item.id) === initialRoomId,
    );
    if (!targetRoom) return;

    setSelected(targetRoom.id);
    setText("");
    setRegistration(false);
  }, [initialRoomId, rooms.data]);
  useEffect(() => {
    if (!selected) return;
    let alive = true,
      controller = new AbortController();
    setRoom(null);
    setError("");
    const load = () => {
      if (document.hidden) return;
      api(`/chatrooms/${selected}/?role=${user.role}`, {
        signal: controller.signal,
      })
        .then((d) => {
          if (alive) {
            setRoom(d);
            setError("");
            const latest = d.messages?.at(-1);
            const key = selected + ":" + latest?.id;
            if (latest && lastRead.current !== key) {
              lastRead.current = key;
              api(`/chatrooms/${selected}/read/${latest.id}/`, {
                method: "POST",
                body: {},
              })
                .then(() => {
                  if (alive) rooms.reload();
                })
                .catch(() => {
                  lastRead.current = "";
                });
            }
          }
        })
        .catch((e) => {
          if (alive && !controller.signal.aborted) setError(e.message);
        });
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      controller.abort();
      clearInterval(timer);
    };
  }, [selected, user.role]);
  useEffect(() => {
    if (!selected || registration) return undefined;
    const timer = window.setInterval(() => registrationResource.reload(), 10000);
    return () => window.clearInterval(timer);
  }, [selected, registration]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [room?.messages?.length]);
  async function send(e) {
    e.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      const m = await api(`/chatrooms/${selected}/message/`, {
        method: "POST",
        body: { text: text.trim() },
      });
      setRoom((r) => ({ ...r, messages: [...(r.messages || []), m] }));
      setText("");
      rooms.reload();
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="chat-layout">
        <div className="room-list">
          <h3>나의 대화</h3>
          <State resource={rooms}>
            {list(rooms.data).map((r) => (
              <button
                key={r.id}
                className={selected === r.id ? "selected" : ""}
                onClick={() => {
                  setSelected(r.id);
                  setText("");
                  setRegistration(false);
                }}
              >
                <span className="avatar">
                  <MessageCircle size={18} />
                </span>
                <span>
                  <b>
                    {r.opponent_info?.nickname ||
                      r.opponent_info?.user_name ||
                      r.title ||
                      "대화"}
                  </b>
                  <small>
                    {r.last_message?.text || "대화를 시작해 보세요"}
                  </small>
                </span>
                {r.not_read_count > 0 && <em>{r.not_read_count}</em>}
              </button>
            ))}
            {!list(rooms.data).length && (
              <p className="muted room-empty">아직 시작한 대화가 없어요.</p>
            )}
          </State>
        </div>
        <div className="conversation">
          {!selected ? (
            <Empty
              icon={MessageCircle}
              title="대화를 선택해 주세요"
              text="앱에서 나누던 대화를 웹에서도 이어갈 수 있어요."
            />
          ) : (
            <>
              <div className="conversation-head">
                <b>
                  {room?.opponent_info?.nickname ||
                    room?.opponent_info?.user_name ||
                    room?.title ||
                    "대화"}
                </b>
                <div className="actions">
                  <Btn
                    disabled={!room || registrationResource.loading}
                    onClick={() => setRegistration(true)}
                  >
                    {registrationComplete ? "수업 정보" : "성사 등록"}
                  </Btn>
                  <Btn
                    disabled={!room}
                    onClick={async () => {
                      try {
                        const d = await api(`/chatrooms/${selected}/like/`, {
                          method: "POST",
                          body: {},
                        });
                        notify(
                          d.is_liked
                            ? "대화를 즐겨찾기에 추가했습니다."
                            : "즐겨찾기를 해제했습니다.",
                        );
                        rooms.reload();
                      } catch (e) {
                        notify(e.message);
                      }
                    }}
                  >
                    즐겨찾기
                  </Btn>
                  <Btn
                    disabled={!room?.opponent_info?.user_id}
                    onClick={async () => {
                      if (
                        !window.confirm(
                          "상대방을 차단할까요? 차단 관리는 계정 관리에서 할 수 있습니다.",
                        )
                      )
                        return;
                      try {
                        await api("/blocks/", {
                          method: "POST",
                          body: { blocked_user: room.opponent_info.user_id },
                        });
                        setSelected(null);
                        rooms.reload();
                        notify("상대방을 차단했습니다.");
                      } catch (e) {
                        notify(e.message);
                      }
                    }}
                  >
                    차단
                  </Btn>
                  <Btn
                    disabled={!room}
                    onClick={async () => {
                      try {
                        const d = await api(`/chatrooms/${selected}/mute/`, {
                          method: "POST",
                        });
                        notify(
                          d.is_muted
                            ? "대화 알림을 껐습니다."
                            : "대화 알림을 켰습니다.",
                        );
                        rooms.reload();
                      } catch (e) {
                        notify(e.message);
                      }
                    }}
                  >
                    알림 설정
                  </Btn>
                  <Btn
                    disabled={!room}
                    onClick={async () => {
                      if (
                        !window.confirm(
                          "채팅방을 삭제하고 나갈까요? 상대방의 대화도 삭제됩니다.",
                        )
                      )
                        return;
                      try {
                        await api(`/chatrooms/${selected}/out/`, {
                          method: "DELETE",
                        });
                        setSelected(null);
                        rooms.reload();
                      } catch (e) {
                        notify(e.message);
                      }
                    }}
                  >
                    나가기
                  </Btn>
                </div>
              </div>
              {error && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}
              <div className="messages">
                {!room && !error && (
                  <div className="loading">
                    <LoaderCircle className="spin" />
                  </div>
                )}
                {room?.messages?.map((m) => (
                  <div
                    key={m.id}
                    className={
                      "message " + (m.sender === user.id ? "mine" : "")
                    }
                  >
                    <small>{m.sender_nickname}</small>
                    {m.text && <p>{m.text}</p>}
                    {m.images?.map((img) => (
                      <a
                        href={img.image}
                        key={img.id}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <img src={img.image} alt="대화 첨부 이미지" />
                      </a>
                    ))}
                    <time>
                      {m.created_at
                        ? new Date(m.created_at).toLocaleTimeString("ko-KR", {
                            hour: "2-digit",
                            minute: "2-digit",
                          })
                        : ""}
                    </time>
                  </div>
                ))}
                <div ref={end} />
              </div>
              <form onSubmit={send} className="message-form">
                <input
                  aria-label="메시지"
                  placeholder="메시지를 입력하세요"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  maxLength={5000}
                  disabled={!room}
                />
                <Btn
                  className="primary"
                  disabled={busy || !text.trim() || !room}
                  aria-label="메시지 보내기"
                >
                  <Send size={18} />
                </Btn>
              </form>
              <ReportForm source="chat" id={selected} />
            </>
          )}
        </div>
      </div>
      {registration && room && (
        <Registration
          room={room}
          onClose={() => {
            setRegistration(false);
            registrationResource.reload();
          }}
          onUpdated={registrationResource.reload}
        />
      )}
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
