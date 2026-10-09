export const list = (data) =>
  Array.isArray(data) ? data : data?.results || [];
export function apiPath(path) {
  const url = new URL(path, "https://api.classystudy.com");
  if (
    url.origin !== "https://api.classystudy.com" ||
    !url.pathname.startsWith("/") ||
    url.pathname.startsWith("//")
  )
    throw new Error("잘못된 API 주소입니다.");
  return "/api" + url.pathname + url.search;
}
export function errorText(data) {
  if (typeof data === "string") return data;
  if (!data) return "요청을 처리하지 못했습니다.";
  if (data.error === "Invalid credentials")
    return "이메일 또는 비밀번호가 올바르지 않습니다.";
  return Object.values(data)
    .map((v) => (typeof v === "object" ? errorText(v) : String(v)))
    .join(" ");
}
export async function api(path, options = {}) {
  const token =
    path === "/accounts/login/" ? null : sessionStorage.getItem("classy_token");
  const { body, ...rest } = options;
  const headers = {
    ...(token ? { Authorization: `Token ${token}` } : {}),
    ...(body && !(body instanceof FormData)
      ? { "Content-Type": "application/json" }
      : {}),
    ...options.headers,
  };
  const res = await fetch(apiPath(path), {
    ...rest,
    headers,
    body:
      body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    signal: options.signal || AbortSignal.timeout(30000),
  });
  const data =
    res.status === 204
      ? null
      : await res
          .json()
          .catch(() => ({ detail: "서버 응답을 확인할 수 없습니다." }));
  if (!res.ok) {
    if (res.status === 401 && token)
      window.dispatchEvent(new Event("classy:expired"));
    throw new Error(errorText(data));
  }
  return data;
}

/** Downloads a protected API attachment with the current account token. */
export async function downloadProtectedFile(path, filename) {
  const token = sessionStorage.getItem("classy_token");
  const res = await fetch(apiPath(path), {
    headers: token ? { Authorization: `Token ${token}` } : {},
    signal: AbortSignal.timeout(30000),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    if (res.status === 401 && token)
      window.dispatchEvent(new Event("classy:expired"));
    throw new Error(errorText(data));
  }
  const objectUrl = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}
