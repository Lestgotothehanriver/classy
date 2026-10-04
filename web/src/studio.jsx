import React, { useContext, useEffect, useRef, useState } from "react";
import { api, apiPath, errorText, list } from "./api";
import { Ctx, Btn, State, Empty, useLoad, money, Modal } from "./shared";
import { PageHeading } from "./design";

export function uploadLecture(body, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiPath("/lectures/write/"));
    xhr.setRequestHeader(
      "Authorization",
      "Token " + sessionStorage.getItem("classy_token"),
    );
    xhr.timeout = 900000;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable)
        onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        data = { detail: "서버 응답을 확인할 수 없습니다." };
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else {
        if (xhr.status === 401)
          window.dispatchEvent(new Event("classy:expired"));
        reject(new Error(errorText(data)));
      }
    };
    xhr.onerror = xhr.ontimeout = () =>
      reject(
        new Error(
          "연결이 끊겼습니다. 서버에서 처리 중일 수 있으니 콘텐츠 목록을 확인한 뒤 다시 시도하세요.",
        ),
      );
    xhr.send(body);
  });
}
function useFileUrl(file) {
  const [url, set] = useState("");
  useEffect(() => {
    if (!file) {
      set("");
      return;
    }
    const value = URL.createObjectURL(file);
    set(value);
    return () => URL.revokeObjectURL(value);
  }, [file]);
  return url;
}
const initial = {
  title: "",
  content: "",
  price: "0",
  subjects: [],
  is_preview: false,
};
export function Studio({ upload = false }) {
  const { user, subjects, notify, go } = useContext(Ctx),
    [tab, setTab] = useState(upload ? "upload" : "content");
  const content = useLoad(
    user.role === "instructor" ? "/mypage/instructor/uploaded-lectures/" : null,
  );
  const [edit, setEdit] = useState(null),
    [search, setSearch] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  if (user.role !== "instructor")
    return (
      <Empty
        title="선생님 전용 공간이에요"
        text="선생님 계정으로 전환하면 강의를 관리할 수 있습니다."
      />
    );
  const rows = list(content.data),
    filtered = rows.filter((x) =>
      x.title.toLowerCase().includes(search.toLowerCase()),
    );
  return (
    <>
      <PageHeading
        title="강사 스튜디오"
        description="좋은 강의를 만들고, 학생과 만나는 과정을 한곳에서."
      >
        <Btn
          className="primary"
          disabled={uploadBusy}
          onClick={() => setTab("upload")}
        >
          새 강의 업로드
        </Btn>
      </PageHeading>
      <div className="studio-layout">
        <aside className="catalog-aside">
          <nav aria-label="스튜디오 메뉴">
            <button
              className={tab === "content" ? "active" : ""}
              disabled={uploadBusy}
              onClick={() => {
                setTab("content");
                content.reload();
              }}
            >
              콘텐츠
            </button>
            <button
              className={tab === "upload" ? "active" : ""}
              disabled={uploadBusy}
              onClick={() => setTab("upload")}
            >
              업로드
            </button>
            <button onClick={() => go("settlement")}>수익 및 정산</button>
            <button onClick={() => go("verification")}>강사 인증</button>
          </nav>
        </aside>
        <section>
          {tab === "upload" ? (
            <UploadForm
              onBusy={setUploadBusy}
              onComplete={() => {
                content.reload();
                setTab("content");
              }}
            />
          ) : (
            <State resource={content}>
              <div className="studio-summary">
                <span>
                  등록 강의 <b>{rows.length}</b>
                </span>
                <span>
                  판매 중 <b>{rows.filter((x) => x.is_active).length}</b>
                </span>
                <span>
                  조회수 합계{" "}
                  <b>
                    {money(rows.reduce((n, x) => n + (x.view_count || 0), 0))}
                  </b>
                </span>
              </div>
              <label className="form">
                내 강의 검색
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="강의 제목"
                />
              </label>
              {filtered.length ? (
                <div className="studio-list">
                  {filtered.map((item) => (
                    <article key={item.id} className="studio-row">
                      {item.thumbnail && <img src={item.thumbnail} alt="" />}
                      <div>
                        <h3>{item.title}</h3>
                        <p className="muted">
                          {item.is_preview ? "프리뷰 · " : ""}
                          {item.is_active ? "판매 중" : "판매 중지"} ·{" "}
                          {money(item.price)} 캐시 · 조회{" "}
                          {money(item.view_count)}
                        </p>
                      </div>
                      <Btn onClick={() => setEdit(item)}>관리</Btn>
                    </article>
                  ))}
                </div>
              ) : (
                <Empty
                  title="등록한 강의가 없습니다"
                  text="첫 강의를 업로드하고 학생들과 만나보세요."
                />
              )}
            </State>
          )}
        </section>
      </div>
      {edit && (
        <ManageLecture
          item={edit}
          onClose={() => setEdit(null)}
          onSaved={() => {
            setEdit(null);
            content.reload();
          }}
        />
      )}
    </>
  );
}
function UploadForm({ onComplete, onBusy }) {
  const { user, subjects, notify } = useContext(Ctx),
    key = "classy_draft_" + user.id;
  const [draft, setDraft] = useState(() => {
    try {
      return { ...initial, ...JSON.parse(localStorage.getItem(key) || "{}") };
    } catch {
      return initial;
    }
  });
  const [video, setVideo] = useState(null),
    [thumbnail, setThumbnail] = useState(null),
    [duration, setDuration] = useState(0);
  const [videoReady, setVideoReady] = useState(false);
  const [busy, setBusy] = useState(false),
    [progress, setProgress] = useState(0),
    [error, setError] = useState(""),
    [saved, setSaved] = useState(false);
  const videoUrl = useFileUrl(video),
    thumbUrl = useFileUrl(thumbnail),
    player = useRef();
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(draft));
      setSaved(true);
    } catch {
      setSaved(false);
    }
  }, [draft, key]);
  useEffect(() => {
    const guard = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    if (busy) window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [busy]);
  useEffect(() => {
    onBusy(busy);
    window.dispatchEvent(new CustomEvent("classy:uploading", { detail: busy }));
    return () => {
      onBusy(false);
      window.dispatchEvent(
        new CustomEvent("classy:uploading", { detail: false }),
      );
    };
  }, [busy, onBusy]);
  const field = (name, value) => setDraft((d) => ({ ...d, [name]: value }));
  function chooseVideo(file) {
    if (!file) return;
    if (!file.type.startsWith("video/") || file.size > 950 * 1024 * 1024) {
      setError("950MB 이하의 영상 파일을 선택해 주세요.");
      return;
    }
    setVideo(file);
    setDuration(0);
    setVideoReady(false);
    setError("");
  }
  async function capture() {
    try {
      const v = player.current;
      if (!v?.videoWidth) throw new Error("영상을 먼저 불러와 주세요.");
      const c = document.createElement("canvas");
      c.width = v.videoWidth;
      c.height = v.videoHeight;
      c.getContext("2d").drawImage(v, 0, 0);
      const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.9));
      if (!blob) throw new Error("썸네일을 만들지 못했습니다.");
      setThumbnail(new File([blob], "thumbnail.jpg", { type: "image/jpeg" }));
    } catch (e) {
      setError(e.message);
    }
  }
  async function submit(e) {
    e.preventDefault();
    if (busy) return;
    setError("");
    if (!video || !videoReady || !thumbnail || !draft.subjects.length) {
      setError("영상 재생 가능 여부, 썸네일, 과목을 확인해 주세요.");
      return;
    }
    if (
      draft.is_preview &&
      !window.confirm(
        "프리뷰는 선생님당 1개입니다. 기존 프리뷰가 있다면 교체됩니다. 계속할까요?",
      )
    )
      return;
    setBusy(true);
    setProgress(0);
    const body = new FormData();
    for (const name of ["title", "content", "price", "is_preview"])
      body.append(name, String(draft[name]));
    draft.subjects.forEach((x) => body.append("subjects", x));
    body.append("video", video);
    body.append("thumbnail", thumbnail);
    body.append("video_duration", String(Math.floor(duration)));
    try {
      await uploadLecture(body, setProgress);
      localStorage.removeItem(key);
      notify("강의 등록이 완료되었습니다.");
      onComplete();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="upload-layout">
      <fieldset disabled={busy} className="form-fields form">
        <div className="section-title">
          <h2>강의 업로드</h2>
          <small className="muted">
            {saved ? "작성 내용 자동 저장됨" : "자동 저장 사용 불가"}
          </small>
        </div>
        <p className="form-note">
          제목과 소개는 이 브라우저에 임시 저장됩니다. 영상·이미지 파일은 다시
          선택해야 합니다.
        </p>
        <label
          className="upload-drop"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (!busy) chooseVideo(e.dataTransfer.files[0]);
          }}
        >
          강의 영상 선택 또는 끌어놓기
          <input
            type="file"
            accept="video/*"
            onChange={(e) => chooseVideo(e.target.files[0])}
          />
          <small>
            {video
              ? `${video.name} · ${(video.size / 1024 / 1024).toFixed(1)} MB`
              : "최대 950MB · MP4 권장"}
          </small>
        </label>
        {videoUrl && (
          <>
            <video
              ref={player}
              src={videoUrl}
              controls
              className="video"
              onLoadedMetadata={(e) => {
                setVideoReady(e.target.videoWidth > 0);
                setDuration(
                  Number.isFinite(e.target.duration) ? e.target.duration : 0,
                );
              }}
              onError={() => {
                setDuration(0);
                setVideoReady(false);
                setError(
                  "이 브라우저에서 영상을 읽을 수 없습니다. MP4 파일을 선택해 주세요.",
                );
              }}
            />
            <Btn type="button" onClick={capture}>
              현재 장면을 썸네일로 사용
            </Btn>
          </>
        )}
        <label>
          강의 제목
          <input
            value={draft.title}
            onChange={(e) => field("title", e.target.value)}
            maxLength={200}
            required
          />
          <small>{draft.title.length}/200</small>
        </label>
        <label>
          강의 소개
          <textarea
            value={draft.content}
            onChange={(e) => field("content", e.target.value)}
            rows={7}
            required
            placeholder="누구를 위한 강의인가요? 학습 목표, 준비물, 수업 순서를 알려주세요."
          />
        </label>
        <label>
          과목 (최대 3개)
          <select
            multiple
            size={6}
            value={draft.subjects.map(String)}
            onChange={(e) => {
              const values = [...e.target.selectedOptions].map((x) =>
                Number(x.value),
              );
              if (values.length > 3) {
                setError("과목은 최대 3개입니다.");
                return;
              }
              field("subjects", values);
            }}
          >
            {subjects.map((s) => (
              <option key={s.number} value={s.number}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          수강료 (캐시)
          <input
            type="number"
            min="0"
            max="2147483647"
            step="1"
            required
            value={draft.price}
            onChange={(e) => field("price", e.target.value)}
          />
        </label>
        <label className="check-label">
          <input
            type="checkbox"
            checked={draft.is_preview}
            onChange={(e) => field("is_preview", e.target.checked)}
          />
          무료 프리뷰 강의로 등록
        </label>
        <label>
          썸네일 이미지
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(e) => {
              const f = e.target.files[0];
              if (f && f.size > 10 * 1024 * 1024) {
                setError("썸네일은 10MB 이하로 선택해 주세요.");
                return;
              }
              setThumbnail(f);
            }}
          />
        </label>
      </fieldset>
      <aside className="upload-preview">
        <h2>게시 전 확인</h2>
        {thumbUrl && <img src={thumbUrl} alt="선택한 썸네일" />}
        <h3>{draft.title || "강의 제목"}</h3>
        <p>
          {draft.is_preview
            ? "무료 프리뷰"
            : `${money(draft.price)} 캐시 · 30일 대여`}
        </p>
        <ul className="publish-checklist">
          {[
            [!!video && videoReady, "영상 확인"],
            [!!thumbnail, "썸네일 준비"],
            [
              !!draft.title.trim() && !!draft.content.trim(),
              "제목과 소개 작성",
            ],
            [draft.subjects.length > 0, "과목 선택"],
          ].map(([ok, label]) => (
            <li key={label}>
              {ok ? "✓" : "○"} {label}
            </li>
          ))}
        </ul>
        <p className="form-note">
          게시하면 학생에게 바로 표시됩니다. 업로드가 끝난 후 서버에서 영상을
          처리하는 동안 잠시 기다려 주세요.
        </p>
        {busy && (
          <div role="status">
            <progress max="100" value={progress} />
            <p>
              {progress === 100
                ? "업로드 완료 · 영상 처리 중…"
                : `업로드 중 ${progress}%`}
            </p>
          </div>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <Btn className="primary full" disabled={busy}>
          {busy ? "등록 중…" : "강의 게시"}
        </Btn>
      </aside>
    </form>
  );
}
function ManageLecture({ item, onClose, onSaved }) {
  const { notify } = useContext(Ctx),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function action(path, method, body) {
    setBusy(true);
    setError("");
    try {
      await api("/lectures/write/" + item.id + "/" + path, { method, body });
      notify("변경사항을 반영했습니다.");
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="강의 관리" onClose={onClose}>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          const d = Object.fromEntries(new FormData(e.currentTarget));
          d.price = Number(d.price);
          action("", "PATCH", d);
        }}
      >
        <label>
          제목
          <input
            name="title"
            defaultValue={item.title}
            required
            maxLength={200}
          />
        </label>
        <label>
          소개
          <textarea name="content" defaultValue={item.content} rows={5} />
        </label>
        <label>
          수강료
          <input
            name="price"
            type="number"
            min="0"
            step="1"
            defaultValue={item.price}
            required
          />
        </label>
        <Btn className="primary" disabled={busy}>
          수정 저장
        </Btn>
      </form>
      <div className="actions">
        <Btn
          disabled={busy}
          onClick={() => {
            if (
              window.confirm(
                item.is_active
                  ? "신규 대여를 중지할까요? 기존 수강생의 대여 권한은 유지됩니다."
                  : "강의 판매를 재개할까요?",
              )
            )
              action(item.is_active ? "stop-sales/" : "resume-sales/", "POST");
          }}
        >
          {item.is_active ? "판매 중지" : "판매 재개"}
        </Btn>
        <Btn
          disabled={busy}
          onClick={() => {
            if (
              window.confirm(
                "강의를 삭제할까요? 삭제 조건을 충족해야 하며 삭제 후 되돌릴 수 없습니다.",
              )
            )
              action("", "DELETE");
          }}
        >
          강의 삭제
        </Btn>
      </div>
      <p className="form-note">
        삭제는 판매 중지 후 30일이 지나고 유효한 대여자가 없을 때 가능합니다.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </Modal>
  );
}
