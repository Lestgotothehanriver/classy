import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  BookOpen,
  RefreshCw,
  LockKeyhole,
  LoaderCircle,
  ArrowRight,
  X,
} from "lucide-react";
import { api } from "./api";
import regions from "./regions.json";
export const Ctx = createContext();
export const money = (n) => Number(n || 0).toLocaleString("ko-KR");
export const date = (d) => (d ? new Date(d).toLocaleDateString("ko-KR") : "");

/** 앱의 정산 계좌 등록 화면과 공유하는 은행 선택 목록이다. */
export const BANKS = [
  "국민은행",
  "신한은행",
  "우리은행",
  "IBK기업은행",
  "하나은행",
  "NH농협은행",
  "카카오뱅크",
  "토스뱅크",
  "케이뱅크",
  "씨티은행",
  "SC제일은행",
  "우체국",
  "새마을금고",
  "신협",
  "수협은행",
];

/** 강의 재생 시간(초)을 사람이 읽기 쉬운 분·초 형식으로 변환한다. */
export const formatVideoDuration = (seconds) => {
  const totalSeconds = Math.floor(Number(seconds));
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) return "";

  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;

  if (minutes === 0) return `${remainingSeconds}초`;
  if (remainingSeconds === 0) return `${minutes}분`;
  return `${minutes}분 ${remainingSeconds}초`;
};

let schoolsRequest;

/** 앱과 같은 학교 목록을 필요할 때만 정적 자산에서 불러온다. */
function loadSchools() {
  schoolsRequest ??= fetch("/schools.json").then((response) => {
    if (!response.ok) throw new Error("학교 목록을 불러오지 못했습니다.");
    return response.json();
  });
  return schoolsRequest;
}

/** 학교 선택 뒤 해당 학교의 학과와 입학연도를 선택하도록 묶은 입력 필드다. */
export function AcademicFields({
  university = "",
  department = "",
  studentNumber = "",
}) {
  const [schools, setSchools] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [selectedSchool, setSelectedSchool] = useState(null);
  const [selectedDepartment, setSelectedDepartment] = useState(department);

  useEffect(() => {
    let alive = true;
    loadSchools()
      .then((items) => {
        if (!alive) return;
        setSchools(items);
        const current = items.find((item) => item.name === university);
        setSelectedSchool(
          current ||
            (university
              ? {
                  name: university,
                  departments: department ? [department] : [],
                }
              : null),
        );
      })
      .catch((error) => {
        if (alive) setLoadError(error.message);
      });
    return () => {
      alive = false;
    };
  }, [university, department]);

  const availableSchools =
    selectedSchool && !schools.some((school) => school.name === selectedSchool.name)
      ? [selectedSchool, ...schools]
      : schools;
  const departments = selectedSchool?.departments || [];
  const currentYear = new Date().getFullYear();
  const years = Array.from(
    { length: 100 },
    (_, index) => String(currentYear - index),
  );
  const selectedYear = String(studentNumber || "");
  const yearOptions = years.includes(selectedYear)
    ? years
    : [selectedYear, ...years].filter(Boolean);

  return (
    <>
      <label>
        학교
        <select
          name="university"
          value={selectedSchool?.name || ""}
          onChange={(event) => {
            const school = schools.find((item) => item.name === event.target.value);
            setSelectedSchool(school || null);
            setSelectedDepartment("");
          }}
          required
        >
          <option value="" disabled>
            학교를 선택해주세요
          </option>
          {availableSchools.map((school) => (
            <option key={school.name} value={school.name}>
              {school.name}
            </option>
          ))}
        </select>
      </label>
      {loadError && <p className="error">{loadError}</p>}
      <label>
        학과/전공
        <select
          name="department"
          value={selectedDepartment}
          onChange={(event) => setSelectedDepartment(event.target.value)}
          disabled={!selectedSchool || departments.length === 0}
          required
        >
          <option value="" disabled>
            학과를 선택해주세요
          </option>
          {departments.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <label>
        입학연도 (학번)
        <select name="student_number" defaultValue={selectedYear} required>
          <option value="" disabled>
            입학연도를 선택해주세요
          </option>
          {yearOptions.map((year) => (
            <option key={year} value={year}>
              {year}년
            </option>
          ))}
        </select>
      </label>
    </>
  );
}

/** 시/도와 시·군·구 목록에서만 지역을 선택하게 하는 공통 입력 필드다. */
export function RegionFields({ label = "활동 지역", name = "region", value = "", required = false }) {
  const initial = regions.find(([, region]) => region === value)?.[1] || value;
  const [province, ...districtParts] = String(initial || "").split(" ");
  const initialDistrict = districtParts.join(" ");
  const [selectedProvince, setSelectedProvince] = useState(province || "");
  const [selectedDistrict, setSelectedDistrict] = useState(initialDistrict);
  const provinces = [...new Set(regions.map(([, region]) => region.split(" ")[0]))];
  const districts = regions
    .map(([, region]) => region.split(" "))
    .filter(([currentProvince]) => currentProvince === selectedProvince)
    .map((parts) => parts.slice(1).join(" "));
  const selectedRegion = [selectedProvince, selectedDistrict]
    .filter(Boolean)
    .join(" ");

  return (
    <label>
      {label}
      <div className="selection-grid">
        <select
          aria-label={`${label} 시/도`}
          value={selectedProvince}
          onChange={(event) => {
            setSelectedProvince(event.target.value);
            setSelectedDistrict("");
          }}
          required={required}
        >
          <option value="">시/도 선택</option>
          {provinces.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <select
          aria-label={`${label} 시·군·구`}
          value={selectedDistrict}
          onChange={(event) => setSelectedDistrict(event.target.value)}
          disabled={!selectedProvince}
          required={required}
        >
          <option value="">시·군·구 선택</option>
          {districts.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </div>
      <input name={name} type="hidden" value={selectedRegion} />
    </label>
  );
}

export function useLoad(path, deps = [], { keepDataOnReload = false } = {}) {
  const [state, set] = useState({ loading: true, data: null, error: "" });
  const [version, bump] = useState(0);
  const reloading = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    const keepData = keepDataOnReload && reloading.current;
    reloading.current = false;
    set((current) =>
      keepData && current.data
        ? { ...current, loading: false, error: "" }
        : { loading: !!path, data: null, error: "" },
    );
    if (path)
      api(path, { signal: controller.signal })
        .then((data) => {
          if (!controller.signal.aborted)
            set({ data, loading: false, error: "" });
        })
        .catch((e) => {
          if (!controller.signal.aborted)
            set((current) =>
              keepData && current.data
                ? { ...current, loading: false, error: "" }
                : { data: null, loading: false, error: e.message },
            );
        });
    return () => controller.abort();
  }, [path, version, keepDataOnReload, ...deps]);
  return {
    ...state,
    reload: () => {
      reloading.current = true;
      bump((v) => v + 1);
    },
  };
}
export function Btn({ children, className = "", ...props }) {
  return (
    <button className={"btn " + className} {...props}>
      {children}
    </button>
  );
}
export function Empty({
  title = "아직 등록된 내용이 없어요",
  text = "새로운 소식이 생기면 이곳에서 확인할 수 있어요.",
  icon: Icon = BookOpen,
  children,
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={26} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {children}
    </div>
  );
}
export function State({ resource, children }) {
  if (resource.loading)
    return (
      <div className="loading" role="status">
        <LoaderCircle className="spin" />
        불러오는 중이에요
      </div>
    );
  if (resource.error)
    return (
      <Empty icon={RefreshCw} title="불러오지 못했어요" text={resource.error}>
        <Btn onClick={resource.reload}>다시 시도</Btn>
      </Empty>
    );
  return children;
}
export function Gate({ children }) {
  const { user, login } = useContext(Ctx);
  return user ? (
    children
  ) : (
    <Empty
      icon={LockKeyhole}
      title="나의 배움을 이어가세요"
      text="Classy 앱에서 사용하던 계정으로 로그인하면 선생님, 강의와 대화를 그대로 만날 수 있어요."
    >
      <Btn className="primary" onClick={login}>
        기존 계정으로 로그인 <ArrowRight size={16} />
      </Btn>
    </Empty>
  );
}
export function Modal({ title, onClose, children, wide = false }) {
  const { toast } = useContext(Ctx);
  const ref = useRef();
  useEffect(() => {
    ref.current.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={wide ? "wide" : ""}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <button className="icon-button" aria-label="닫기" onClick={onClose}>
          <X />
        </button>
      </div>
      {toast && (
        <p className="dialog-notice" role="status">
          {toast}
        </p>
      )}
      {children}
    </dialog>
  );
}
export function Subjects({ values = [] }) {
  const { subjects } = useContext(Ctx);
  return (
    <div className="tags">
      {(Array.isArray(values) ? values : []).slice(0, 4).map((s, i) => (
        <span key={i}>
          {typeof s === "object"
            ? s.label || s.name
            : typeof s === "string" && !/^\d+$/.test(s)
              ? s
              : subjects.find((x) => x.number === Number(s))?.name ||
                "과목 " + s}
        </span>
      ))}
    </div>
  );
}
