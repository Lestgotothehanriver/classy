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
export const Ctx = createContext();
export const money = (n) => Number(n || 0).toLocaleString("ko-KR");
export const date = (d) => (d ? new Date(d).toLocaleDateString("ko-KR") : "");
export function useLoad(path, deps = []) {
  const [state, set] = useState({ loading: true, data: null, error: "" });
  const [version, bump] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    set({ loading: !!path, data: null, error: "" });
    if (path)
      api(path, { signal: controller.signal })
        .then((data) => {
          if (!controller.signal.aborted)
            set({ data, loading: false, error: "" });
        })
        .catch((e) => {
          if (!controller.signal.aborted)
            set({ data: null, loading: false, error: e.message });
        });
    return () => controller.abort();
  }, [path, version, ...deps]);
  return { ...state, reload: () => bump((v) => v + 1) };
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
