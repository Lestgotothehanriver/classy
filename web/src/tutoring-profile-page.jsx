import React, { useContext, useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { api } from "./api";
import regions from "./regions.json";
import { SubjectPicker } from "./studio";
import { Btn, Ctx, FieldLabel, MobileBackAction, useLoad } from "./shared";

function toIds(values, findByLabel) {
  return (Array.isArray(values) ? values : [])
    .map((value) => {
      if (typeof value === "object") return Number(value.number || value.id);
      return Number(findByLabel(value) || value);
    })
    .filter(Number.isFinite);
}

function selectedMethod(method) {
  return String(method || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

/** 선생님의 과외 프로필을 생성하거나 수정하는 독립 페이지입니다. */
export function TutoringProfilePage() {
  const { go, notify, subjects } = useContext(Ctx);
  const resource = useLoad("/tutoring/instructor-info/mine/");
  const profile = resource.data || null;
  const [subjectIds, setSubjectIds] = useState([]);
  const [regionIds, setRegionIds] = useState([]);
  const [schedule, setSchedule] = useState("");
  const [cost, setCost] = useState("");
  const [methods, setMethods] = useState([]);
  const [extra, setExtra] = useState("");
  const [subjectPickerOpen, setSubjectPickerOpen] = useState(false);
  const [regionProvince, setRegionProvince] = useState("");
  const [regionDistrict, setRegionDistrict] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!profile) return;
    setSubjectIds(toIds(
      profile.subjects,
      (value) => subjects.find((item) => item.name === value)?.number,
    ));
    setRegionIds(toIds(
      profile.regions,
      (value) => regions.find(([, name]) => name === value)?.[0],
    ));
    setSchedule(profile.schedule || "");
    setCost(profile.cost || "");
    setMethods(selectedMethod(profile.method));
    setExtra(profile.etc || "");
  }, [profile?.id, subjects]);

  const isEditing = Boolean(profile?.id);
  const isValid =
    subjectIds.length > 0 &&
    schedule.trim() &&
    cost.trim() &&
    methods.length > 0 &&
    regionIds.length > 0;

  function toggleMethod(method) {
    setMethods((current) =>
      current.includes(method)
        ? current.filter((value) => value !== method)
        : [...current, method],
    );
  }

  const provinces = [...new Set(regions.map(([, name]) => name.split(" ")[0]))];
  const districts = regions.filter(([, name]) => name.split(" ")[0] === regionProvince);

  function addRegion() {
    const id = Number(regionDistrict);
    if (Number.isFinite(id))
      setRegionIds((current) => (current.includes(id) ? current : [...current, id]));
    setRegionDistrict("");
  }

  async function submit(event) {
    event.preventDefault();
    if (!isValid || busy) return;
    setBusy(true);
    setError("");
    const body = {
      subjects: subjectIds,
      regions: regionIds,
      schedule: schedule.trim(),
      cost: cost.trim(),
      method: methods.join(","),
      location: regionIds
        .map((id) => regions.find(([regionId]) => Number(regionId) === id)?.[1])
        .filter(Boolean)
        .join(","),
      etc: extra.trim(),
    };
    try {
      await api(
        isEditing
          ? `/tutoring/instructor-info/${profile.id}/`
          : "/tutoring/instructor-info/",
        {
          method: isEditing ? "PATCH" : "POST",
          body: isEditing ? body : { ...body, is_tutoring: true },
        },
      );
      notify(isEditing ? "프로필이 수정되었습니다." : "프로필이 등록되었습니다.");
      go("tutoring-manage");
    } catch (submitError) {
      setError(submitError.message || "과외 프로필을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  if (resource.loading)
    return <div className="loading">프로필 정보를 불러오는 중이에요.</div>;
  if (resource.error)
    return (
      <main className="form-page registration-page tutoring-profile-page">
        <div className="form-page-content registration-page-content">
          <div className="form-page-body registration-page-body">
            <p className="error" role="alert">{resource.error}</p>
            <Btn onClick={resource.reload}>다시 시도</Btn>
          </div>
        </div>
      </main>
    );

  return (
    <main className="form-page registration-page tutoring-profile-page">
      <div className="form-page-content registration-page-content">
        <div className="form-page-body registration-page-body">
          <header className="registration-page-head">
            <MobileBackAction type="button" onClick={() => go("tutoring-manage")}>
              과외 관리로
            </MobileBackAction>
            <h1>{isEditing ? "프로필 수정" : "프로필 생성"}</h1>
          </header>

          <form className="form registration-form" onSubmit={submit}>
            <fieldset className="form-fields" disabled={busy}>
              <section className="tutoring-profile-intro">
                <h2>과외를 시작하시겠어요?</h2>
                <p>프로필을 작성해주시면 과외 제안을 보낼 수 있어요.</p>
              </section>

              <div className="chip-form-field">
              <div className="subject-field">
                <FieldLabel required>수업 과목</FieldLabel>
                <button
                  type="button"
                  className="subject-picker-trigger"
                  onClick={() => setSubjectPickerOpen(true)}
                >
                  <span>{subjectIds.length ? `${subjectIds.length}개 과목 선택됨` : "관련된 과목을 선택해주세요."}</span>
                  <Search size={24} aria-hidden="true" />
                </button>
              </div>
              {subjectIds.length > 0 && (
                <div className="subject-chips" aria-label="선택된 수업 과목">
                  {subjectIds.map((id) => {
                    const subject = subjects.find((item) => Number(item.number) === id);
                    return subject ? (
                      <button type="button" key={id} onClick={() => setSubjectIds((current) => current.filter((value) => value !== id))}>
                        {subject.name} <X size={14} aria-hidden="true" />
                      </button>
                    ) : null;
                  })}
                </div>
              )}
              </div>

              <label>
                <FieldLabel required>수업 일정</FieldLabel>
                <textarea value={schedule} onChange={(event) => setSchedule(event.target.value)} rows={2} placeholder={"희망 수업 일정을 작성해주세요.\n(예: 화, 목 오후 4시 이후 가능)"} required />
              </label>
              <label>
                <FieldLabel required>수업료</FieldLabel>
                <textarea value={cost} onChange={(event) => setCost(event.target.value)} rows={3} placeholder={"희망 수업료를 작성해주세요.\n(예: 평일 시간당 2만원)"} required />
              </label>

              <div className="tutoring-method-field">
                <FieldLabel required>수업 방식</FieldLabel>
                <small>복수 선택 가능</small>
                <div className="tutoring-method-options">
                  {["대면", "비대면"].map((method) => (
                    <button type="button" key={method} className={methods.includes(method) ? "selected" : ""} aria-pressed={methods.includes(method)} onClick={() => toggleMethod(method)}>
                      {method === "대면" ? "대면 수업" : "화상 수업"}
                    </button>
                  ))}
                </div>
              </div>

              <div className="tutoring-region-field chip-form-field">
                <FieldLabel required>수업 가능 지역</FieldLabel>
                <div className="tutoring-region-add">
                  <select value={regionProvince} onChange={(event) => { setRegionProvince(event.target.value); setRegionDistrict(""); }} aria-label="수업 가능 지역 시도 선택">
                    <option value="">시/도</option>
                    {provinces.map((province) => <option key={province} value={province}>{province}</option>)}
                  </select>
                  <select value={regionDistrict} onChange={(event) => setRegionDistrict(event.target.value)} disabled={!regionProvince} aria-label="수업 가능 지역 시구군 선택">
                    <option value="">시/구/군</option>
                    {districts.map(([id, name]) => <option key={id} value={id}>{name.split(" ").slice(1).join(" ")}</option>)}
                  </select>
                  <Btn type="button" onClick={addRegion} disabled={!regionDistrict}>추가</Btn>
                </div>
                {regionIds.length > 0 && (
                  <div className="subject-chips" aria-label="선택된 수업 가능 지역">
                    {regionIds.map((id) => {
                      const region = regions.find(([regionId]) => Number(regionId) === id);
                      return region ? <button type="button" key={id} onClick={() => setRegionIds((current) => current.filter((value) => value !== id))}>{region[1]} <X size={14} aria-hidden="true" /></button> : null;
                    })}
                  </div>
                )}
              </div>

              <label>
                <FieldLabel>상세</FieldLabel>
                <textarea value={extra} onChange={(event) => setExtra(event.target.value)} rows={5} placeholder="학생/학부모님께 추가로 하실 말씀이 있으시다면 자유롭게 적어주세요." />
              </label>
              {error && <p className="error" role="alert">{error}</p>}
              <Btn className="primary full" disabled={!isValid || busy}>
                {busy ? "저장 중…" : isEditing ? "프로필 수정 완료" : "프로필 등록"}
              </Btn>
            </fieldset>
          </form>
        </div>
      </div>
      {subjectPickerOpen && <SubjectPicker subjects={subjects} selectedIds={subjectIds} onChange={setSubjectIds} onClose={() => setSubjectPickerOpen(false)} />}
    </main>
  );
}
