import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  createContext,
  useContext,
} from "react";
import { createRoot } from "react-dom/client";
import {
  BookOpen,
  Ban,
  MapPin,
  UserRound,
  ArrowUpRight,
  ArrowRight,
  Search,
  Home,
  Users,
  Play,
  Eye,
  Star,
  ThumbsUp,
  MessageCircle,
  Heart,
  Info,
  Bell,
  BellOff,
  Settings,
  LogOut,
  X,
  Menu,
  ChevronRight,
  ChevronDown,
  ChevronLeft,
  GraduationCap,
  ShieldCheck,
  SlidersHorizontal,
  Send,
  RefreshCw,
  LockKeyhole,
  LoaderCircle,
  Upload,
  Leaf,
  MoreVertical,
  Pencil,
  Trash2,
} from "lucide-react";
import { api, list, sendSupportMessageViaWebSocket, subscribeWebSocket } from "./api";
import { Auth } from "./auth";
import { Studio } from "./studio";
import { ClassInformationModal, registrationStatus } from "./contracts";
import { Services, ReportForm, StudentPostEditorPage, VerificationPage } from "./services";
import { RegistrationPage } from "./registration-page";
import { TutoringProfilePage } from "./tutoring-profile-page";
import "./redesign.css";
import {
  Ctx,
  money,
  date,
  formatLectureCount,
  formatLectureTimeAgo,
  formatVideoDuration,
  useLoad,
  Btn,
  Empty,
  State,
  Gate,
  Modal,
  ConfirmDialog,
  Subjects,
  MobileBackAction,
} from "./shared";
import {
  Shell,
  PageHeading,
  HomePage,
  NoticePage,
  Catalog,
  Profile,
  ProfileEdit,
  Avatar,
  endpoints,
  pageNames,
} from "./design";
import { getMobileStoreUrl } from "./app_download";
import { LandingPage } from "./landing";
import { getLatestClassResource } from "./tutoring-state";
import { isPublicId, parseRoute, pathFor, pushPath } from "./router";

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

const lectureCommentNotificationTypes = new Set([
  "lecture_comment",
  "lecture_comment_reply",
]);

const authPageModes = {
  "/login": "login",
  "/signup": "signup",
  "/password-reset": "reset",
};

/** Resolve a historical numeric hash target without ever placing its PK in a new URL. */
async function resolveLegacyPath(target) {
  const [page, id, segment, nestedId] = String(target || "").split("/");
  if (!id || isPublicId(id)) return pathFor(target);
  try {
    if (page === "lecture") {
      const detail = await api(`/lectures/${id}/`);
      const lectureId = detail.lecture_info?.public_id;
      if (!lectureId) return "/home";
      if (segment !== "comment" || !nestedId) return `/lectures/${lectureId}`;
      const comments = list(await api(`/lectures/${id}/comments/`));
      const comment = comments
        .flatMap((row) => [row, ...list(row.replies)])
        .find((row) => String(row.id) === nestedId);
      return comment?.public_id
        ? `/lectures/${lectureId}?comment=${encodeURIComponent(comment.public_id)}`
        : `/lectures/${lectureId}`;
    }
    if (page === "teacher-profile") {
      const instructor = await api(`/tutoring/instructors/${id}/`);
      return instructor.public_id ? `/instructors/${instructor.public_id}` : "/instructors";
    }
    if (page === "tutoring-post-detail" || page === "tutoring-post") {
      const post = await api(`/tutoring/posts/${id}/`);
      if (!post.public_id) return "/tutoring-posts";
      return page === "tutoring-post"
        ? `/tutoring-posts/${post.public_id}/edit`
        : `/tutoring-posts/${post.public_id}`;
    }
    if (page === "notices") {
      const notice = await api(`/notices/${id}/`);
      return notice.public_id ? `/notices/${notice.public_id}` : "/notices";
    }
    if (page === "chat" || page === "tutoring-registration") {
      const room = await api(`/chatrooms/${id}/`);
      if (!room.public_id) return "/messages";
      if (page === "tutoring-registration") {
        return `/messages/${room.public_id}/registration${segment === "proof" ? "/proof" : ""}`;
      }
      return `/messages/${room.public_id}`;
    }
  } catch {
    return "/home";
  }
  return pathFor(target);
}

function App() {
  const uploadLock = useRef(false);
  const [activeRole, setActiveRole] = useState(
    sessionStorage.getItem("classy_role") || "",
  );
  const [user, setUser] = useState(null),
    [ready, setReady] = useState(false);
  const [route, setRoute] = useState(() => parseRoute());
  const page = route.page;
  const [modal, setModal] = useState(null),
    [toast, setToast] = useState("");
  const [pendingChatRoomId, setPendingChatRoomId] = useState(null);
  const [postListItem, setPostListItem] = useState(null);
  const [teacherProfileReturn, setTeacherProfileReturn] = useState(null);
  const pageRef = useRef(page);
  const pendingTeacherProfileNavigation = useRef(null);
  pageRef.current = page;
  const activeUserRole = activeRole || user?.role;
  // A teacher's lecture destination is their own Studio, never the public catalog.
  // Resolve it before rendering so a direct #lectures URL cannot mount Catalog first.
  const displayPage =
    activeUserRole === "instructor" && page === "lectures" ? "studio" : page;
  const subjects = useLoad("/accounts/subjects/");
  const hasAuthenticatedSession = Boolean(
    user && sessionStorage.getItem("classy_token"),
  );
  const unreadNotifications = useLoad(
    hasAuthenticatedSession ? "/notification/unread-count/" : null,
    [user?.id],
  );
  const notify = (msg) => setToast(msg);
  useEffect(() => {
    const publicId = route.params.publicId;
    const roomPublicId = route.params.roomPublicId;
    let legacyTarget = "";

    if (page === "lecture" && publicId && !isPublicId(publicId)) {
      legacyTarget = `lecture/${publicId}`;
    } else if (page === "teacher-profile" && publicId && !isPublicId(publicId)) {
      legacyTarget = `teacher-profile/${publicId}`;
    } else if (page === "tutoring-post-detail" && publicId && !isPublicId(publicId)) {
      legacyTarget = `tutoring-post-detail/${publicId}`;
    } else if (page === "notices" && publicId && !isPublicId(publicId)) {
      legacyTarget = `notices/${publicId}`;
    } else if (page === "chat" && roomPublicId && !isPublicId(roomPublicId)) {
      legacyTarget = `chat/${roomPublicId}`;
    } else if (page === "tutoring-registration" && roomPublicId && !isPublicId(roomPublicId)) {
      legacyTarget = `tutoring-registration/${roomPublicId}/${route.params.step === "proof" ? "proof" : ""}`;
    } else if (page === "tutoring-post" && route.params.postId && route.params.postId !== "new" && !isPublicId(route.params.postId)) {
      legacyTarget = `tutoring-post/${route.params.postId}`;
    }

    if (!legacyTarget) return;
    resolveLegacyPath(legacyTarget).then((destination) => {
      if (destination !== location.pathname + location.search) {
        location.replace(destination);
      }
    });
  }, [page, route.params.postId, route.params.publicId, route.params.roomPublicId, route.params.step]);
  useEffect(() => {
    if (location.pathname !== "/download") return;

    const storeUrl = getMobileStoreUrl();
    if (storeUrl) {
      location.replace(storeUrl);
      return;
    }

    location.replace("/home");
  }, []);
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
        history.replaceState(null, "", pathFor(pageRef.current));
        notify("강의 등록이 완료될 때까지 기다려 주세요.");
        return;
      }
      const nextRoute = parseRoute();
      const targetInstructorId = nextRoute.params.publicId || "";
      if (
        nextRoute.page !== "teacher-profile" ||
        targetInstructorId !== pendingTeacherProfileNavigation.current
      ) {
        setTeacherProfileReturn(null);
      }
      pendingTeacherProfileNavigation.current = null;
      setRoute(nextRoute);
      setModal(null);
      window.scrollTo(0, 0);
    };
    window.addEventListener("popstate", change);
    return () => window.removeEventListener("popstate", change);
  }, []);
  useEffect(() => {
    if (displayPage !== page) {
      pushPath(pathFor(displayPage), { replace: true });
    }
  }, [displayPage, page]);
  useEffect(() => {
    document.title = (pageNames[displayPage] || "홈") + " | CLASSY";
  }, [displayPage]);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(""), 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  useEffect(() => {
    if (!hasAuthenticatedSession) return undefined;

    const refresh = () => {
      if (sessionStorage.getItem("classy_token")) unreadNotifications.reload();
    };
    const timer = window.setInterval(refresh, 30000);
    window.addEventListener("focus", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [hasAuthenticatedSession, user?.id]);
  const go = async (p) => {
    if (String(p).startsWith("/")) {
      pushPath(p);
      return;
    }
    const [targetPage, ...segments] = p.split("/");
    const destination =
      activeUserRole === "instructor" && targetPage === "lectures"
        ? ["studio", ...segments].join("/")
        : p;
    const path = await resolveLegacyPath(destination);
    pushPath(path);
  };
  const openChat = (room) => {
    const publicId =
      typeof room === "object" ? room?.public_id : isPublicId(room) ? room : "";
    setPendingChatRoomId(publicId || null);
    go(publicId ? `chat/${publicId}` : "chat");
  };
  const closeChatRoom = () => {
    setPendingChatRoomId(null);
    go("chat");
  };
  const openPostDetail = (item) => {
    setPostListItem(item || null);
    go(`tutoring-post-detail/${item.public_id}`);
  };
  const openTeacherProfile = (instructor) => {
    const publicId =
      typeof instructor === "object"
        ? instructor?.public_id
        : isPublicId(instructor)
          ? instructor
          : "";
    if (!publicId) {
      notify("운영자 프로필을 찾을 수 없어요.");
      return;
    }
    setTeacherProfileReturn({
      instructorId: publicId,
      page: location.pathname || "/home",
    });
    pendingTeacherProfileNavigation.current = publicId;
    go(`teacher-profile/${publicId}`);
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
      const roomPublicId = notification?.data?.room_public_id?.toString();
      const roomId = notification?.data?.room_id?.toString();
      if (!roomPublicId && !roomId) return false;
      openChat(roomPublicId || roomId);
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

    if (notification?.type === "support_ticket") {
      go("support");
      return true;
    }

    if (lectureCommentNotificationTypes.has(notification?.type)) {
      const lectureId =
        notification?.data?.lecture_public_id?.toString() ||
        notification?.data?.lecture_id?.toString();
      if (!lectureId) return false;
      setToast("");
      const commentId =
        notification?.data?.parent_comment_public_id?.toString() ||
        notification?.data?.comment_public_id?.toString() ||
        notification?.data?.parent_comment_id?.toString() ||
        notification?.data?.comment_id?.toString();
      go(commentId ? `lecture/${lectureId}/comment/${commentId}` : `lecture/${lectureId}`);
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
    ? { ...user, role: activeUserRole }
    : null;
  const unreadNotificationCount = Number(
    unreadNotifications.data?.[effectiveUser?.role],
  ) || 0;
  const context = {
    user: effectiveUser,
    route,
    setUser,
    toast,
    subjects: list(subjects.data),
    notify,
    go,
    openTeacherProfile,
    openChat,
    openPostDetail,
    login: () => location.assign("/login"),
    detail: (kind, id, item) => {
      setToast("");
      if (kind === "teachers") {
        openTeacherProfile(item || { public_id: id });
        return;
      }
      if (kind === "posts") {
        openPostDetail(item || { public_id: id });
        return;
      }
      go(`lecture/${item?.public_id || id}`);
    },
    refreshUser: () => api("/accounts/me/").then(setUser),
    unreadNotificationCount,
    refreshNotificationUnreadCount: () => {
      if (sessionStorage.getItem("classy_token")) unreadNotifications.reload();
    },
    setRole: (role) => changeRole(role),
    openNotificationTarget,
    signup: () => location.assign("/signup"),
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
  const authPageMode = authPageModes[location.pathname];
  if (authPageMode)
    return (
      <Ctx.Provider value={context}>
        <Auth initial={authPageMode} />
      </Ctx.Provider>
    );
  if (page === "tutoring-post") {
    const postId = route.params.postId || "new";
    const returnTo = route.query.get("returnTo") || "";
    return (
      <Ctx.Provider value={context}>
        <Shell
          page={page}
          activeRole={activeRole}
          setActiveRole={changeRole}
          fullBleed
        >
          {!ready ? (
            <div className="loading">
              <LoaderCircle className="spin" />
              계정을 확인하고 있어요
            </div>
          ) : (
            <Gate>
              <StudentPostEditorPage
                postId={postId}
                returnTo={returnTo}
              />
            </Gate>
          )}
        </Shell>
      </Ctx.Provider>
    );
  }
  if (page === "tutoring-registration") {
    return (
      <Ctx.Provider value={context}>
        <Shell
          page={page}
          activeRole={activeRole}
          setActiveRole={changeRole}
          fullBleed
        >
          {!ready ? (
            <div className="loading">
              <LoaderCircle className="spin" />
              계정을 확인하고 있어요
            </div>
          ) : (
            <Gate>
              <RegistrationPage roomId={route.params.roomPublicId} />
            </Gate>
          )}
        </Shell>
      </Ctx.Provider>
    );
  }
  if (page === "tutoring-profile") {
    return (
      <Ctx.Provider value={context}>
        <Shell
          page={page}
          activeRole={activeRole}
          setActiveRole={changeRole}
          fullBleed
        >
          {!ready ? (
            <div className="loading">
              <LoaderCircle className="spin" />
              정보를 확인하고 있어요.
            </div>
          ) : (
            <Gate>
              <TutoringProfilePage />
            </Gate>
          )}
        </Shell>
      </Ctx.Provider>
    );
  }
  if (page === "verification") {
    return (
      <Ctx.Provider value={context}>
        <Shell
          page={page}
          activeRole={activeRole}
          setActiveRole={changeRole}
          fullBleed
        >
          {!ready ? (
            <div className="loading">
              <LoaderCircle className="spin" />
              정보를 확인하고 있어요.
            </div>
          ) : (
            <Gate>
              <VerificationPage />
            </Gate>
          )}
        </Shell>
      </Ctx.Provider>
    );
  }
  return (
    <Ctx.Provider value={context}>
      <Shell page={displayPage} activeRole={activeRole} setActiveRole={changeRole}>
        {!ready ? (
          <div className="loading">
            <LoaderCircle className="spin" />
            계정을 확인하고 있어요
          </div>
        ) : displayPage === "home" ? (
          <HomePage />
        ) : displayPage === "profile" ? (
          <Gate>
            <Profile onLogout={logout} />
          </Gate>
        ) : displayPage === "profile-edit" ? (
          <Gate>
            <ProfileEdit />
          </Gate>
        ) : displayPage === "teacher-profile" ? (
          <Gate>
            <TeacherProfilePage
              id={route.params.publicId}
              officialReturnTo={
                teacherProfileReturn?.instructorId ===
                route.params.publicId
                  ? teacherProfileReturn.page
                  : ""
              }
              onOfficialReturnHandled={() => setTeacherProfileReturn("")}
            />
          </Gate>
        ) : displayPage === "lecture" ? (
          <Gate>
            <LecturePage
              id={route.params.publicId}
              initialExpandedCommentId={route.query.get("comment")}
            />
          </Gate>
        ) : displayPage === "tutoring-post-detail" ? (
          <Gate>
            <TutoringPostPage
              id={route.params.publicId}
              listItem={postListItem}
            />
          </Gate>
        ) : displayPage === "notices" ? (
          <NoticePage />
        ) : displayPage === "notifications" ? (
          <>
            <PageHeading title="알림" />
            <Gate>
              <Notifications />
            </Gate>
          </>
        ) : displayPage === "chat" ? (
          <>
            <PageHeading
              title="채팅"
              description="진행 중인 상담과 수업 이야기를 확인하세요."
            />
            <Gate>
              <Chat
                initialRoomId={
                  route.params.roomPublicId || pendingChatRoomId
                }
                onRoomClosed={closeChatRoom}
              />
            </Gate>
          </>
        ) : displayPage === "not-found" ? (
          <Empty
            title="페이지를 찾을 수 없어요"
            text="주소를 다시 확인하거나 홈으로 돌아가 주세요."
          >
            <Btn className="primary" onClick={() => go("home")}>홈으로</Btn>
          </Empty>
        ) : ["upload", "studio"].includes(displayPage) ? (
          <Gate>
            <Studio key={displayPage} upload={displayPage === "upload"} />
          </Gate>
        ) : [
            "cash",
            "settlement",
            "account",
            "tutoring-manage",
            "support",
          ].includes(displayPage) ? (
          <Gate>
            <Services key={displayPage} page={displayPage} onLogout={logoutLocal} />
          </Gate>
        ) : (
          <>
            <PageHeading title={pageNames[displayPage]} />
            {displayPage === "lectures" ? (
              <Gate>
                <Catalog
                  key={displayPage + effectiveUser?.role}
                  kind="lectures"
                  mode={displayPage}
                />
              </Gate>
            ) : (
              <Catalog
                key={displayPage + effectiveUser?.role}
                kind={
                  displayPage === "saved-teachers"
                    ? "teachers"
                    : ["teachers", "posts"].includes(displayPage)
                      ? displayPage
                      : "lectures"
                }
                mode={displayPage}
              />
            )}
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
      {modal?.type === "detail" && (
        <Detail
          kind={modal.kind}
          id={modal.id}
          item={modal.item}
          initialExpandedCommentId={modal.initialExpandedCommentId}
          onClose={() => setModal(null)}
        />
      )}
    </Ctx.Provider>
  );
}
function Detail({ kind, id, item, initialExpandedCommentId, onClose }) {
  const { notify, user, refreshUser } = useContext(Ctx);
  const base = (endpoints[kind] || "/lectures/") + id + "/";
  const resource = useLoad(base);
  const [busy, setBusy] = useState(false),
    [video, setVideo] = useState(""),
    [liked, setLiked] = useState(null),
    [rented, setRented] = useState(false),
    [rentConfirm, setRentConfirm] = useState(false),
    [instructorPurchaseNotice, setInstructorPurchaseNotice] = useState(false),
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
            ? "선생님 프로필"
            : "과외 모집 상세"
      }
      onClose={onClose}
      wide
      className={isTeacher ? "teacher-profile-modal" : ""}
      scrollable={isTeacher}
    >
      <State resource={resource}>
        {video ? (
          <video
            className="video"
            controls
            controlsList="nodownload"
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
                <ThumbsUp
                  size={17}
                  fill={(liked ?? d.is_liked) ? "currentColor" : "none"}
                />
                추천
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
                  <Btn
                    disabled={busy}
                    onClick={() =>
                      user?.role === "instructor"
                        ? setInstructorPurchaseNotice(true)
                        : setRentConfirm(true)
                    }
                  >
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
                        if (user?.role === "instructor") {
                          setRentConfirm(false);
                          setInstructorPurchaseNotice(true);
                          return;
                        }
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
            {instructorPurchaseNotice && (
              <div className="confirm-box" role="alert">
                <b>학생 계정으로 전환 후 강의를 구매해 주세요.</b>
                <div className="actions">
                  <Btn onClick={() => setInstructorPurchaseNotice(false)}>
                    확인
                  </Btn>
                </div>
              </div>
            )}
            <p className="form-note">
              보유 캐시는 기존 계정과 연동됩니다. 마이페이지의 캐시 관리에서
              캐시 잔액과 이용 내역을 확인하세요.
            </p>
            <Comments
              id={id}
              initialExpandedCommentId={initialExpandedCommentId}
            />
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
            <ProfileSafetyActions
              instructorId={id}
              userId={d.user || item?.user}
              teacherName={d.user_name || item?.user_name || "선생님"}
              onBlocked={onClose}
            />
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
        {!isTeacher && (
          <ReportForm
            source={kind === "lectures" ? "lecture" : "tutoring_post"}
            id={id}
          />
        )}
      </State>
    </Modal>
  );
}
/** 앱 강의 플레이어 상세 구조를 웹의 전용 페이지로 옮긴 화면이다. */
function LecturePage({ id, initialExpandedCommentId }) {
  const { go, notify, refreshUser, subjects, user, openTeacherProfile } = useContext(Ctx);
  const resource = useLoad(
    isPublicId(id) ? `/lectures/public/${id}/` : null,
    [id],
  );
  const detail = resource.data || {};
  const instructorId = detail.lecture_info?.instructor?.id;
  const instructorLecturesResource = useLoad(
    instructorId ? `/lectures/?instructor=${instructorId}&page=1` : null,
    [instructorId],
  );
  const otherLecturesResource = useLoad(
    Number.isInteger(id) && id > 0 ? "/lectures/?page=1" : null,
    [id],
  );
  const [busy, setBusy] = useState(false);
  const [video, setVideo] = useState("");
  const [liked, setLiked] = useState(null);
  const [rented, setRented] = useState(false);
  const [rentConfirm, setRentConfirm] = useState(false);
  const [instructorPurchaseNotice, setInstructorPurchaseNotice] = useState(false);

  if (!isPublicId(id)) {
    return (
      <Empty
        title="강의를 찾을 수 없어요"
        text="강의 목록에서 다시 선택해 주세요."
      >
        <Btn onClick={() => go("lectures")}>강의 목록으로</Btn>
      </Empty>
    );
  }

  const lecture = detail.lecture_info || {};
  const lectureId = lecture.id;
  const instructor = lecture.instructor || {};
  const rentalStatus = rented ? "valid" : detail.rental_status;
  const isRented = ["active", "valid"].includes(rentalStatus);
  const isPaid = Number(lecture.price) > 0;
  const isLiked = liked ?? Boolean(lecture.is_liked);
  const likeCount = Math.max(
    0,
    Number(lecture.like_count || 0) +
      (liked == null || isLiked === Boolean(lecture.is_liked)
        ? 0
        : isLiked
          ? 1
          : -1),
  );
  const academicInfo = [
    instructor.university,
    [
      instructor.department,
      instructor.student_number
        ? `${String(instructor.student_number).slice(-2)}학번`
        : "",
    ]
      .filter(Boolean)
      .join(" "),
  ].filter(Boolean);
  const recommended = list(detail.recommended).filter(
    (item) => item.public_id !== id,
  );
  const loadedInstructorLectures = list(instructorLecturesResource.data)
    .filter((item) => item.public_id !== id)
    .slice(0, 4);
  const instructorLectures = (
    loadedInstructorLectures.length
      ? loadedInstructorLectures
      : recommended.filter(
          (item) => Number(item.instructor?.id) === Number(instructor.id),
        )
  ).slice(0, 4);
  const otherLectures = list(otherLecturesResource.data)
    .filter(
      (item) =>
        item.public_id !== id && Number(item.instructor?.id) !== Number(instructor.id),
    )
    .slice(0, 4);
  const subjectLabels = (lecture.subjects || [])
    .map(
      (subject) =>
        typeof subject === "object"
          ? subject.label || subject.name
          : subjects.find((item) => item.number === Number(subject))?.name ||
            `과목 ${subject}`,
    )
    .filter(Boolean);

  async function action(work) {
    setBusy(true);
    try {
      await work();
    } catch (error) {
      notify(error.message);
    } finally {
      setBusy(false);
    }
  }

  function play(path) {
    action(async () => {
      const response = await api(`/lectures/${lectureId}/${path}/`);
      setVideo(response.video);
    });
  }

  function toggleLike() {
    action(async () => {
      const response = await api(`/lectures/${lectureId}/like/`, { method: "POST" });
      setLiked(response.is_liked ?? !isLiked);
    });
  }

  async function rentLecture() {
    await action(async () => {
      if (user?.role === "instructor") {
        setRentConfirm(false);
        setInstructorPurchaseNotice(true);
        return;
      }
      await api("/cash/rentals/", {
        method: "POST",
        body: { lecture_id: lectureId },
      });
      setRented(true);
      setRentConfirm(false);
      await refreshUser();
      notify("강의를 대여했습니다.");
    });
  }

  return (
    <div className="lecture-detail-page">
      <State resource={resource}>
        <div className="lecture-detail-mobile-actions">
          <MobileBackAction onClick={() => go("lectures")}>
            강의 목록으로
          </MobileBackAction>
        </div>
        <div className="lecture-detail-page-layout">
          <main className="lecture-detail-main">
            <section className="lecture-video-stage" aria-label="강의 영상">
              {video ? (
                <video
                  className="video"
                  controls
                  controlsList="nodownload"
                  autoPlay
                  src={video}
                  onError={() =>
                    notify("영상 재생에 실패했습니다. 네트워크 상태를 확인해 주세요.")
                  }
                />
              ) : (
                <button
                  type="button"
                  className="lecture-video-poster"
                  disabled={busy}
                  onClick={() => play("stream")}
                  aria-label={`${lecture.title || "강의"} 재생`}
                >
                  {lecture.thumbnail ? (
                    <img src={lecture.thumbnail} alt="" />
                  ) : (
                    <span className="lecture-video-placeholder" aria-hidden="true" />
                  )}
                  <span className="lecture-video-play" aria-hidden="true">
                    <Play size={28} fill="currentColor" />
                  </span>
                </button>
              )}
            </section>

            <section className="lecture-detail-metadata">
              <div className="lecture-detail-title-row">
                <h1>{lecture.title || "강의"}</h1>
                {isRented && <span className="lecture-rental-badge">대여 중</span>}
              </div>
              <div className="lecture-detail-meta" aria-label="강의 메타 정보">
                <span>
                  <Eye size={15} aria-hidden="true" />
                  {formatLectureCount(lecture.view_count)}회
                </span>
                {subjectLabels.length > 0 && <span>{subjectLabels.join(" · ")}</span>}
                <span>
                  <ThumbsUp size={15} aria-hidden="true" />
                  {formatLectureCount(likeCount)}
                </span>
                {lecture.created_at && (
                  <span>{formatLectureTimeAgo(lecture.created_at)}</span>
                )}
              </div>
            </section>

            {instructor.id && (
              <section className="lecture-channel" aria-label="강의 채널">
                <button
                  type="button"
                  className="lecture-instructor"
                  onClick={() => openTeacherProfile(instructor)}
                >
                  <Avatar
                    src={instructor.profile_image}
                    name={instructor.user_name || "선생님"}
                  />
                  <span className="lecture-instructor-copy">
                    <strong>{instructor.user_name || "선생님"}</strong>
                    {academicInfo.length > 0 && (
                      <small>{academicInfo.join(" · ")}</small>
                    )}
                  </span>
                  <ChevronRight className="lecture-channel-arrow" size={18} aria-hidden="true" />
                </button>
                <div className="lecture-detail-actions">
                  <Btn
                    className={`compact-action-button lecture-recommend-button${isLiked ? " is-recommended" : ""}`}
                    disabled={busy}
                    aria-pressed={isLiked}
                    onClick={toggleLike}
                  >
                    <ThumbsUp size={17} fill={isLiked ? "currentColor" : "none"} />
                    추천
                  </Btn>
                  <ReportForm
                    source="lecture"
                    id={lectureId}
                    label="신고"
                    className="compact-action-button lecture-report-button"
                  />
                </div>
              </section>
            )}

            <section className="lecture-purchase-panel">
              <div className="lecture-purchase-layout">
                <dl className="lecture-facts">
                  <div>
                    <dt>수강료</dt>
                    <dd>{isPaid ? `${money(lecture.price)} 캐시` : "무료"}</dd>
                  </div>
                  <div>
                    <dt>대여 기간</dt>
                    <dd>{lecture.rental_period || 30}일</dd>
                  </div>
                  <div>
                    <dt>강의 길이</dt>
                    <dd>{formatVideoDuration(lecture.video_duration) || "확인 중"}</dd>
                  </div>
                </dl>
                <div className="lecture-purchase-actions">
                  {isPaid && !isRented && (
                    <Btn
                      className="primary lecture-rent-button"
                      disabled={busy}
                      onClick={() =>
                        user?.role === "instructor"
                          ? setInstructorPurchaseNotice(true)
                          : setRentConfirm(true)
                      }
                    >
                      대여하기
                    </Btn>
                  )}
                  {(!isPaid || isRented) && (
                    <Btn
                      className="primary lecture-play-button"
                      disabled={busy}
                      onClick={() => play("stream")}
                    >
                      <Play size={16} />
                      강의 재생
                    </Btn>
                  )}
                  {detail.sample_preview && isPaid && !isRented && (
                    <Btn
                      className="lecture-preview-button"
                      disabled={busy}
                      onClick={() => play("preview")}
                    >
                      무료 미리보기 재생
                    </Btn>
                  )}
                </div>
              </div>
              {rentConfirm && (
                <div className="confirm-box">
                  <b>
                    {money(lecture.price)} 캐시로 {lecture.rental_period || 30}일 대여할까요?
                  </b>
                  <p>
                    보유 캐시: {money(user?.cash)} 캐시. 대여하면 캐시가 차감됩니다.
                  </p>
                  <div className="actions">
                    <Btn disabled={busy} onClick={() => setRentConfirm(false)}>
                      취소
                    </Btn>
                    <Btn disabled={busy} className="primary" onClick={rentLecture}>
                      대여 확정
                    </Btn>
                  </div>
                </div>
              )}
              {instructorPurchaseNotice && (
                <div className="confirm-box" role="alert">
                  <b>학생 계정으로 전환 후 강의를 구매해 주세요.</b>
                  <div className="actions">
                    <Btn onClick={() => setInstructorPurchaseNotice(false)}>확인</Btn>
                  </div>
                </div>
              )}
              <p className="form-note">
                보유 캐시는 기존 계정과 연동됩니다. 마이페이지의 캐시 관리에서
                캐시 잔액과 이용 내역을 확인하세요.
              </p>
            </section>

            <section className="lecture-comments-inline" aria-label="댓글">
              <h2>댓글 {formatLectureCount(lecture.comment_count)}개</h2>
              <Comments
                id={lecture.public_id || id}
                initialExpandedCommentId={initialExpandedCommentId}
                hideTitle
                composerFirst
                sheetStyle
                onCommentsChanged={resource.reload}
              />
            </section>
          </main>

          <aside className="lecture-detail-sidebar" aria-label="추천 강의">
            <section className="lecture-recommendations">
              {instructor.id && (
                <section className="lecture-recommendation-section">
                  <h2>{instructor.user_name || "선생님"}의 다른 강의</h2>
                  <LectureRecommendationList
                    lectures={instructorLectures}
                    loading={instructorLecturesResource.loading}
                    onSelect={(lecture) => go(`lecture/${lecture.public_id}`)}
                    subjectLabel={(item) =>
                      (item.subjects || [])
                        .map(
                          (subject) =>
                            typeof subject === "object"
                              ? subject.label || subject.name
                              : subjects.find(
                                  (entry) => entry.number === Number(subject),
                                )?.name || `과목 ${subject}`,
                        )
                        .filter(Boolean)
                        .join(" · ")
                    }
                  />
                </section>
              )}
              <section className="lecture-recommendation-section">
                <h2>다른 강의 찾아보기</h2>
                <LectureRecommendationList
                  lectures={otherLectures}
                  loading={otherLecturesResource.loading}
                    onSelect={(lecture) => go(`lecture/${lecture.public_id}`)}
                  subjectLabel={(item) =>
                    (item.subjects || [])
                      .map(
                        (subject) =>
                          typeof subject === "object"
                            ? subject.label || subject.name
                            : subjects.find(
                                (entry) => entry.number === Number(subject),
                              )?.name || `과목 ${subject}`,
                      )
                      .filter(Boolean)
                      .join(" · ")
                  }
                />
              </section>
            </section>

          </aside>
        </div>
      </State>
    </div>
  );
}

function LectureRecommendationList({ lectures, loading, onSelect, subjectLabel }) {
  if (loading) {
    return <p className="lecture-recommendation-empty">강의를 불러오는 중이에요</p>;
  }
  if (!lectures.length) {
    return <p className="lecture-recommendation-empty">조회된 강의가 없어요</p>;
  }
  return (
    <div className="lecture-recommendation-list">
      {lectures.map((item) => (
        <button
          type="button"
          key={item.id}
          className="lecture-recommendation"
          onClick={() => onSelect(item)}
        >
          {item.thumbnail ? (
            <img src={item.thumbnail} alt="" />
          ) : (
            <span className="lecture-recommendation-placeholder">
              <Play size={18} aria-hidden="true" />
            </span>
          )}
          <span className="lecture-recommendation-copy">
            <strong>{item.title}</strong>
            <span className="lecture-recommendation-meta">
              {subjectLabel(item) && <span>{subjectLabel(item)}</span>}
              <span>
                <Eye size={13} aria-hidden="true" />
                {formatLectureCount(item.view_count)}
              </span>
              <span>
                <ThumbsUp size={13} aria-hidden="true" />
                {formatLectureCount(item.like_count)}
              </span>
              {item.created_at && <span>{formatLectureTimeAgo(item.created_at)}</span>}
            </span>
            <small>
              {Number(item.price) > 0 ? `${money(item.price)} 캐시` : "무료 강의"}
            </small>
          </span>
        </button>
      ))}
    </div>
  );
}

function TeacherProfilePage({
  id,
  officialReturnTo = "",
  onOfficialReturnHandled,
}) {
  const { go } = useContext(Ctx);
  const resource = useLoad(
    isPublicId(id) ? `/tutoring/instructors/public/${id}/` : null,
    [id],
  );

  if (!isPublicId(id)) {
    return (
      <Empty
        title="선생님 프로필을 찾을 수 없어요"
        text="목록에서 다시 선택해 주세요."
      >
        <Btn onClick={() => go("teachers")}>선생님 목록으로</Btn>
      </Empty>
    );
  }

  const teacher = resource.data || {};
  const teacherName = teacher.user_name || "";
  const isOfficialCreator = teacher.is_official_creator === true;
  const returnFromOfficialProfile = () => {
    if (officialReturnTo) {
      onOfficialReturnHandled?.();
      go(officialReturnTo);
      return;
    }
    go("lectures");
  };
  return (
    <div className="teacher-profile-page">
      <State resource={resource}>
        <div className="teacher-profile-mobile-actions">
          <MobileBackAction
            className="teacher-profile-mobile-list"
            onClick={
              isOfficialCreator ? returnFromOfficialProfile : () => go("teachers")
            }
          >
            {isOfficialCreator ? "강의 목록으로" : "선생님 목록으로"}
          </MobileBackAction>
          {!isOfficialCreator && (
            <ProfileSafetyActions
              className="teacher-profile-compact-safety-actions teacher-profile-mobile-safety-actions"
              instructorId={teacher.id}
              userId={teacher.user}
              teacherName={teacherName || "선생님"}
              onBlocked={() => go("teachers")}
              reportLabel="신고"
              blockLabel="차단"
            />
          )}
        </div>
        <div className="teacher-profile-page-layout">
          <div className="teacher-profile-page-content">
            <TeacherProfile id={id} teacher={teacher} />
          </div>
          {!isOfficialCreator && (
            <aside className="teacher-profile-sidebar" aria-label="선생님 프로필 작업">
              <Proposal kind="teachers" id={teacher.id} onClose={() => go("teachers")} />
              <ProfileSafetyActions
                className="teacher-profile-compact-safety-actions teacher-profile-desktop-safety-actions"
                instructorId={teacher.id}
                userId={teacher.user}
                teacherName={teacherName || "선생님"}
                onBlocked={() => go("teachers")}
                reportLabel="신고"
                blockLabel="차단"
              />
            </aside>
          )}
        </div>
      </State>
    </div>
  );
}

/** 학생의 과외 모집 공고를 프로필 화면과 같은 독립 상세 페이지로 표시합니다. */
function TutoringPostPage({ id, listItem }) {
  const { go, user } = useContext(Ctx);
  const resource = useLoad(
    isPublicId(id) ? `/tutoring/posts/public/${id}/` : null,
    [id],
  );

  if (!isPublicId(id)) {
    return (
      <Empty
        title="과외 공고를 찾을 수 없어요"
        text="목록에서 다시 선택해 주세요."
      >
        <Btn onClick={() => go("posts")}>과외 공고 목록으로</Btn>
      </Empty>
    );
  }

  const post = resource.data || {};
  const isOwnPost = Number(post.student?.user) === Number(user?.id);
  const profileImage =
    listItem?.public_id === id
      ? listItem.student_profile_image
      : isOwnPost
        ? user?.profile_image
        : null;
  const studentName =
    listItem?.public_id === id
      ? listItem.student_name
      : isOwnPost
        ? user?.nickname
        : "학생";
  return (
    <div className="teacher-profile-page tutoring-post-page">
      <State resource={resource}>
        <div className="teacher-profile-mobile-actions tutoring-post-mobile-actions">
          <MobileBackAction
            className="teacher-profile-mobile-list"
            onClick={() => go("posts")}
          >
            과외 공고 목록으로
          </MobileBackAction>
          <TutoringPostSafetyActions
            className="teacher-profile-mobile-safety-actions"
            post={post}
            studentName={studentName}
          />
        </div>
        <div className="teacher-profile-page-layout">
          <main className="teacher-profile-page-content">
            <TutoringPostDetail
              post={post}
              profileImage={profileImage}
              studentName={studentName}
              isOwnPost={isOwnPost}
            />
          </main>
          <aside className="teacher-profile-sidebar" aria-label="과외 공고 작업">
            <Proposal kind="posts" id={post.id} onClose={() => go("posts")} />
            <TutoringPostSafetyActions
              className="teacher-profile-compact-safety-actions teacher-profile-desktop-safety-actions"
              post={post}
              studentName={studentName}
            />
          </aside>
        </div>
      </State>
    </div>
  );
}

/** 과외 공고의 기본 정보와 학생 후기를 표시합니다. */
function TutoringPostDetail({ post, profileImage, studentName, isOwnPost }) {
  const [tab, setTab] = useState("info");
  const reviews = useLoad(
    tab === "reviews" && post.student?.id
      ? `/tutoring/students/${post.student.id}/reviews/`
      : null,
    [tab, post.student?.id],
  );
  const sexLabel =
    post.sex === "여" || post.sex === "여성" || post.sex === "F"
      ? "여성"
      : post.sex === "남" || post.sex === "남성" || post.sex === "M"
        ? "남성"
        : post.sex || "";
  const personalInfo = [sexLabel, post.age != null ? `만 ${post.age}세` : ""]
    .filter(Boolean);
  const studentInfo = [sexLabel, post.grade, post.field]
    .filter(Boolean)
    .join(" · ");
  const textLabels = (values) =>
    (Array.isArray(values) ? values : [])
      .map((value) =>
        typeof value === "object" ? value.label || value.name : value,
      )
      .filter(Boolean)
      .join(", ");
  const createdAt = post.created_at ? new Date(post.created_at) : null;
  const createdDate =
    createdAt && !Number.isNaN(createdAt.valueOf())
      ? `${createdAt.getFullYear()}-${String(createdAt.getMonth() + 1).padStart(2, "0")}-${String(createdAt.getDate()).padStart(2, "0")}`
      : "";

  return (
    <section className="tutoring-post-detail">
      <header className="tutoring-post-header">
        <Avatar
          src={profileImage}
          name="학생"
          size="profile-avatar"
        />
        <div className="tutoring-post-identity">
          <h2>{studentName || "학생"}</h2>
          <div className="tutoring-post-meta">
            {createdDate && <span>{createdDate}</span>}
            {createdDate && <i aria-hidden="true" />}
            <span>
              <Eye size={14} aria-hidden="true" />
              조회수 {post.view_count || 0}회
            </span>
          </div>
        </div>
        {isOwnPost && (
          <span className={`post-status ${post.is_active === false ? "closed" : "active"}`}>
            {post.is_active === false ? "모집 마감" : "모집 중"}
          </span>
        )}
      </header>
      <div className="teacher-profile-info tutoring-post-summary">
        {personalInfo.length > 0 && (
          <div className="teacher-profile-info-item">
            <UserRound size={15} aria-hidden="true" />
            <span className="teacher-profile-personal-info">
              {personalInfo.map((label, index) => (
                <React.Fragment key={label}>
                  {index > 0 && (
                    <span
                      className="teacher-profile-info-divider"
                      aria-hidden="true"
                    />
                  )}
                  <span>{label}</span>
                </React.Fragment>
              ))}
            </span>
          </div>
        )}
        {textLabels(post.regions) && (
          <div className="teacher-profile-info-item">
            <MapPin size={15} aria-hidden="true" />
            <span>{textLabels(post.regions)}</span>
          </div>
        )}
        {textLabels(post.subjects) && (
          <div className="teacher-profile-info-item teacher-profile-subjects">
            <BookOpen size={15} aria-hidden="true" />
            <span>{textLabels(post.subjects)}</span>
          </div>
        )}
      </div>
      <div className="registration-tabs detail-tabs" role="tablist" aria-label="학생 모집 공고 상세">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "info"}
          className={tab === "info" ? "active" : ""}
          onClick={() => setTab("info")}
        >
          과외 공고
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
      {tab === "info" ? (
        <dl className="class-info-list post-detail-list">
          <div>
            <dt>공고 제목</dt>
            <dd>{post.title || "제목 없음"}</dd>
          </div>
          <div>
            <dt>학생 정보</dt>
            <dd>{studentInfo || "정보 미입력"}</dd>
          </div>
          <div>
            <dt>수업 과목</dt>
            <dd>{textLabels(post.subjects) || "협의"}</dd>
          </div>
          <div>
            <dt>수업 방식</dt>
            <dd>{post.method || "상담 후 결정"}</dd>
          </div>
          <div>
            <dt>수업료</dt>
            <dd>{post.cost ? `${money(post.cost)}원` : "협의"}</dd>
          </div>
          <div>
            <dt>수업 일정</dt>
            <dd>{post.schedule || "협의 가능"}</dd>
          </div>
          {post.situation && (
            <div>
              <dt>학생 상황</dt>
              <dd>{post.situation}</dd>
            </div>
          )}
          {post.etc && (
            <div>
              <dt>기타 요청</dt>
              <dd>{post.etc}</dd>
            </div>
          )}
        </dl>
      ) : (
        <State resource={reviews}>
          {list(reviews.data).length ? (
            <div className="review-list tutoring-post-review-list">
              {list(reviews.data).map((review) => (
                <article className="comment" key={review.id}>
                  <b>
                    {review.instructor_nickname || review.instructor_label || "선생님"}
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
            <p className="tutoring-post-tab-empty">등록된 과외 리뷰가 없습니다.</p>
          )}
        </State>
      )}
    </section>
  );
}

/** 공고 상세 페이지에서 신고 및 학생 차단 동작을 제공합니다. */
function TutoringPostSafetyActions({ post, studentName = "학생", className = "" }) {
  const { user, go } = useContext(Ctx);
  const studentUserId = Number(post.student?.user);

  if (!studentUserId || studentUserId === Number(user?.id)) return null;

  return (
    <div className={`profile-safety-actions ${className}`.trim()}>
      <ReportForm source="tutoring_post" id={post.id} label="신고" />
      <BlockUserButton
        userId={studentUserId}
        targetName={studentName}
        targetLabel="학생"
        label="차단"
        onBlocked={() => go("posts")}
      />
    </div>
  );
}
function ProfileSafetyActions({
  className = "",
  instructorId,
  userId,
  teacherName,
  onBlocked,
  reportLabel,
  blockLabel,
}) {
  return (
    <div className={`profile-safety-actions ${className}`.trim()}>
      <ReportForm
        source="teacher_profile"
        id={instructorId}
        label={reportLabel}
      />
      <BlockUserButton
        userId={userId}
        targetName={teacherName}
        onBlocked={onBlocked}
        label={blockLabel}
      />
    </div>
  );
}
function BlockUserButton({
  userId,
  targetName,
  targetLabel = "선생님",
  onBlocked,
  label = "차단하기",
  className = "",
}) {
  const { user, notify } = useContext(Ctx);
  const [busy, setBusy] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const targetUserId = Number(userId);
  const currentUserId = Number(user?.id);

  if (
    !Number.isInteger(targetUserId) ||
    targetUserId <= 0 ||
    targetUserId === currentUserId
  ) {
    return null;
  }

  async function blockTeacher() {
    setBusy(true);
    try {
      await api("/blocks/", {
        method: "POST",
        body: { blocked_user: targetUserId },
      });
      setIsConfirmOpen(false);
      notify(`${targetName} ${targetLabel}을 차단했어요.`);
      onBlocked();
    } catch (error) {
      notify(error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Btn
        className={`compact-action-button block-teacher-button ${className}`.trim()}
        disabled={busy}
        onClick={() => setIsConfirmOpen(true)}
      >
        <Ban size={16} aria-hidden="true" />
        {busy ? "차단 중…" : label}
      </Btn>
      {isConfirmOpen && (
        <ConfirmDialog
          title={`${targetName} ${targetLabel}을 차단할까요?`}
          description={
            targetLabel === "선생님"
              ? "차단한 선생님의 프로필과 강의를 더 이상 볼 수 없어요.(차단한 선생님은 마이페이지에서 수정할 수 있어요.)"
              : "차단한 학생의 프로필과 모집 공고를 더 이상 볼 수 없어요."
          }
          cancelLabel="취소"
          confirmLabel="차단하기"
          busy={busy}
          onCancel={() => setIsConfirmOpen(false)}
          onConfirm={blockTeacher}
        />
      )}
    </>
  );
}
function Proposal({ kind, id, onClose }) {
  const { user, notify, go } = useContext(Ctx);
  const eligible =
    kind === "teachers" ? user.role === "student" : user.role === "instructor";
  const isStudentPostProposal = kind === "posts";
  const posts = useLoad(
    eligible && kind === "teachers" ? "/tutoring/my-posts/" : null,
  );
  const proposals = useLoad(
    eligible && isStudentPostProposal ? "/tutoring/proposals/" : null,
    [eligible, isStudentPostProposal],
    { keepDataOnReload: true },
  );
  const chatRooms = useLoad(
    eligible && isStudentPostProposal ? "/chatrooms/?role=instructor" : null,
    [eligible, isStudentPostProposal],
    { keepDataOnReload: true },
  );
  const [busy, setBusy] = useState(false),
    [open, setOpen] = useState(false),
    [checkingProfile, setCheckingProfile] = useState(false),
    [message, setMessage] = useState(""),
    [sentRoomId, setSentRoomId] = useState(null),
    [isProfileDialogOpen, setIsProfileDialogOpen] = useState(false),
    [isVerificationDialogOpen, setIsVerificationDialogOpen] = useState(false),
    [isConfirmOpen, setIsConfirmOpen] = useState(false),
    [isSavedProposalsOpen, setIsSavedProposalsOpen] = useState(false),
    [savedProposalOrder, setSavedProposalOrder] = useState("newest"),
    [savedProposalDetail, setSavedProposalDetail] = useState(null);
  const hasActivePosts = list(posts.data).some((post) => post.is_active !== false);
  const proposalRows = list(proposals.data);
  const sortedProposalRows = [...proposalRows].sort((left, right) => {
    const difference = new Date(right.created_at) - new Date(left.created_at);
    return savedProposalOrder === "newest" ? difference : -difference;
  });
  const currentProposal = proposalRows.find(
    (proposal) => Number(proposal.tutoring_post) === Number(id),
  );
  const currentRoom = list(chatRooms.data).find(
    (room) => Number(room.post) === Number(id),
  );
  const proposalRoomId = sentRoomId || currentRoom?.public_id;
  const proposalAccepted = Boolean(currentRoom?.is_accepted);
  const canSubmitStudentProposal = message.trim().length >= 10;
  const hasSentStudentProposal = isStudentPostProposal && (currentProposal || sentRoomId);
  const isProposalStatusLoading = isStudentPostProposal && (proposals.loading || chatRooms.loading);

  async function openProposal() {
    if (kind === "teachers") {
      setOpen(true);
      return;
    }

    setCheckingProfile(true);
    try {
      const [profile, verification] = await Promise.all([
        api("/tutoring/instructor-info/mine/"),
        api("/pending/"),
      ]);
      if (!profile) {
        setIsProfileDialogOpen(true);
      } else if (verification?.status !== "VERIFIED") {
        setIsVerificationDialogOpen(true);
      } else {
        setOpen(true);
      }
    } catch (error) {
      notify(error.message || "제안 가능 상태를 확인하지 못했어요.");
    } finally {
      setCheckingProfile(false);
    }
  }

  async function sendProposal(body) {
    setBusy(true);
    try {
      const result = await api(
        kind === "teachers"
          ? "/tutoring/propose-to-instructor/"
          : "/tutoring/propose-to-student/",
        { method: "POST", body },
      );
      notify("과외 제안을 보냈습니다. 채팅에서 확인해 주세요.");
      if (isStudentPostProposal) {
        setSentRoomId(result.room_public_id || result.room_id);
        proposals.reload();
        chatRooms.reload();
        go(`chat/${result.room_public_id || result.room_id}`);
      } else {
        onClose();
        go("chat");
      }
    } catch (error) {
      if (error.data?.code === "tutoring_profile_required") {
        setIsProfileDialogOpen(true);
      } else if (error.data?.code === "academic_verification_required") {
        setIsVerificationDialogOpen(true);
      } else {
        notify(error.message);
      }
    } finally {
      setBusy(false);
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (kind === "teachers") {
      const form = new FormData(event.currentTarget);
      await sendProposal({ instructor_id: id, post_id: Number(form.get("post_id")) });
      return;
    }
    if (canSubmitStudentProposal) setIsConfirmOpen(true);
  }

  if (!eligible) return null;
  return (
    <div className="info-panel" aria-busy={isProposalStatusLoading || undefined}>
      <h3>
        {isProposalStatusLoading ? <span className="proposal-status-skeleton-title" aria-hidden="true" /> : kind === "teachers"
          ? "지금 과외 상담을 시작해보세요."
          : hasSentStudentProposal
            ? "이미 제안서를 보낸 공고에요."
            : "지금 과외 제안을 보내보세요."}
      </h3>
      {isProposalStatusLoading ? (
        <div className="proposal-status-skeleton" role="status" aria-label="제안 상태 불러오는 중">
          <span aria-hidden="true" />
        </div>
      ) : hasSentStudentProposal ? (
        <div className="proposal-status-actions">
          {proposalAccepted && proposalRoomId ? (
            <Btn className="primary" onClick={() => go(`chat/${proposalRoomId}`)}>
              <MessageCircle size={16} aria-hidden="true" />
              채팅방으로 이동
            </Btn>
          ) : (
            <Btn type="button" disabled className="proposal-complete-button">
              과외 제안 완료
            </Btn>
          )}
        </div>
      ) : !open ? (
        <Btn className="primary" disabled={checkingProfile} onClick={openProposal}>
          <MessageCircle size={16} />
          {checkingProfile
            ? "확인 중…"
            : kind === "teachers"
            ? "이 선생님에게 과외 문의하기"
            : "이 학생에게 과외 제안 보내기"}
        </Btn>
      ) : (
        <form className="form" onSubmit={submit}>
          {kind === "teachers" ? (
            <State resource={posts}>
              {list(posts.data).filter((p) => p.is_active !== false).length ? (
                <label>
                  과외 공고를 선택해 주세요.
                  <select name="post_id" required defaultValue="">
                    <option value="" disabled>과외 공고 선택</option>
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
                <>
                  <p>상담을 제안하려면 과외 공고가 필요해요.</p>
                  <Btn
                    className="proposal-post-create"
                    type="button"
                    onClick={() => go("tutoring-post/new")}
                  >
                    새 모집 공고 작성하러 가기
                  </Btn>
                </>
              )}
            </State>
          ) : (
            <>
              <Btn type="button" className="proposal-saved-button" onClick={() => setIsSavedProposalsOpen(true)}>
                이전 제안서 불러오기
              </Btn>
              <label>
                <textarea
                  name="message"
                  rows={7}
                  required
                  value={message}
                  maxLength={3000}
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder="학생에게 전달될 과외 제안서를 작성해 주세요. 간단한 자기소개와 수업 소개, 커리큘럼, 가능 일정 등을 구체적으로 적어주세요. 최소 10자 이상 입력해야 합니다."
                />
                <span className={`proposal-message-counter ${canSubmitStudentProposal ? "valid" : ""}`}>{message.length}/3000</span>
              </label>
            </>
          )}
          <p className="form-note">
            제안을 보내면 상대방에게 알림이 전달되고 상담 채팅방이 만들어집니다.
          </p>
          <div className="actions proposal-form-actions">
            <div className="proposal-form-secondary-actions">
              <Btn type="button" onClick={() => setOpen(false)}>
                취소
              </Btn>
              {kind === "teachers" && hasActivePosts && (
                <Btn
                  className="proposal-post-create"
                  type="button"
                  onClick={() => go("tutoring-post/new")}
                >
                  새 모집 공고 작성하러 가기
                </Btn>
              )}
            </div>
            <Btn
              className="primary"
              disabled={
                busy ||
                (kind === "teachers" && !hasActivePosts) ||
                (isStudentPostProposal && !canSubmitStudentProposal)
              }
            >
              {busy ? "전송 중…" : "제안 보내기"}
            </Btn>
          </div>
        </form>
      )}
      {isSavedProposalsOpen && (
        <Modal
          title="이전 제안서 불러오기"
          onClose={() => setIsSavedProposalsOpen(false)}
          className="proposal-saved-modal"
          scrollable
        >
          <State resource={proposals}>
            <div className="proposal-saved-toolbar">
              <select
                aria-label="제안서 정렬"
                value={savedProposalOrder}
                onChange={(event) => setSavedProposalOrder(event.target.value)}
              >
                <option value="newest">최신순</option>
                <option value="oldest">오래된순</option>
              </select>
            </div>
            <div className="proposal-saved-list">
              {sortedProposalRows.length ? sortedProposalRows.map((proposal) => (
                <article key={proposal.id}>
                  <p>{proposal.message}</p>
                  <div className="proposal-saved-meta">
                    <small>{date(proposal.created_at)}</small>
                  </div>
                  <Btn
                    type="button"
                    className="primary proposal-saved-use"
                    onClick={() => {
                      setMessage(proposal.message || "");
                      setIsSavedProposalsOpen(false);
                    }}
                  >
                    선택
                  </Btn>
                  <Btn
                    type="button"
                    className="proposal-saved-detail"
                    onClick={() => {
                      setIsSavedProposalsOpen(false);
                      setSavedProposalDetail(proposal);
                    }}
                  >
                    상세보기
                  </Btn>
                </article>
              )) : <p className="muted">저장된 제안서가 없어요.</p>}
            </div>
          </State>
        </Modal>
      )}
      {savedProposalDetail && (
        <Modal
          title="과외 제안서 상세"
          onClose={() => setSavedProposalDetail(null)}
          className="proposal-saved-detail-modal"
          scrollable
        >
          <article className="proposal-saved-detail-content">
            <small>{date(savedProposalDetail.created_at)}</small>
            <p>{savedProposalDetail.message}</p>
            <div className="proposal-saved-detail-actions">
              <Btn
                type="button"
                onClick={() => {
                  setSavedProposalDetail(null);
                  setIsSavedProposalsOpen(true);
                }}
              >
                뒤로가기
              </Btn>
              <Btn
                type="button"
                className="primary"
                onClick={() => {
                  setMessage(savedProposalDetail.message || "");
                  setSavedProposalDetail(null);
                }}
              >
                선택
              </Btn>
            </div>
          </article>
        </Modal>
      )}
      {isProfileDialogOpen && (
        <ConfirmDialog
          title="아직 과외 프로필이 없어요"
          description="과외 제안을 보내시려면 먼저 선생님의 과외 프로필을 만들어 주세요."
          cancelLabel="닫기"
          confirmLabel="프로필 만들기"
          onCancel={() => setIsProfileDialogOpen(false)}
          onConfirm={() => {
            setIsProfileDialogOpen(false);
            go("tutoring-profile");
          }}
        />
      )}
      {isVerificationDialogOpen && (
        <ConfirmDialog
          title="학력 인증이 필요해요"
          description="아직 학력 인증이 완료되지 않았어요. 과외 제안을 보내려면 학력 인증이 완료되어야 해요."
          cancelLabel="닫기"
          confirmLabel="인증하러 가기"
          onCancel={() => setIsVerificationDialogOpen(false)}
          onConfirm={() => {
            setIsVerificationDialogOpen(false);
            go("verification");
          }}
        />
      )}
      {isConfirmOpen && (
        <ConfirmDialog
          title="제안서를 전송할까요?"
          description="제안서를 보낸 뒤에는 수정할 수 없으며, 상대방이 답장을 보내기 전까지 메시지를 보낼 수 없습니다."
          cancelLabel="취소"
          confirmLabel="전송"
          busy={busy}
          onCancel={() => setIsConfirmOpen(false)}
          onConfirm={() => {
            setIsConfirmOpen(false);
            sendProposal({ post_id: id, message: message.trim() });
          }}
        />
      )}
    </div>
  );
}

function TeacherProfileTabEmpty({ title, description }) {
  return (
    <div className="teacher-profile-tab-empty">
      <p>{title}</p>
      {description && <small>{description}</small>}
    </div>
  );
}

function TeacherRatingGauge({ label, rating }) {
  const normalizedRating = Math.min(5, Math.max(0, Number(rating) || 0));
  const displayRating = Number.isInteger(normalizedRating)
    ? String(normalizedRating)
    : normalizedRating.toFixed(1);

  return (
    <div className="teacher-rating-gauge">
      <div>
        <span>{label}</span>
        <span><b>{displayRating}</b>/5</span>
      </div>
      <span className="teacher-rating-gauge-track" aria-hidden="true">
        <span style={{ width: `${(normalizedRating / 5) * 100}%` }} />
      </span>
    </div>
  );
}

function TeacherProfile({ id, teacher, item }) {
  const { user, notify, detail, subjects } = useContext(Ctx);
  const [tab, setTab] = useState("info");
  const profile = { ...(item || {}), ...(teacher || {}) };
  const isOfficialCreator = profile.is_official_creator === true;
  const selectedTab = isOfficialCreator ? "lectures" : tab;
  const info = useLoad(
    isOfficialCreator ? null : `/tutoring/instructors/public/${id}/info/`,
    [id, isOfficialCreator],
  );
  const reviews = useLoad(
    !isOfficialCreator && selectedTab === "reviews"
      ? `/tutoring/instructors/public/${id}/reviews/`
      : null,
    [id, isOfficialCreator, selectedTab],
  );
  const lectures = useLoad(
    profile.id ? `/lectures/?instructor=${profile.id}` : null,
    [profile.id],
  );
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
  const hasTutoringInfo =
    Boolean(info.data) &&
    Boolean(
      infoData.cost ||
        infoData.schedule ||
        textLabels(infoData.subjects),
    );
  const isOwnProfile = Number(profile.user) === Number(user?.id);
  const sexLabel =
    profile.sex === "여" || profile.sex === "여성" || profile.sex === "F"
      ? "여성"
      : profile.sex === "남" || profile.sex === "남성" || profile.sex === "M"
        ? "남성"
        : profile.sex || "";
  const personalInfo = [sexLabel, age != null ? `만 ${age}세` : ""].filter(
    Boolean,
  );
  const locationLabel =
    profile.region || textLabels(infoData.regions) || infoData.location || "";
  const subjectLabels = (Array.isArray(profile.subjects)
    ? profile.subjects
    : []
  )
    .map((subject) => {
      if (typeof subject === "object") return subject.label || subject.name;
      if (typeof subject === "string" && !/^\d+$/.test(subject)) {
        return subject;
      }
      return subjects.find((item) => item.number === Number(subject))?.name;
    })
    .filter(Boolean)
    .join(", ");
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
  const formatRating = (rating) => {
    const value = Number(rating) || 0;
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  };
  const studentNumber = profile.student_number
    ? `${String(profile.student_number).slice(2)}학번`
    : "";
  const lectureRows = list(lectures.data);
  const previewLecture = lectureRows.find((lecture) => lecture.is_preview);
  const otherLectures = lectureRows.filter((lecture) => !lecture.is_preview);
  const lectureSubject = (lecture) => {
    const [subject] = Array.isArray(lecture.subjects) ? lecture.subjects : [];
    if (typeof subject === "object") return subject.label || subject.name || "";
    if (typeof subject === "string" && !/^\d+$/.test(subject)) return subject;
    return subjects.find((item) => item.number === Number(subject))?.name || "";
  };
  const reviewSubjects = (values) =>
    (Array.isArray(values) ? values : [])
      .map((subject) => {
        if (typeof subject === "object") return subject.label || subject.name;
        if (typeof subject === "string" && !/^\d+$/.test(subject)) return subject;
        return subjects.find((item) => item.number === Number(subject))?.name;
      })
      .filter(Boolean)
      .join(", ");
  const lectureMeta = (lecture) => (
    <div className="teacher-lecture-meta">
      {lectureSubject(lecture) && (
        <span className="teacher-lecture-meta-item">{lectureSubject(lecture)}</span>
      )}
      <span className="teacher-lecture-meta-item">
        <Eye size={16} aria-hidden="true" />
        {formatLectureCount(lecture.view_count)}
      </span>
      <span className="teacher-lecture-meta-item">
        <ThumbsUp size={16} aria-hidden="true" />
        {formatLectureCount(lecture.like_count)}
      </span>
      {formatLectureTimeAgo(lecture.created_at) && (
        <span className="teacher-lecture-meta-item">
          {formatLectureTimeAgo(lecture.created_at)}
        </span>
      )}
    </div>
  );

  async function toggleLike() {
    try {
      const result = await api(`/tutoring/instructors/${profile.id}/like/`, {
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
      {isOfficialCreator ? (
        <>
          <div className="teacher-profile-header official-profile-header">
            <Avatar
              src={profile.profile_image}
              name={profile.user_name || "클래씨 운영자"}
              size="profile-avatar"
            />
            <div className="teacher-profile-identity">
              <h2>
                {profile.user_name || "클래씨 운영자"}
                <span className="official-profile-badge">운영자</span>
              </h2>
            </div>
          </div>
          <p className="teacher-profile-introduction">
            클래씨 운영자 계정입니다.
          </p>
        </>
      ) : (
        <>
          <div className="teacher-profile-header">
            <Avatar
              src={profile.profile_image}
              name={profile.user_name || "선생님"}
              size="profile-avatar"
            />
            <div className="teacher-profile-identity">
              <h2>
                {profile.user_name || "선생님"}
                {profile.is_certified && <ShieldCheck size={17} className="certified" aria-label="인증된 선생님" />}
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
          <div className="teacher-profile-info">
            {personalInfo.length > 0 && (
              <div className="teacher-profile-info-item">
                <UserRound size={15} aria-hidden="true" />
                <span className="teacher-profile-personal-info">
                  {personalInfo.map((label, index) => (
                    <React.Fragment key={label}>
                      {index > 0 && (
                        <span
                          className="teacher-profile-info-divider"
                          aria-hidden="true"
                        />
                      )}
                      <span>{label}</span>
                    </React.Fragment>
                  ))}
                </span>
              </div>
            )}
            {locationLabel && (
              <div className="teacher-profile-info-item">
                <MapPin size={15} aria-hidden="true" />
                <span>{locationLabel}</span>
              </div>
            )}
            {subjectLabels && (
              <div className="teacher-profile-info-item teacher-profile-subjects">
                <BookOpen size={15} aria-hidden="true" />
                <span>{subjectLabels}</span>
              </div>
            )}
          </div>
          {profile.instruction && (
            <p className="teacher-profile-introduction">
              선생님 한 줄 소개: {profile.instruction}
            </p>
          )}
          <State resource={info}>
            {info.data && (
              <section className="teacher-profile-stats">
                <div
                  className={
                    "teacher-profile-status" +
                    (infoData.is_tutoring ? " available" : "")
                  }
                >
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
                      <strong>
                        {Number(infoData.current_rank) > 0
                          ? `${infoData.current_rank}위`
                          : "랭킹 외"}
                      </strong>
                    </div>
                  </>
                )}
              </section>
            )}
          </State>
        </>
      )}
      <div
        className="registration-tabs detail-tabs"
        role="tablist"
        aria-label={isOfficialCreator ? "운영자 프로필 상세" : "선생님 프로필 상세"}
      >
        <button
          type="button"
          role="tab"
          aria-selected={selectedTab === "lectures"}
          className={selectedTab === "lectures" ? "active" : ""}
          onClick={() => setTab("lectures")}
        >
          강의
        </button>
        {!isOfficialCreator && <>
          <button
            type="button"
            role="tab"
            aria-selected={selectedTab === "info"}
            className={selectedTab === "info" ? "active" : ""}
            onClick={() => setTab("info")}
          >
            과외 정보
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={selectedTab === "reviews"}
            className={selectedTab === "reviews" ? "active" : ""}
            onClick={() => setTab("reviews")}
          >
            과외 리뷰
          </button>
        </>}
      </div>
      {selectedTab === "lectures" && (
        <State resource={lectures}>
          {lectureRows.length ? (
            <div className="teacher-profile-lectures">
              {previewLecture && (
                <section className="teacher-profile-lecture-section teacher-profile-preview-section">
                  <h3>{profile.user_name || "선생님"} 선생님의 프리뷰 영상</h3>
                  <button
                    type="button"
                    className="teacher-preview-lecture"
                    onClick={() => detail("lectures", previewLecture.id, previewLecture)}
                  >
                    {previewLecture.thumbnail ? (
                      <img src={previewLecture.thumbnail} alt="" />
                    ) : (
                      <span className="teacher-preview-placeholder"><Play size={48} /></span>
                    )}
                    <b>{previewLecture.title}</b>
                    {lectureMeta(previewLecture)}
                  </button>
                </section>
              )}
              {otherLectures.length > 0 && (
                <section className="teacher-profile-lecture-section">
                  <h3>{profile.user_name || "선생님"} 선생님의 강의</h3>
                  <div className="teacher-profile-lecture-list">
                    {otherLectures.map((lecture) => (
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
                        <span className="teacher-lecture-content">
                          <b>{lecture.title}</b>
                          {lectureMeta(lecture)}
                          <small>
                            {lecture.is_preview
                              ? "프리뷰 강의"
                              : Number(lecture.price) === 0
                                ? "무료 강의"
                                : `${money(lecture.price)} 캐시`}
                          </small>
                        </span>
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </div>
          ) : (
            <TeacherProfileTabEmpty
              title="강의가 아직 없어요."
              description={
                isOwnProfile
                  ? "첫 강의를 등록해 학생들에게 선생님을 알려보세요."
                  : "선생님이 강의를 올리기를 기다려주세요."
              }
            />
          )}
        </State>
      )}
      {!isOfficialCreator && selectedTab === "info" && (
        <State resource={info}>
          {hasTutoringInfo ? (
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
                <dd>{infoData.cost_display || infoData.cost || "협의 후 결정"}</dd>
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
          ) : (
            <TeacherProfileTabEmpty title="아직 과외 정보를 등록하지 않은 선생님이에요" />
          )}
        </State>
      )}
      {!isOfficialCreator && selectedTab === "reviews" && (
        <State resource={reviews}>
          {reviewRows.length ? (
            <>
              <section className="teacher-review-summary">
                <div className="teacher-review-total">
                  <Star size={24} fill="currentColor" aria-hidden="true" />
                  <b>{formatRating(averageRating)}<span> /5</span></b>
                  <small>({reviewRows.length})</small>
                </div>
                <div className="teacher-review-summary-gauges">
                  <TeacherRatingGauge label="전문적이에요" rating={professional} />
                  <TeacherRatingGauge label="강의력이 좋아요" rating={teaching} />
                  <TeacherRatingGauge label="시간을 잘 지켜요" rating={punctuality} />
                </div>
              </section>
              <div className="teacher-review-list">
                {reviewRows.map((review) => (
                  <article className="teacher-review-card" key={review.id}>
                    <div className="teacher-review-author">
                      <Avatar
                        src={review.student_profile_image}
                        name={review.student_label || "학생"}
                      />
                      <div className="teacher-review-identity">
                        <div>
                          <b>{review.student_label || "학생"}</b>
                          {review.class_type && <span>{review.class_type}</span>}
                        </div>
                        {date(review.created_at) && <small>{date(review.created_at)}</small>}
                      </div>
                    </div>
                    {reviewSubjects(review.subjects) && (
                      <p className="teacher-review-subjects">
                        <BookOpen size={14} aria-hidden="true" />
                        {reviewSubjects(review.subjects)}
                      </p>
                    )}
                    <p>{review.comment}</p>
                    <div className="teacher-review-scores">
                      <TeacherRatingGauge label="전문적이에요" rating={review.professionalism} />
                      <TeacherRatingGauge label="강의력이 좋아요" rating={review.teaching_skill} />
                      <TeacherRatingGauge label="시간을 잘 지켜요" rating={review.punctuality} />
                    </div>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <TeacherProfileTabEmpty
              title="아직 리뷰가 없어요."
              description="첫 번째 리뷰를 남겨주세요."
            />
          )}
        </State>
      )}
    </section>
  );
}
function Comments({
  id,
  initialExpandedCommentId,
  hideTitle = false,
  composerFirst = false,
  sheetStyle = false,
  onCommentsChanged,
}) {
  const [commentRows, setCommentRows] = useState([]);
  const [nextCommentsPath, setNextCommentsPath] = useState("");
  const [isLoadingMoreComments, setIsLoadingMoreComments] = useState(false);
  const [loadMoreCommentsError, setLoadMoreCommentsError] = useState("");
  const [openCommentMenuId, setOpenCommentMenuId] = useState(null);
  const loadMoreSentinelRef = useRef(null);
  const commentMenuRef = useRef(null);
  const [expandedCommentIds, setExpandedCommentIds] = useState(() => new Set());
  const [replyThreads, setReplyThreads] = useState({});
  const [loadingReplyIds, setLoadingReplyIds] = useState(() => new Set());
  const [replyErrors, setReplyErrors] = useState({});
  const commentsPath = isPublicId(id)
    ? `/lectures/public/${id}/comments/`
    : `/lectures/${id}/comments/`;
  const resource = useLoad(
    `${commentsPath}?page=1&lazy_replies=true`,
  );
  const { notify, user } = useContext(Ctx);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setCommentRows([]);
    setNextCommentsPath("");
    setLoadMoreCommentsError("");
  }, [id]);

  useEffect(() => {
    if (openCommentMenuId === null) return;
    const closeOnOutsidePointerDown = (event) => {
      if (!commentMenuRef.current?.contains(event.target)) {
        setOpenCommentMenuId(null);
      }
    };
    document.addEventListener("pointerdown", closeOnOutsidePointerDown);
    return () =>
      document.removeEventListener("pointerdown", closeOnOutsidePointerDown);
  }, [openCommentMenuId]);

  useEffect(() => {
    if (!resource.data) return;
    setCommentRows(list(resource.data));
    setNextCommentsPath(resource.data.next || "");
    setLoadMoreCommentsError("");
  }, [resource.data]);

  const loadMoreComments = useCallback(async () => {
    if (!nextCommentsPath || isLoadingMoreComments) return;
    setIsLoadingMoreComments(true);
    setLoadMoreCommentsError("");
    try {
      const data = await api(nextCommentsPath);
      setCommentRows((current) => {
        const loadedIds = new Set(current.map((comment) => comment.id));
        return [
          ...current,
          ...list(data).filter((comment) => !loadedIds.has(comment.id)),
        ];
      });
      setNextCommentsPath(data.next || "");
    } catch (error) {
      setLoadMoreCommentsError(error.message);
    } finally {
      setIsLoadingMoreComments(false);
    }
  }, [isLoadingMoreComments, nextCommentsPath]);

  useEffect(() => {
    const sentinel = loadMoreSentinelRef.current;
    if (!sentinel || !nextCommentsPath || isLoadingMoreComments) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) loadMoreComments();
      },
      { rootMargin: "320px 0px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [isLoadingMoreComments, loadMoreComments, nextCommentsPath]);

  async function loadReplies(commentId, { force = false } = {}) {
    const normalizedCommentId = commentId.toString();
    if (
      !force &&
      Object.prototype.hasOwnProperty.call(replyThreads, normalizedCommentId)
    ) {
      return;
    }
    if (loadingReplyIds.has(normalizedCommentId)) return;

    setLoadingReplyIds((current) => new Set([...current, normalizedCommentId]));
    setReplyErrors((current) => {
      const next = { ...current };
      delete next[normalizedCommentId];
      return next;
    });
    try {
      const data = await api(
        `${commentsPath}?lazy_replies=true&parent_id=${encodeURIComponent(commentId)}`,
      );
      setReplyThreads((current) => ({
        ...current,
        [normalizedCommentId]: list(data),
      }));
    } catch (e) {
      setReplyErrors((current) => ({
        ...current,
        [normalizedCommentId]: e.message,
      }));
    } finally {
      setLoadingReplyIds((current) => {
        const next = new Set(current);
        next.delete(normalizedCommentId);
        return next;
      });
    }
  }

  useEffect(() => {
    if (!initialExpandedCommentId) return;
    const commentId = initialExpandedCommentId.toString();
    setExpandedCommentIds((current) => new Set([...current, commentId]));
    const parentComment = commentRows.find(
      (comment) => comment.id.toString() === commentId,
    );
    if (parentComment) loadReplies(parentComment.id);
  }, [initialExpandedCommentId, commentRows]);

  const toggleReplies = (commentId) => {
    const normalizedCommentId = commentId.toString();
    const isOpening = !expandedCommentIds.has(normalizedCommentId);
    setExpandedCommentIds((current) => {
      const next = new Set(current);
      if (next.has(normalizedCommentId)) next.delete(normalizedCommentId);
      else next.add(normalizedCommentId);
      return next;
    });
    if (isOpening) loadReplies(commentId);
  };
  const refreshReplies = (commentId) => {
    const normalizedCommentId = commentId.toString();
    setExpandedCommentIds((current) => new Set([...current, normalizedCommentId]));
    loadReplies(commentId, { force: true });
    resource.reload();
  };
  async function submit(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const content = new FormData(form).get("content").trim();
    if (!content) return;
    setBusy(true);
    try {
      await api(commentsPath, {
        method: "POST",
        body: { content, author_role: user?.role },
      });
      form.reset();
      resource.reload();
      onCommentsChanged?.();
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  const composer = (
    <form
      onSubmit={submit}
      className={`inline-form${sheetStyle ? " comment-sheet-composer" : ""}`}
    >
      {sheetStyle && (
        <Avatar
          src={user?.profile_image}
          name={user?.nickname || "나"}
          size="comment-sheet-avatar"
        />
      )}
      <textarea
        name="content"
        aria-label="댓글"
        placeholder="댓글을 입력하세요."
        required
        maxLength={2000}
        rows={1}
      />
      {sheetStyle ? (
        <button
          type="submit"
          className="comment-sheet-submit"
          aria-label="댓글 등록"
          disabled={busy}
        >
          <Send size={20} aria-hidden="true" />
        </button>
      ) : (
        <Btn disabled={busy}>등록</Btn>
      )}
    </form>
  );
  return (
    <div className={`comments${sheetStyle ? " comments-sheet-content" : ""}`}>
      {!hideTitle && <h3>강의 이야기</h3>}
      {composerFirst && composer}
      <State resource={resource}>
        {commentRows.map((c) => (
          <CommentRow
            key={c.id}
            comment={c}
            lecture={id}
            reload={resource.reload}
            rootCommentId={c.id}
            repliesExpanded={expandedCommentIds.has(c.id.toString())}
            replies={replyThreads[c.id.toString()] || c.replies || []}
            repliesLoading={loadingReplyIds.has(c.id.toString())}
            repliesError={replyErrors[c.id.toString()]}
            onToggleReplies={() => toggleReplies(c.id)}
            onRetryReplies={() => loadReplies(c.id, { force: true })}
            onReplyUpdated={refreshReplies}
            onCommentsChanged={onCommentsChanged}
            activeMenuId={openCommentMenuId}
            onMoreMenuChange={(commentId, isOpen) =>
              setOpenCommentMenuId(isOpen ? commentId : null)
            }
            // Keep the outside-click boundary available to a nested reply menu
            // as well.  Passing it only when the root comment is open leaves a
            // reply menu without a ref, so its own pointerdown is mistaken for
            // an outside click before the edit/delete click handler can run.
            menuRef={commentMenuRef}
          />
        ))}
      </State>
      {(nextCommentsPath || loadMoreCommentsError) && (
        <div className="comments-load-more">
          {loadMoreCommentsError ? (
            <p>
              {loadMoreCommentsError}{" "}
              <button type="button" className="text-button" onClick={loadMoreComments}>
                다시 시도
              </button>
            </p>
          ) : (
            <div
              ref={loadMoreSentinelRef}
              className="comments-load-sentinel"
              aria-live="polite"
            >
              {isLoadingMoreComments && (
                <>
                  <LoaderCircle className="spin" size={16} aria-hidden="true" />
                  댓글을 불러오는 중...
                </>
              )}
            </div>
          )}
        </div>
      )}
      {!composerFirst && composer}
    </div>
  );
}
function CommentRow({
  comment: c,
  lecture,
  reload,
  reply = false,
  rootCommentId,
  repliesExpanded = false,
  replies = [],
  repliesLoading = false,
  repliesError,
  onToggleReplies,
  onRetryReplies,
  onReplyUpdated,
  onCommentsChanged,
  activeMenuId,
  onMoreMenuChange,
  menuRef,
}) {
  const { notify, user } = useContext(Ctx),
    [mode, setMode] = useState(""),
    [text, setText] = useState(""),
    [busy, setBusy] = useState(false);
  const replyTargetName = c.referenced_person_name || "";
  // Replies are fetched through a separate, paginated endpoint.  Keep the
  // server-provided flag as the primary source, but fall back to the author
  // user ID so an older/cached reply response cannot hide its own actions.
  const commentAuthorId =
    typeof c.author === "object" ? c.author?.id : c.author;
  const isMine =
    c.is_mine === true ||
    (commentAuthorId != null &&
      user?.id != null &&
      String(commentAuthorId) === String(user.id));
  const isMoreOpen = activeMenuId === c.id;
  const commentsPath = isPublicId(lecture)
    ? `/lectures/public/${lecture}/comments/`
    : `/lectures/${lecture}/comments/`;
  const startEditing = () => {
    setMode("edit");
    setText(c.content);
    onMoreMenuChange?.(c.id, false);
  };
  async function deleteComment() {
    if (!window.confirm("댓글을 삭제할까요?")) return;
    onMoreMenuChange?.(c.id, false);
    setBusy(true);
    try {
      await api(`/lectures/comments/${c.id}/`, { method: "DELETE" });
      if (reply) onReplyUpdated?.(rootCommentId || c.id);
      else reload();
      onCommentsChanged?.();
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api(
        mode === "edit"
          ? `/lectures/comments/${c.id}/`
          : commentsPath,
        {
          method: mode === "edit" ? "PATCH" : "POST",
          body:
            mode === "edit"
              ? { content: text }
              : {
                  content: text,
                  author_role: user?.role,
                  ...(mode === "reply"
                    ? { parent: c.parent || c.id, reply_to: c.id }
                    : {}),
                },
        },
      );
      setMode("");
      if (mode === "reply" || reply) {
        onReplyUpdated?.(rootCommentId || c.id);
      } else {
        reload();
      }
      onCommentsChanged?.();
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="comment">
      <Avatar
        src={c.author_profile_image || c.author?.profile_image}
        name={c.author_name || "수강생"}
        size="comment-avatar"
      />
      <div className="comment-header">
        <div className="comment-identity">
          <b>{c.author_name || "수강생"}</b>
          <small>{formatLectureTimeAgo(c.created_at)}</small>
        </div>
        <div className="comment-more" ref={isMoreOpen ? menuRef : null}>
          <button
            type="button"
            className="comment-more-button"
            aria-label="댓글 더보기"
            aria-expanded={isMoreOpen}
            aria-haspopup="menu"
            onClick={() => onMoreMenuChange?.(c.id, !isMoreOpen)}
          >
            <MoreVertical size={20} aria-hidden="true" />
          </button>
          {isMoreOpen && (
            <div className="comment-more-menu" role="menu">
              {isMine ? (
                <>
                  <button type="button" role="menuitem" onClick={startEditing}>
                    <Pencil size={16} aria-hidden="true" />
                    수정
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    disabled={busy}
                    onClick={deleteComment}
                  >
                    <Trash2 size={16} aria-hidden="true" />
                    삭제
                  </button>
                </>
              ) : (
                <ReportForm source="comment" id={c.id} label="신고" />
              )}
            </div>
          )}
        </div>
      </div>
      <p>
        {reply && replyTargetName && (
          <span className="comment-reply-target">@{replyTargetName} </span>
        )}
        {c.content}
      </p>
      <div className="comment-thread-controls">
        {!reply && Number(c.reply_count ?? c.replies?.length ?? 0) > 0 && (
          <button
            type="button"
            className="text-button"
            aria-expanded={repliesExpanded}
            onClick={onToggleReplies}
          >
            <span>답글 {c.reply_count ?? c.replies?.length ?? 0}개</span>
            <ChevronDown
              size={14}
              aria-hidden="true"
              className={repliesExpanded ? "is-expanded" : ""}
            />
          </button>
        )}
        <button
          type="button"
          className="text-button"
          aria-label={`${c.author_name || "수강생"}님에게 답글`}
          title={`${c.author_name || "수강생"}님에게 답글`}
          onClick={() => {
            setMode("reply");
            setText("");
          }}
        >
          <MessageCircle size={18} aria-hidden="true" />
          <span>답글 달기</span>
        </button>
      </div>
      {mode && (
        <>
          {mode === "reply" && (
            <p className="comment-replying-to">
              ↳ {c.author_name || "수강생"}님에게 답글
            </p>
          )}
          <form className="inline-form" onSubmit={save}>
            <textarea
              aria-label={mode === "edit" ? "댓글 수정" : "답글 내용"}
              placeholder={
                mode === "edit"
                  ? "댓글을 수정하세요"
                  : `${c.author_name || "수강생"}님에게 답글 작성...`
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
              required
              maxLength={2000}
              rows={1}
            />
            <Btn disabled={busy}>저장</Btn>
            <Btn type="button" onClick={() => setMode("")}>
              취소
            </Btn>
          </form>
        </>
      )}
      {!reply && repliesExpanded && repliesLoading && <ReplyThreadSkeleton />}
      {!reply && repliesExpanded && repliesError && (
        <div className="comment-reply-load-error" role="alert">
          <span>답글을 불러오지 못했어요.</span>
          <button type="button" className="text-button" onClick={onRetryReplies}>
            다시 시도
          </button>
        </div>
      )}
      {!reply && repliesExpanded && !repliesLoading && !repliesError && (
        <div className="comment-reply-list" aria-label="답글 목록">
          {replies.map((r) => (
            <CommentRow
              key={r.id}
              comment={r}
              lecture={lecture}
              reload={reload}
              reply
              rootCommentId={rootCommentId || c.id}
              onReplyUpdated={onReplyUpdated}
              onCommentsChanged={onCommentsChanged}
              activeMenuId={activeMenuId}
              onMoreMenuChange={onMoreMenuChange}
              menuRef={activeMenuId === r.id ? menuRef : null}
            />
          ))}
        </div>
      )}
    </article>
  );
}

function ReplyThreadSkeleton() {
  return (
    <div className="comment-reply-skeleton" role="status" aria-label="답글 불러오는 중">
      <span />
      <span />
    </div>
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
function isSupportRoomId(roomId) {
  return typeof roomId === "string" && roomId.startsWith("support:");
}

function supportConversationId(roomId) {
  return roomId.slice("support:".length);
}

function toSupportRoom(conversation) {
  return {
    id: `support:${conversation.id}`,
    is_support: true,
    official_instructor_id: conversation.official_instructor_id,
    official_instructor_public_id: conversation.official_instructor_public_id,
    title: conversation.title || "클래씨 공식 계정",
    opponent_info: {
      user_name: conversation.title || "클래씨 공식 계정",
      profile_image: conversation.profile_image || "",
      official_instructor_id: conversation.official_instructor_id,
      official_instructor_public_id: conversation.official_instructor_public_id,
    },
    last_message: conversation.last_message
      ? { text: conversation.last_message.content }
      : null,
    not_read_count: Number(conversation.unread_count) || 0,
  };
}

function toSupportChatDetail(conversation) {
  return {
    ...toSupportRoom(conversation),
    messages: (conversation.messages || []).map((message) => ({
      id: message.id,
      is_support: true,
      sender_kind: message.sender_kind,
      sender_nickname:
        message.sender_kind === "MEMBER"
          ? "나"
          : conversation.title || "클래씨 공식 계정",
      text: message.content,
      created_at: message.created_at,
      action: message.action,
    })),
  };
}

function Chat({ initialRoomId, onRoomClosed }) {
  const { user, notify, go, openTeacherProfile } = useContext(Ctx);
  const [likedOnly, setLikedOnly] = useState(false);
  const rooms = useLoad(
    `/chatrooms/?role=${user.role}${likedOnly ? "&liked=true" : ""}`,
    [user.role, likedOnly],
  );
  const supportRooms = useLoad(
    "/support/conversations/?role=" + user.role,
    [user.role],
  );
  const classResources = useLoad(`/tutoring/resources/?role=${user.role}`, [user.role]);
  const [selected, setSelected] = useState(null),
    [room, setRoom] = useState(null),
    [error, setError] = useState(""),
    [text, setText] = useState(""),
    [classInformation, setClassInformation] = useState(null),
    [failedText, setFailedText] = useState(""),
    [busy, setBusy] = useState(false),
    [updatingAction, setUpdatingAction] = useState(""),
    [moreOpen, setMoreOpen] = useState(false);
  const isSupportRoom = isSupportRoomId(selected);
  const selectedSupportConversationId = isSupportRoom
    ? supportConversationId(selected)
    : null;
  const chatRooms = [
    ...list(rooms.data).sort((left, right) => Number(right.is_liked) - Number(left.is_liked)),
    ...list(supportRooms.data).map(toSupportRoom),
  ];
  const selectedPublicId = isSupportRoom
    ? ""
    : room?.public_id ||
      chatRooms.find((item) => String(item.id) === String(selected))?.public_id ||
      (isPublicId(initialRoomId) ? initialRoomId : "");
  const currentClassResource =
    selected && !isSupportRoom
      ? getLatestClassResource(list(classResources.data), selected)
      : null;
  const registrationComplete = Boolean(
    currentClassResource && registrationStatus(currentClassResource).isComplete,
  );
  const canSend = Boolean(
    room &&
      (isSupportRoom || room.is_accepted || Number(room.initiated_by) !== Number(user.id)),
  );
  const roomName =
    room?.opponent_info?.nickname ||
    room?.opponent_info?.user_name ||
    room?.title ||
    "대화";
  const end = useRef();
  const lastRead = useRef("");
  useEffect(() => {
    if (!initialRoomId) {
      setSelected(null);
      setRoom(null);
      return;
    }
    const targetRoom = chatRooms.find(
      (item) => String(item.public_id) === String(initialRoomId),
    );
    if (!targetRoom) return;

    setSelected(targetRoom.id);
  }, [initialRoomId, rooms.data, supportRooms.data]);
  useEffect(() => {
    setMoreOpen(false);
  }, [selected]);
  useEffect(() => {
    if (!selected) return;
    setText(sessionStorage.getItem(`classy_chat_draft_${selected}`) || "");
    setFailedText("");
  }, [selected]);
  useEffect(() => {
    if (!selected) return;
    const key = `classy_chat_draft_${selected}`;
    if (text.trim()) sessionStorage.setItem(key, text);
    else sessionStorage.removeItem(key);
  }, [selected, text]);
  useEffect(() => {
    if (!selected) return;
    let alive = true,
      controller = new AbortController();
    setRoom(null);
    setError("");
    const load = () => {
      if (document.hidden) return;
      const detailPath = isSupportRoom
        ? `/support/conversations/${selectedSupportConversationId}/`
        : selectedPublicId
          ? `/chatrooms/public/${selectedPublicId}/?role=${user.role}`
          : `/chatrooms/${selected}/?role=${user.role}`;
      api(detailPath, {
        signal: controller.signal,
      })
        .then((d) => {
          if (alive) {
            const nextRoom = isSupportRoom ? toSupportChatDetail(d) : d;
            setRoom(nextRoom);
            setError("");
            const latest = nextRoom.messages?.at(-1);
            const key = selected + ":" + latest?.id;
            if (latest && lastRead.current !== key) {
              lastRead.current = key;
              const readPath = isSupportRoom
                ? `/support/conversations/${selectedSupportConversationId}/read/`
                : `/chatrooms/${selected}/read/${latest.id}/`;
              api(readPath, {
                method: "POST",
                body: {},
              })
                .then(() => {
                  if (alive) {
                    rooms.reload();
                    supportRooms.reload();
                  }
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
    const refresh = (event) => {
      if (event.event === "chat_summary" || event.event === "chat_read_state") {
        rooms.reload();
        supportRooms.reload();
        if (String(event.room_id) === String(selected)) load();
        return;
      }
      load();
    };
    const unsubscribeNotifications = subscribeWebSocket("/ws/notifications/", refresh);
    const roomSocketPath = isSupportRoom
      ? `/ws/support/conversations/${selectedSupportConversationId}/`
      : selectedPublicId
        ? `/ws/chat/public/${selectedPublicId}/`
        : `/ws/chat/${selected}/`;
    const unsubscribeRoom = subscribeWebSocket(roomSocketPath, refresh);
    return () => {
      alive = false;
      controller.abort();
      unsubscribeNotifications();
      unsubscribeRoom();
    };
  }, [selected, selectedPublicId, user.role]);
  useEffect(() => {
    if (!selected || isSupportRoom || registrationComplete) return undefined;
    const timer = window.setInterval(() => classResources.reload(), 10000);
    return () => window.clearInterval(timer);
  }, [selected, isSupportRoom, registrationComplete]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [room?.messages?.length]);
  async function send(e) {
    e.preventDefault();
    if (!text.trim() || busy || !canSend) return;
    setBusy(true);
    try {
      if (isSupportRoom) {
        try {
          await sendSupportMessageViaWebSocket(
            `/ws/support/conversations/${selectedSupportConversationId}/`,
            text.trim(),
          );
        } catch (error) {
          if (error?.sent) throw error;
          await api(
            `/support/conversations/${selectedSupportConversationId}/messages/`,
            { method: "POST", body: { content: text.trim() } },
          );
        }
      } else {
        const m = await api(`/chatrooms/${selected}/message/`, {
          method: "POST",
          body: { text: text.trim() },
        });
        setRoom((current) => ({
          ...current,
          messages: (current.messages || []).some((message) => message.id === m.id)
            ? current.messages
            : [...(current.messages || []), m],
        }));
      }
      setText("");
      setFailedText("");
      rooms.reload();
      supportRooms.reload();
    } catch (e) {
      setFailedText(text.trim());
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  function selectRoom(roomItem) {
    setSelected(roomItem.id);
    go(`chat/${roomItem.public_id}`);
  }
  function closeRoom() {
    setSelected(null);
    setRoom(null);
    setMoreOpen(false);
    onRoomClosed?.();
  }
  function openRegistration() {
    if (registrationComplete) {
      setClassInformation(currentClassResource);
      return;
    }
    if (!selectedPublicId) {
      notify("채팅방 정보를 불러오는 중이에요. 잠시 후 다시 시도해 주세요.");
      return;
    }
    go(`tutoring-registration/${selectedPublicId}`);
  }
  async function toggleLiked() {
    const previous = Boolean(room?.is_liked);
    const optimisticValue = !previous;
    setRoom((current) =>
      current ? { ...current, is_liked: optimisticValue } : current,
    );
    setUpdatingAction("like");
    try {
      const data = await api(`/chatrooms/${selected}/like/`, {
        method: "POST",
        body: {},
      });
      const isLiked = data.is_liked ?? optimisticValue;
      setRoom((current) => (current ? { ...current, is_liked: isLiked } : current));
      notify(isLiked ? "대화를 찜했습니다." : "찜을 해제했습니다.");
      rooms.reload();
    } catch (error) {
      setRoom((current) => (current ? { ...current, is_liked: previous } : current));
      notify(error.message);
    } finally {
      setUpdatingAction("");
    }
  }
  async function toggleMuted() {
    const previous = Boolean(room?.is_muted);
    const optimisticValue = !previous;
    setRoom((current) =>
      current ? { ...current, is_muted: optimisticValue } : current,
    );
    setUpdatingAction("mute");
    try {
      const data = await api(`/chatrooms/${selected}/mute/`, { method: "POST" });
      const isMuted = data.is_muted ?? optimisticValue;
      setRoom((current) => (current ? { ...current, is_muted: isMuted } : current));
      notify(isMuted ? "대화 알림을 껐습니다." : "대화 알림을 켰습니다.");
      rooms.reload();
    } catch (error) {
      setRoom((current) => (current ? { ...current, is_muted: previous } : current));
      notify(error.message);
    } finally {
      setUpdatingAction("");
    }
  }
  async function leaveRoom() {
    if (!window.confirm("채팅방을 삭제하고 나갈까요? 상대방의 대화도 삭제됩니다.")) {
      return;
    }
    try {
      await api(`/chatrooms/${selected}/out/`, { method: "DELETE" });
      closeRoom();
      rooms.reload();
    } catch (error) {
      notify(error.message);
    }
  }
  return (
    <>
      <div className={"chat-layout " + (selected ? "chat-room-selected" : "")}>
        <div className="room-list">
          <div className="room-list-head">
            <h3>나의 대화</h3>
            <Btn className="small" onClick={() => setLikedOnly((value) => !value)}>
              {likedOnly ? "전체" : "찜"}
            </Btn>
          </div>
          <State resource={rooms}>
            {chatRooms.map((r) => (
              (() => {
                const roomName =
                  r.opponent_info?.nickname ||
                  r.opponent_info?.user_name ||
                  r.title ||
                  "대화";
                return (
              <button
                key={r.id}
                className={selected === r.id ? "selected" : ""}
                onClick={() => selectRoom(r)}
              >
                <Avatar src={r.opponent_info?.profile_image} name={roomName} />
                <span>
                  <b>{roomName}</b>
                  <small>
                    {r.last_message?.text || "대화를 시작해 보세요"}
                  </small>
                </span>
                {r.not_read_count > 0 && <em>{r.not_read_count}</em>}
              </button>
                );
              })()
            ))}
            {!chatRooms.length && (
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
                <button
                  type="button"
                  className="chat-mobile-back"
                  onClick={closeRoom}
                  aria-label="대화 목록으로 돌아가기"
                >
                  <ChevronLeft size={22} aria-hidden="true" />
                </button>
                {isSupportRoom && room?.official_instructor_public_id ? (
                  <button
                    type="button"
                    className="support-profile-link"
                    onClick={() => openTeacherProfile(room.official_instructor_public_id)}
                    aria-label={`${room?.opponent_info?.user_name || room?.title || "클래씨 공식 계정"} 프로필 보기`}
                  >
                    <Avatar
                      src={room?.opponent_info?.profile_image}
                      name={room?.opponent_info?.user_name || room?.title || "클래씨 공식 계정"}
                    />
                    <b>
                      {room?.opponent_info?.nickname ||
                        room?.opponent_info?.user_name ||
                        room?.title ||
                        "대화"}
                    </b>
                    <ChevronRight size={16} aria-hidden="true" />
                  </button>
                ) : (
                  <b className="conversation-title">{roomName}</b>
                )}
                {!isSupportRoom && (
                  <div className="conversation-main-actions">
                  <Btn
                    className={registrationComplete ? "compact-action-button" : ""}
                    disabled={!room || classResources.loading}
                    onClick={openRegistration}
                  >
                    {registrationComplete && <Info size={16} aria-hidden="true" />}
                    {registrationComplete ? "수업 정보" : "성사 등록"}
                  </Btn>
                  <button
                    type="button"
                    className="chat-more-button"
                    onClick={() => setMoreOpen(true)}
                    aria-label="대화 더보기"
                    aria-haspopup="dialog"
                  >
                    <MoreVertical size={20} aria-hidden="true" />
                  </button>
                  </div>
                )}
              </div>
              {error && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}
              {room && !canSend && !isSupportRoom && (
                <p className="chat-acceptance-notice" role="status">
                  상대방이 수락한 뒤 메시지를 보낼 수 있어요.
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
                      "message " + (
                        (m.is_support
                          ? m.sender_kind === "MEMBER"
                          : m.sender === user.id)
                          ? "mine"
                          : ""
                      )
                    }
                  >
                    <small>{m.sender_nickname}</small>
                    {m.text && <p>{m.text}</p>}
                    {m.action?.url && (
                      <a
                        className="btn primary"
                        href={m.action.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {m.action.label || "고객센터 바로가기"}
                      </a>
                    )}
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
                  placeholder={canSend ? "메시지를 입력하세요" : "상대방이 수락한 뒤 메시지를 보낼 수 있어요."}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  maxLength={5000}
                  disabled={!room || !canSend}
                />
                <Btn
                  className="primary"
                  disabled={busy || !text.trim() || !canSend}
                  aria-label="메시지 보내기"
                >
                  <Send size={18} />
                </Btn>
              </form>
              {failedText && (
                <button
                  type="button"
                  className="text-button chat-retry"
                  onClick={() => {
                    setText(failedText);
                    setFailedText("");
                  }}
                >
                  전송에 실패했어요. 다시 작성하기
                </button>
              )}
            </>
          )}
        </div>
      </div>
      {moreOpen && room && !isSupportRoom && (
        <Modal
          title="대화 관리"
          onClose={() => setMoreOpen(false)}
          className="chat-actions-sheet"
        >
          <div className="chat-more-actions">
            <Btn
              disabled={updatingAction === "like"}
              onClick={toggleLiked}
            >
              <Star
                size={17}
                fill={room.is_liked ? "currentColor" : "none"}
                aria-hidden="true"
              />
              {room.is_liked ? "찜 해제" : "대화 찜하기"}
            </Btn>
            <Btn disabled={updatingAction === "mute"} onClick={toggleMuted}>
              {room.is_muted ? (
                <Bell size={17} aria-hidden="true" />
              ) : (
                <BellOff size={17} aria-hidden="true" />
              )}
              {room.is_muted ? "알림 켜기" : "알림 끄기"}
            </Btn>
            <ReportForm
              source="chat"
              id={selected}
              label="신고"
              className="chat-action-danger"
            />
            <BlockUserButton
              userId={room.opponent_info?.user_id}
              targetName={roomName}
              targetLabel={user.role === "instructor" ? "학생" : "선생님"}
              label="차단"
              className="chat-action-danger"
              onBlocked={() => {
                closeRoom();
                rooms.reload();
              }}
            />
            <Btn className="chat-action-danger" onClick={leaveRoom}>
              <LogOut size={17} aria-hidden="true" />
              채팅방 나가기
            </Btn>
          </div>
        </Modal>
      )}
      {classInformation && (
        <ClassInformationModal
          resource={classInformation}
          counterpartName={
            room?.opponent_info?.nickname ||
            room?.opponent_info?.user_name ||
            "상대방"
          }
          onClose={() => setClassInformation(null)}
        />
      )}
    </>
  );
}
const legacyHash = location.hash.slice(1);
const legacyPage = legacyHash.split("/")[0];
const isLegacyAppRoute = Boolean(legacyHash) && pageNames[legacyPage];

if (isLegacyAppRoute) {
  // URL fragments never reach Nginx, so legacy link canonicalization must be
  // performed in the browser after the existing numeric API resolves it.
  resolveLegacyPath(legacyHash).then((destination) => location.replace(destination));
} else {
  const root = document.getElementById("root");
  const isPublicLanding = location.pathname === "/" && !location.hash;

  if (isPublicLanding) {
    // The landing HTML is prerendered for crawlers and no-JavaScript visitors.
    // Mount it as a client view so React's automatic image resource hints do
    // not produce a hydration mismatch with Vite's static document template.
    createRoot(root).render(<LandingPage />);
  } else {
    createRoot(root).render(<App />);
  }
}
