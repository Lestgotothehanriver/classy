import { useState } from "react";
import { Search } from "lucide-react";
import regions from "./regions.json";
import { FieldLabel, RegionFields } from "./shared";
import { SubjectPicker } from "./studio";

const STUDENT_GRADES = [
  "유치원생", "초1", "초2", "초3", "초4", "초5", "초6", "중1", "중2", "중3",
  "고1", "고2", "고3", "N수생", "사회인",
];
const FIELD_REQUIRED_GRADES = new Set(["고1", "고2", "고3", "N수생"]);
const SPECIALIZED_FIELD_GRADES = new Set(["고3", "N수생", "재수생"]);
const TUITION_OPTIONS = [
  "월 10만원 이하", "월 20만원 이하", "월 30만원 이하", "월 40만원 이하",
  "월 50만원 이하", "월 60만원 이하", "월 70만원 이하", "월 80만원 이하",
  "월 90만원 이하", "월 100만원 이하", "협의 후 결정",
];

function PostFieldLabel({ children, required = false, limit, count = 0 }) {
  return (
    <span className="post-form-label">
      <FieldLabel required={required}>{children}</FieldLabel>
      {limit && <small>{count}/{limit}</small>}
    </span>
  );
}

function formatLocalDate(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function calculateAge(birthDate) {
  if (!birthDate) return null;
  const today = new Date();
  const birthday = new Date(`${birthDate}T00:00:00`);
  let age = today.getFullYear() - birthday.getFullYear();
  if (
    today.getMonth() < birthday.getMonth() ||
    (today.getMonth() === birthday.getMonth() && today.getDate() < birthday.getDate())
  ) age -= 1;
  return age >= 0 ? age : null;
}

function dateForAge(age) {
  if (!age) return "";
  const today = new Date();
  today.setFullYear(today.getFullYear() - Number(age));
  return formatLocalDate(today);
}

function CounterTextField({
  name,
  title,
  defaultValue = "",
  maxLength,
  placeholder,
  required = false,
  multiline = false,
}) {
  const [value, setValue] = useState(defaultValue);
  const Control = multiline ? "textarea" : "input";
  return (
    <label>
      <PostFieldLabel required={required} limit={maxLength} count={value.length}>{title}</PostFieldLabel>
      <Control
        name={name}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        required={required}
        maxLength={maxLength}
        placeholder={placeholder}
        {...(multiline ? { rows: 3 } : {})}
      />
    </label>
  );
}

function StudentSubjectField({ subjects, values }) {
  const [selectedIds, setSelectedIds] = useState(() =>
    toSubjectNumbers(values, subjects).map(Number),
  );
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  return (
    <div className="chip-form-field">
      <div className="subject-field">
        <PostFieldLabel required>수업 과목</PostFieldLabel>
        <button
          type="button"
          className="subject-picker-trigger"
          aria-label="수업 과목 선택"
          onClick={() => setIsPickerOpen(true)}
        >
          <span>
            {selectedIds.length
              ? `${selectedIds.length}개 과목 선택됨`
              : "관련된 과목을 선택해주세요."}
          </span>
          <Search size={24} aria-hidden="true" />
        </button>
        {selectedIds.map((id) => <input key={id} type="hidden" name="subjects" value={id} />)}
      </div>
      {selectedIds.length > 0 && (
        <div className="subject-chips" aria-label="선택된 수업 과목">
          {selectedIds.map((id) => {
            const subject = subjects.find((item) => item.number === id);
            if (!subject) return null;
            return (
              <button
                type="button"
                key={id}
                onClick={() => setSelectedIds((ids) => ids.filter((item) => item !== id))}
                aria-label={`${subject.name} 선택 취소`}
              >
                {subject.name} <span aria-hidden="true">×</span>
              </button>
            );
          })}
        </div>
      )}
      {isPickerOpen && (
        <SubjectPicker
          subjects={subjects}
          selectedIds={selectedIds}
          onChange={setSelectedIds}
          onClose={() => setIsPickerOpen(false)}
        />
      )}
    </div>
  );
}

/** 목록 응답의 과목 데이터를 선택 입력값으로 정규화한다. */
export function toSubjectNumbers(values, subjects) {
  return values.map((value) =>
    String(value.number || subjects.find((subject) => subject.name === value)?.number || value),
  );
}

function toRegionName(values) {
  const region = values?.[0];
  if (!region) return "";
  return region.label || region.name || regions.find(([id]) => String(id) === String(region.number || region.id || region))?.[1] || String(region);
}

/** 앱의 학생 모집 공고 작성 화면과 같은 입력 구성이다. */
export function StudentPostFormFields({ editing, subjects }) {
  const [grade, setGrade] = useState(editing.grade || "");
  const [field, setField] = useState(editing.field || "");
  const [selectedMethods, setSelectedMethods] = useState(() =>
    String(editing.method || "").split(",").filter(Boolean).map((method) => method.trim()),
  );
  const [birthDate, setBirthDate] = useState(() => dateForAge(editing.age));
  const age = calculateAge(birthDate);
  const today = formatLocalDate(new Date());
  const minBirthDate = formatLocalDate(new Date(new Date().setFullYear(new Date().getFullYear() - 100)));
  const tuition = editing.cost ? `월 ${Number(editing.cost) / 10000}만원 이하` : "협의 후 결정";
  const tuitionOptions = TUITION_OPTIONS.includes(tuition) ? TUITION_OPTIONS : [tuition, ...TUITION_OPTIONS];
  const fieldOptions = [
    "문과",
    "이과",
    "예체능",
    ...(SPECIALIZED_FIELD_GRADES.has(grade) ? ["특성화"] : []),
  ];

  return (
    <>
      <CounterTextField
        name="title"
        title="제목"
        defaultValue={editing.title || ""}
        maxLength={30}
        placeholder="제목을 입력해주세요."
        required
      />
      <label>
        <PostFieldLabel required>학생 성별</PostFieldLabel>
        <select name="sex" defaultValue={editing.sex || ""} required>
          <option value="" disabled>성별 선택</option>
          <option value="남성">남성</option>
          <option value="여성">여성</option>
        </select>
      </label>
      <div className="form-columns">
        <label>
          <PostFieldLabel required>학생 나이</PostFieldLabel>
          <span className="post-age-date-field">
            <input
              type="date"
              name="birth_date"
              value={birthDate}
              min={minBirthDate}
              max={today}
              onChange={(event) => setBirthDate(event.target.value)}
              required
            />
            <span aria-hidden="true">{age !== null ? `만 ${age}세` : "나이"}</span>
          </span>
        </label>
        <label><PostFieldLabel required>학년</PostFieldLabel><select name="grade" value={grade} onChange={(event) => { const nextGrade = event.target.value; setGrade(nextGrade); if (!FIELD_REQUIRED_GRADES.has(nextGrade) || (!SPECIALIZED_FIELD_GRADES.has(nextGrade) && field === "특성화")) setField(""); }} required><option value="">학년 선택</option>{STUDENT_GRADES.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      </div>
      {FIELD_REQUIRED_GRADES.has(grade) && (
        <fieldset className="post-form-options">
          <legend><PostFieldLabel required>계열</PostFieldLabel></legend>
          <div className="post-field-toggle-list">
            {fieldOptions.map((option) => (
              <button
                type="button"
                key={option}
                className={field === option ? "selected" : ""}
                aria-pressed={field === option}
                onClick={() => setField(option)}
              >
                {option}
              </button>
            ))}
          </div>
          <input type="hidden" name="field" value={field} />
        </fieldset>
      )}
      <StudentSubjectField subjects={subjects} values={editing.subjects || []} />
      <fieldset className="post-form-options">
        <legend><PostFieldLabel required>수업 방식</PostFieldLabel><p>복수 선택 가능</p></legend>
        <div className="post-method-toggle-list">
          {[["대면", "대면 수업"], ["비대면", "화상 수업"]].map(([value, label]) => {
            const selected = selectedMethods.includes(value);
            return (
              <button
                type="button"
                key={value}
                className={selected ? "selected" : ""}
                aria-pressed={selected}
                onClick={() => setSelectedMethods((methods) => selected ? methods.filter((method) => method !== value) : [...methods, value])}
              >
                {label}
              </button>
            );
          })}
        </div>
        {selectedMethods.map((method) => <input type="hidden" name="methods" value={method} key={method} />)}
      </fieldset>
      <RegionFields label="지역" name="region" value={toRegionName(editing.regions)} required showRequiredLabel />
      <label><PostFieldLabel required>수업료</PostFieldLabel><select name="cost" defaultValue={tuition} required>{tuitionOptions.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
      <CounterTextField
        name="schedule"
        title="수업 일정"
        defaultValue={editing.schedule || ""}
        maxLength={30}
        placeholder="희망 수업 일정을 작성해주세요. (예: 주 3회)"
        required
        multiline
      />
      <CounterTextField
        name="situation"
        title="학생 상황 (선택)"
        defaultValue={editing.situation || ""}
        maxLength={300}
        placeholder={"성적이나 진도 등\n수업에 필요한 정보를 작성해주세요.\n(예: 수학 성적은 평균 3등급이고, 현재 미적분 개념 복습 중이에요. 수능 1등급을 목표로 하고있습니다. 수학과 선생님이었으면 좋겠어요.)"}
        multiline
      />
      <CounterTextField
        name="etc"
        title="기타 요청 (선택)"
        defaultValue={editing.etc || ""}
        maxLength={300}
        placeholder={"기타 요청 사항 및 선생님에게 전하고싶은 내용이 있다면 작성해주세요.\n(예: 강아지를 키우고 있어요. 강아지 알레르기가 있거나, 강아지를 무서워하시는 분은 참고해주세요.)"}
        multiline
      />
    </>
  );
}

/** 학생 공고 폼 데이터를 API의 저장 형식으로 변환한다. */
export function toStudentPostPayload(form) {
  const payload = Object.fromEntries(form);
  const selectedMethods = form.getAll("methods");
  if (!selectedMethods.length) throw new Error("수업 방식을 하나 이상 선택해주세요.");
  const selectedSubjects = form.getAll("subjects").map(Number);
  if (!selectedSubjects.length) throw new Error("수업 과목을 하나 이상 선택해주세요.");
  const selectedRegion = regions.find(([, label]) => label === form.get("region"));
  if (!selectedRegion) throw new Error("지역을 선택해주세요.");
  const age = calculateAge(payload.birth_date);
  if (age === null) throw new Error("학생 생년월일을 확인해주세요.");
  if (FIELD_REQUIRED_GRADES.has(payload.grade) && !payload.field) {
    throw new Error("계열을 선택해주세요.");
  }
  if (
    payload.field === "특성화" &&
    !SPECIALIZED_FIELD_GRADES.has(payload.grade)
  ) {
    throw new Error("선택한 학년에서는 특성화 계열을 선택할 수 없어요.");
  }
  payload.subjects = selectedSubjects;
  payload.age = age;
  payload.field = FIELD_REQUIRED_GRADES.has(payload.grade) ? payload.field : "";
  payload.method = selectedMethods.join(",");
  payload.regions = [Number(selectedRegion[0])];
  payload.cost = payload.cost === "협의 후 결정" ? null : Number(payload.cost.replace(/[^0-9]/g, "")) * 10000;
  delete payload.methods;
  delete payload.region;
  delete payload.birth_date;
  return payload;
}
