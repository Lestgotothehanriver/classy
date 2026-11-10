import React, { useContext, useEffect, useRef, useState } from "react";
import { Check, Search } from "lucide-react";
import { api, list } from "./api";
import { Ctx, Btn, State, Empty, useLoad, money, Modal } from "./shared";
import { PageHeading } from "./design";

export function uploadLecture(body, onProgress) {
  const video = body.get("video");
  if (!(video instanceof File))
    return Promise.reject(new Error("업로드할 영상을 찾을 수 없습니다."));

  return api("/lectures/uploads/initiate/", {
    method: "POST",
    body: {
      filename: video.name,
      content_type: "video/mp4",
      size: video.size,
    },
  }).then(async (upload) => {
    await uploadLectureVideoToS3(upload, video, onProgress);
    body.delete("video");
    return api(`/lectures/uploads/${upload.upload_id}/complete/`, {
      method: "POST",
      body,
      signal: AbortSignal.timeout(90000),
    });
  });
}

function uploadLectureVideoToS3(upload, video, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", upload.url);
    xhr.timeout = 900000;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable)
        onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error("영상 저장소 업로드에 실패했습니다. 다시 시도해주세요."));
    };
    xhr.onerror = xhr.ontimeout = () =>
      reject(
        new Error(
          "영상 저장소 연결이 끊겼습니다. 다시 시도해주세요.",
        ),
      );
    const form = new FormData();
    Object.entries(upload.fields).forEach(([name, value]) => form.append(name, value));
    form.append("file", video);
    xhr.send(form);
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
  price: 0,
  subjects: [],
  is_preview: false,
};

/** 앱의 SignupData.allSubjects와 같은 과목 카테고리별 번호 범위다. */
const subjectCategoryRanges = [
  ["초등", 1, 8],
  ["중등", 9, 17],
  ["고등국어", 18, 31],
  ["고등영어", 32, 34],
  ["고등수학", 35, 53],
  ["고등사회", 54, 80],
  ["고등과학", 81, 107],
  ["제2외국어", 108, 116],
  ["직업탐구", 117, 122],
  ["논술", 123, 130],
  ["기타 국내", 131, 146],
  ["유학", 147, 155],
  ["영어", 156, 164],
  ["외국어", 165, 200],
  ["프로그래밍", 201, 218],
  ["개발", 219, 224],
  ["미술", 225, 241],
  ["악기", 242, 266],
  ["음악", 267, 279],
];

/** 자동 썸네일에 사용할 영상 프레임 시점(초)이다. */
const thumbnailFrameSecond = 1;

/** 웹·앱 공통 강의 가격 정책에 맞춰 캐시 가격을 보정한다. */
function normalizeLecturePrice(value) {
  const price = Number(value);
  if (!Number.isFinite(price)) return 0;
  return Math.min(1000, Math.max(0, Math.round(price / 100) * 100));
}

/** 선택한 과목을 여러 개 유지하는 강의·회원가입 공용 과목 선택 다이얼로그다. */
export function SubjectPicker({
  subjects,
  selectedIds,
  onChange,
  onClose,
  maxSelections,
}) {
  const categoryGroups = subjectCategoryRanges
    .map(([name, start, end]) => ({
      name,
      subjects: subjects.filter(
        (subject) => subject.number >= start && subject.number <= end,
      ),
    }))
    .filter((category) => category.subjects.length > 0);
  const categorizedSubjectIds = new Set(
    categoryGroups.flatMap((category) =>
      category.subjects.map((subject) => subject.number),
    ),
  );
  const uncategorizedSubjects = subjects.filter(
    (subject) => !categorizedSubjectIds.has(subject.number),
  );
  if (uncategorizedSubjects.length > 0)
    categoryGroups.push({ name: "기타", subjects: uncategorizedSubjects });
  const [selectedCategoryName, setSelectedCategoryName] = useState(
    categoryGroups[0]?.name || "",
  );
  const selectedCategory =
    categoryGroups.find((category) => category.name === selectedCategoryName) ||
    categoryGroups[0];
  const selectedIdSet = new Set(selectedIds);
  function toggleSubject(subjectId) {
    if (
      !selectedIdSet.has(subjectId) &&
      maxSelections &&
      selectedIds.length >= maxSelections
    )
      return;
    onChange(
      selectedIdSet.has(subjectId)
        ? selectedIds.filter((id) => id !== subjectId)
        : [...selectedIds, subjectId],
    );
  }
  return (
    <Modal
      title={`과목 선택 ${selectedIds.length}${maxSelections ? `/${maxSelections}` : ""}개`}
      onClose={onClose}
      wide
    >
      <div className="subject-picker-layout">
        <nav className="subject-category-list" aria-label="과목 카테고리">
          {categoryGroups.map((category) => (
            <button
              type="button"
              key={category.name}
              className={
                selectedCategory?.name === category.name ? "selected" : ""
              }
              aria-pressed={selectedCategory?.name === category.name}
              onClick={() => setSelectedCategoryName(category.name)}
            >
              {category.name}
            </button>
          ))}
        </nav>
        <div className="subject-picker-list">
          {selectedCategory?.subjects.map((subject) => {
            const isSelected = selectedIdSet.has(subject.number);
            return (
              <button
                type="button"
                key={subject.number}
                className={isSelected ? "selected" : ""}
                aria-pressed={isSelected}
                disabled={
                  !isSelected &&
                  Boolean(maxSelections) &&
                  selectedIds.length >= maxSelections
                }
                onClick={() => toggleSubject(subject.number)}
              >
                <span>{subject.name}</span>
                {isSelected && <Check size={20} aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      </div>
      <div className="subject-picker-actions">
        <Btn type="button" className="primary full" onClick={onClose}>
          선택 완료
        </Btn>
      </div>
    </Modal>
  );
}
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
        title="강의 스튜디오"
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
      const savedDraft = JSON.parse(localStorage.getItem(key) || "{}");
      return {
        ...initial,
        ...savedDraft,
        price: normalizeLecturePrice(savedDraft.price),
      };
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
  const [subjectPickerOpen, setSubjectPickerOpen] = useState(false);
  const videoUrl = useFileUrl(video),
    thumbUrl = useFileUrl(thumbnail);
  const thumbnailInputRef = useRef(null);
  const thumbnailGenerationRef = useRef(0);
  const hasManualThumbnailRef = useRef(false);
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
  const togglePreview = (isPreview) =>
    setDraft((current) => ({
      ...current,
      is_preview: isPreview,
      price: isPreview ? 0 : current.price,
    }));
  function setThumbnailFile(file, { manuallySelected = false } = {}) {
    if (!file) return;
    if (manuallySelected) hasManualThumbnailRef.current = true;
    setThumbnail(file);

    // 브라우저 기본 파일 입력에도 자동 생성 JPEG를 넣어 선택 상태를 표시한다.
    const input = thumbnailInputRef.current;
    if (!input) return;
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    input.files = dataTransfer.files;
  }
  function chooseVideo(file) {
    if (!file) return;
    if (!file.type.startsWith("video/") || file.size > 950 * 1024 * 1024) {
      setError("950MB 이하의 영상 파일을 선택해 주세요.");
      return;
    }
    thumbnailGenerationRef.current += 1;
    hasManualThumbnailRef.current = false;
    setVideo(file);
    setThumbnail(null);
    if (thumbnailInputRef.current) thumbnailInputRef.current.value = "";
    setDuration(0);
    setVideoReady(false);
    setError("");
  }
  function generateThumbnailFromVideoFrame(videoElement) {
    const generation = thumbnailGenerationRef.current;
    if (
      hasManualThumbnailRef.current ||
      !videoElement.videoWidth ||
      !videoElement.videoHeight
    )
      return;

    const captureFrame = () => {
      const width = Math.min(720, videoElement.videoWidth);
      const height = Math.round(
        (videoElement.videoHeight * width) / videoElement.videoWidth,
      );
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      canvas.getContext("2d")?.drawImage(videoElement, 0, 0, width, height);
      canvas.toBlob((blob) => {
        if (
          !blob ||
          generation !== thumbnailGenerationRef.current ||
          hasManualThumbnailRef.current
        )
          return;
        setThumbnailFile(
          new File([blob], "video-thumbnail.jpg", { type: "image/jpeg" }),
        );
      }, "image/jpeg", 0.85);
    };

    const targetTime =
      Number.isFinite(videoElement.duration) &&
      videoElement.duration <= thumbnailFrameSecond
        ? 0
        : thumbnailFrameSecond;
    if (Math.abs(videoElement.currentTime - targetTime) < 0.01) {
      captureFrame();
      return;
    }
    videoElement.addEventListener("seeked", captureFrame, { once: true });
    videoElement.currentTime = targetTime;
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
    for (const name of ["title", "price", "is_preview"])
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
    <>
      <form onSubmit={submit} className="upload-layout">
      <fieldset disabled={busy} className="form-fields form">
        <div className="section-title">
          <h2>강의 업로드</h2>
          <small className="muted">
            {saved ? "작성 내용 자동 저장됨" : "자동 저장 사용 불가"}
          </small>
        </div>
        <p className="form-note">
          제목과 설정은 이 브라우저에 임시 저장됩니다. 영상·이미지 파일은 다시
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
              : "영상을 선택해주세요."}
          </small>
        </label>
        <p className="upload-spec">
          권장 규격: 16:9 · MP4(H.264/AVC 비디오 + AAC 오디오) · 1920×1080px 이하
        </p>
        <details className="codec-guide">
          <summary>아이폰·갤럭시 HEVC(H.265) 영상 변환 안내</summary>
          <p>
            <strong>MP4 확장자여도 HEVC(H.265) 영상은 업로드할 수 없습니다.</strong>
            <br />
            MP4 컨테이너에 H.264/AVC 비디오와 AAC 오디오로 저장된 파일만 지원합니다.
          </p>
          <ul>
            <li>
              <strong>iPhone로 촬영 시:</strong> 설정 → 카메라 → 포맷 → “높은 호환성”을
              선택해 주세요.
            </li>
            <li>
              <strong>Galaxy로 촬영 시:</strong> 카메라 → 설정 → 고급 동영상 옵션 →
              “고효율 동영상(HEVC)”을 꺼주세요.
            </li>
            <li>
              <strong>이미 촬영한 영상:</strong> 사진/갤러리의 공유·내보내기에서 호환 형식
              또는 H.264 옵션을 선택해 주세요. 옵션이 없으면 Mac 사진 앱의 내보내기나 Windows
              HandBrake로 H.264 MP4로 변환한 뒤 업로드해 주세요.
            </li>
          </ul>
        </details>
        {videoUrl && (
          <>
            <video
              src={videoUrl}
              controls
              className="video"
              onLoadedMetadata={(e) => {
                setVideoReady(e.target.videoWidth > 0);
                setDuration(
                  Number.isFinite(e.target.duration) ? e.target.duration : 0,
                );
              }}
              onLoadedData={(e) => generateThumbnailFromVideoFrame(e.currentTarget)}
              onError={() => {
                setDuration(0);
                setVideoReady(false);
                setError(
                  "이 브라우저에서 영상을 읽을 수 없습니다. MP4 파일을 선택해 주세요.",
                );
              }}
            />
          </>
        )}
        <label>
          썸네일 이미지
          <input
            ref={thumbnailInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(e) => {
              const file = e.target.files[0];
              if (file && file.size > 10 * 1024 * 1024) {
                setError("썸네일은 10MB 이하로 선택해 주세요.");
                return;
              }
              setThumbnailFile(file, { manuallySelected: true });
            }}
          />
          <small>
            권장 규격: 16:9 · JPG/JPEG · 1280×720px 이상. 영상 선택 시 첫 화면이
            자동으로 설정되며, 원하는 이미지로 변경할 수 있습니다.
          </small>
        </label>
        <label>
          강의 제목
          <input
            value={draft.title}
            onChange={(e) => field("title", e.target.value)}
            maxLength={200}
            placeholder="강의 제목을 입력해 주세요."
            required
          />
          <small>{draft.title.length}/200</small>
        </label>
        <div className="subject-field">
          <span>관련 과목</span>
          <button
            type="button"
            className="subject-picker-trigger"
            aria-label="관련 과목 선택"
            onClick={() => setSubjectPickerOpen(true)}
          >
            <span>관련된 과목을 선택해주세요.</span>
            <Search size={24} aria-hidden="true" />
          </button>
        </div>
        {draft.subjects.length > 0 && (
          <div className="subject-chips" aria-label="선택된 과목">
            {draft.subjects.map((subjectId) => {
              const subject = subjects.find((item) => item.number === subjectId);
              if (!subject) return null;
              return (
                <button
                  type="button"
                  key={subject.number}
                  onClick={() =>
                    field(
                      "subjects",
                      draft.subjects.filter((id) => id !== subject.number),
                    )
                  }
                  aria-label={`${subject.name} 선택 취소`}
                >
                  {subject.name} <span aria-hidden="true">×</span>
                </button>
              );
            })}
          </div>
        )}
        <label className="price-slider-field">
          가격
          <input
            type="range"
            min="0"
            max="1000"
            step="100"
            disabled={draft.is_preview}
            value={draft.price}
            onChange={(e) => field("price", Number(e.target.value))}
          />
          <strong>{money(draft.price)} 캐시</strong>
          <small>선생님의 강의 가격을 최대 1000캐시까지 설정할 수 있어요.</small>
        </label>
        <label className="check-label preview-check">
          <input
            type="checkbox"
            checked={draft.is_preview}
            onChange={(e) => togglePreview(e.target.checked)}
          />
          <span>
            <strong>프리뷰 영상이에요.</strong>
            <small>
              프리뷰 영상은 선생님 프로필의 메인에 표시되는 무료 강의입니다.
              <br />
              프리뷰 영상은 계정 당 하나만 등록할 수 있으며, 프리뷰 영상 등록 시 이미
              등록된 프리뷰 영상이 있다면 해당 영상은 삭제되고 신규 영상이 게시됩니다.
            </small>
          </span>
        </label>
        <div className="upload-notices" aria-label="강의 등록 안내">
          <p>
            타인의 권리를 침해하는 내용이나 불법촬영을 게재시 삭제 조치되고 관련 법에 따라
            처벌 받을 수 있습니다.
          </p>
          <p>
            영상 게시 후 최초 구매자 발생 시 기존 이용자의 권리 보호를 위해 영상 수정 및
            삭제가 제한될 수 있습니다.
          </p>
        </div>
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
            [!!draft.title.trim(), "제목 작성"],
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
      {subjectPickerOpen && (
        <SubjectPicker
          subjects={subjects}
          selectedIds={draft.subjects}
          onChange={(selectedSubjects) => field("subjects", selectedSubjects)}
          onClose={() => setSubjectPickerOpen(false)}
        />
      )}
    </>
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
          수강료
          <input
            name="price"
            type="number"
            min="0"
            max="1000"
            step="100"
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
