/**
 * Browser-path routing for the web app.
 *
 * Public UUIDs stay opaque in the address bar. The application still accepts
 * the previous symbolic route names at its navigation boundary so individual
 * screens do not need to know about URL formatting.
 */

const staticPaths = {
  home: "/home",
  lectures: "/lectures",
  teachers: "/instructors",
  posts: "/tutoring-posts",
  learning: "/my/lectures",
  saved: "/my/saved/lectures",
  expired: "/my/expired-lectures",
  "saved-teachers": "/my/saved/instructors",
  chat: "/messages",
  profile: "/my",
  "profile-edit": "/my/profile",
  notifications: "/notifications",
  upload: "/studio/upload",
  studio: "/studio",
  cash: "/my/cash",
  settlement: "/studio/settlement",
  verification: "/studio/verification",
  account: "/my/account",
  "tutoring-manage": "/tutoring/manage",
  "tutoring-profile": "/tutoring/profile",
  support: "/support",
  notices: "/notices",
};

export const publicIdPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isPublicId(value) {
  return publicIdPattern.test(String(value || ""));
}

function decode(segment) {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

/** Parse the current browser path into the existing screen identifiers. */
export function parseRoute(location = window.location) {
  const parts = location.pathname
    .split("/")
    .filter(Boolean)
    .map(decode);
  const query = new URLSearchParams(location.search);
  const [head, second, third, fourth] = parts;

  if (parts.length === 0) return { page: "landing", params: {}, query };
  if (head === "home") return { page: "home", params: {}, query };
  if (head === "lectures") {
    return second
      ? { page: "lecture", params: { publicId: second }, query }
      : { page: "lectures", params: {}, query };
  }
  if (head === "instructors") {
    return second
      ? { page: "teacher-profile", params: { publicId: second }, query }
      : { page: "teachers", params: {}, query };
  }
  if (head === "tutoring-posts") {
    if (second === "new") return { page: "tutoring-post", params: { postId: "new" }, query };
    if (second && third === "edit") {
      return { page: "tutoring-post", params: { postId: second }, query };
    }
    return second
      ? { page: "tutoring-post-detail", params: { publicId: second }, query }
      : { page: "posts", params: {}, query };
  }
  if (head === "notices") {
    return second
      ? { page: "notices", params: { publicId: second }, query }
      : { page: "notices", params: {}, query };
  }
  if (head === "messages") {
    if (!second) return { page: "chat", params: {}, query };
    if (third === "registration") {
      return {
        page: "tutoring-registration",
        params: { roomPublicId: second, step: fourth === "proof" ? "proof" : "basic" },
        query,
      };
    }
    return { page: "chat", params: { roomPublicId: second }, query };
  }
  if (head === "my") {
    if (second === "saved" && third === "lectures") {
      return { page: "saved", params: {}, query };
    }
    if (second === "expired" && third === "lectures") {
      return { page: "expired", params: {}, query };
    }
    if (second === "saved" && third === "instructors") {
      return { page: "saved-teachers", params: {}, query };
    }
    const pages = {
      undefined: "profile",
      profile: "profile-edit",
      lectures: "learning",
      cash: "cash",
      account: "account",
    };
    return { page: pages[second] || "not-found", params: {}, query };
  }
  if (head === "studio") {
    const pages = {
      undefined: "studio",
      upload: "upload",
      settlement: "settlement",
      verification: "verification",
    };
    return { page: pages[second] || "not-found", params: {}, query };
  }
  if (head === "tutoring") {
    const pages = { manage: "tutoring-manage", profile: "tutoring-profile" };
    return { page: pages[second] || "not-found", params: {}, query };
  }
  if (head === "notifications") return { page: "notifications", params: {}, query };
  if (head === "support") return { page: "support", params: {}, query };
  return { page: "not-found", params: {}, query };
}

/** Build a canonical browser path from the existing symbolic route input. */
export function pathFor(target) {
  const [page, first, second] = String(target || "home").split("/");
  if (staticPaths[page] && first == null) return staticPaths[page];
  if (page === "lecture" && first) return `/lectures/${encodeURIComponent(first)}`;
  if (page === "teacher-profile" && first) return `/instructors/${encodeURIComponent(first)}`;
  if (page === "tutoring-post-detail" && first) return `/tutoring-posts/${encodeURIComponent(first)}`;
  if (page === "tutoring-post") {
    if (first === "new") return "/tutoring-posts/new";
    return `/tutoring-posts/${encodeURIComponent(first)}/edit`;
  }
  if (page === "notices" && first) return `/notices/${encodeURIComponent(first)}`;
  if (page === "chat" && first) return `/messages/${encodeURIComponent(first)}`;
  if (page === "tutoring-registration" && first) {
    const suffix = second === "proof" ? "/proof" : "";
    return `/messages/${encodeURIComponent(first)}/registration${suffix}`;
  }
  return staticPaths[page] || "/home";
}

/** Convert the prior hash route into a symbolic target without writing history. */
export function legacyHashTarget(hash = window.location.hash) {
  const value = hash.replace(/^#/, "");
  return value || "home";
}

export function pushPath(path, { replace = false } = {}) {
  const method = replace ? "replaceState" : "pushState";
  window.history[method](null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
