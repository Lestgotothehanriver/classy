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
  Plus,
  Check,
  Upload,
  Leaf,
} from "lucide-react";
import { api, list } from "./api";
import { Auth } from "./auth";
import { Studio } from "./studio";
import { Services, ReportForm } from "./services";
import { Registration } from "./contracts";
import "./redesign.css";
import {
  Ctx,
  money,
  date,
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
  Catalog,
  Profile,
  endpoints,
  pageNames,
} from "./design";
function App() {
  const uploadLock = useRef(false);
  const [activeRole, setActiveRole] = useState(
    sessionStorage.getItem("classy_role") || "",
  );
  const [user, setUser] = useState(null),
    [ready, setReady] = useState(false);
  const [page, setPage] = useState(
    pageNames[location.hash.slice(1)] ? location.hash.slice(1) : "home",
  );
  const [modal, setModal] = useState(null),
    [toast, setToast] = useState("");
  const pageRef = useRef(page);
  pageRef.current = page;
  const subjects = useLoad("/accounts/subjects/");
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
      const next = location.hash.slice(1);
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
  const go = (p) => {
    location.hash = p;
  };
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
    detail: (kind, id) => {
      setToast("");
      setModal({ type: "detail", kind, id });
    },
    refreshUser: () => api("/accounts/me/").then(setUser),
    setRole: (role) => changeRole(role),
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
              <Chat />
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
          onClose={() => setModal(null)}
        />
      )}
    </Ctx.Provider>
  );
}
function Detail({ kind, id, onClose }) {
  const { notify, user, refreshUser } = useContext(Ctx);
  const base = (endpoints[kind] || "/lectures/") + id + "/";
  const resource = useLoad(base);
  const [busy, setBusy] = useState(false),
    [video, setVideo] = useState(""),
    [liked, setLiked] = useState(null),
    [rented, setRented] = useState(false),
    [rentConfirm, setRentConfirm] = useState(false);
  const d = resource.data?.lecture_info || resource.data || {};
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
        <Subjects values={d.subjects} />
        <h2 className="detail-title">
          {d.title || d.user_name || d.instructor?.user_name || "수업 소개"}
        </h2>
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
                  {d.video_duration
                    ? Math.ceil(d.video_duration / 60) + "분"
                    : "확인 중"}
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
            {resource.data?.preview_video?.video && (
              <Btn
                className="full"
                onClick={() => setVideo(resource.data.preview_video.video)}
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
              이용 내역과 쿠폰을 확인하세요.
            </p>
            <Comments id={id} />
          </>
        ) : (
          <>
            <div className="detail-facts">
              <span>
                수업 방식
                <strong>
                  {d.method === "ONLINE"
                    ? "온라인"
                    : d.method === "OFFLINE"
                      ? "대면"
                      : "상담 후 결정"}
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
            {kind === "teachers" && <TeacherInfo id={id} />}
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
function TeacherInfo({ id }) {
  const info = useLoad(`/tutoring/instructors/${id}/info/`),
    reviews = useLoad(`/tutoring/instructors/${id}/reviews/`);
  return (
    <>
      <State resource={info}>
        {info.data && (
          <div className="info-panel">
            <h3>수업 안내</h3>
            <p>
              {info.data.instruction ||
                info.data.etc ||
                "선생님과 상담하며 수업을 정해 보세요."}
            </p>
            <p>
              {info.data.cost_display || ""} {info.data.schedule || ""}{" "}
              {info.data.location || ""}
            </p>
          </div>
        )}
      </State>
      <h3>수강 후기</h3>
      <State resource={reviews}>
        {list(reviews.data).length ? (
          list(reviews.data).map((r, i) => (
            <div className="comment" key={r.id || i}>
              <b>{r.student_name || r.user_name || "수강생"}</b>
              <p>{r.comment || r.content || r.review}</p>
            </div>
          ))
        ) : (
          <p className="muted">아직 등록된 후기가 없어요.</p>
        )}
      </State>
    </>
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
  const r = useLoad(`/notification/?page=${notificationPage}`);
  const { notify } = useContext(Ctx);
  return (
    <>
      <div className="actions">
        <Btn
          onClick={async () => {
            try {
              await api("/notification/read-all/", {
                method: "POST",
                body: {},
              });
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
                  onClick={async () => {
                    try {
                      await api(`/notification/${n.id}/read/`, {
                        method: "POST",
                      });
                      r.reload();
                    } catch (e) {
                      notify(e.message);
                    }
                  }}
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
function Chat() {
  const { user, notify } = useContext(Ctx);
  const rooms = useLoad("/chatrooms/?role=" + user.role);
  const [selected, setSelected] = useState(null),
    [room, setRoom] = useState(null),
    [error, setError] = useState(""),
    [text, setText] = useState(""),
    [busy, setBusy] = useState(false);
  const end = useRef();
  const lastRead = useRef("");
  const [attachments, setAttachments] = useState([]),
    [registration, setRegistration] = useState(false);
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
    end.current?.scrollIntoView({ block: "nearest" });
  }, [room?.messages?.length]);
  async function send(e) {
    e.preventDefault();
    if ((!text.trim() && !attachments.length) || busy) return;
    setBusy(true);
    try {
      let img_ids = [];
      if (attachments.length) {
        const body = new FormData();
        attachments.forEach((f) => body.append("images", f));
        const uploaded = await api("/images/", { method: "POST", body });
        img_ids = uploaded.image_ids;
      }
      const m = await api(`/chatrooms/${selected}/message/`, {
        method: "POST",
        body: { text: text.trim(), ...(img_ids.length ? { img_ids } : {}) },
      });
      setRoom((r) => ({ ...r, messages: [...(r.messages || []), m] }));
      setText("");
      setAttachments([]);
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
                  setAttachments([]);
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
                  <Btn disabled={!room} onClick={() => setRegistration(true)}>
                    성사 등록
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
                <label className="chat-attach" title="이미지 첨부">
                  +
                  <input
                    type="file"
                    aria-label="대화 이미지 첨부"
                    multiple
                    accept="image/*"
                    disabled={busy || !room}
                    onChange={(e) => {
                      const files = [...e.target.files];
                      if (
                        files.length > 5 ||
                        files.some((f) => f.size > 10 * 1024 * 1024)
                      ) {
                        notify("이미지는 10MB 이하, 최대 5개까지 첨부하세요.");
                        return;
                      }
                      setAttachments(files);
                      e.target.value = "";
                    }}
                  />
                </label>
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
                  disabled={
                    busy || (!text.trim() && !attachments.length) || !room
                  }
                  aria-label="메시지 보내기"
                >
                  <Send size={18} />
                </Btn>
              </form>
              {attachments.length > 0 && (
                <div className="actions">
                  {attachments.map((f, i) => (
                    <button
                      key={i}
                      className="text-button"
                      onClick={() =>
                        setAttachments((a) => a.filter((_, n) => n !== i))
                      }
                    >
                      {f.name} ×
                    </button>
                  ))}
                </div>
              )}
              <ReportForm source="chat" id={selected} />
            </>
          )}
        </div>
      </div>
      {registration && room && (
        <Registration room={room} onClose={() => setRegistration(false)} />
      )}
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
