export const appStoreUrl =
  "https://apps.apple.com/kr/app/%ED%81%B4%EB%9E%98%EC%94%A8/id6806294828";
export const playStoreUrl =
  "https://play.google.com/store/apps/details?id=com.classystudy.app";
export const appDownloadQrUrl = "https://classystudy.com/download";

export function getMobileStoreUrl() {
  const userAgent = navigator.userAgent;
  const isAndroid = /Android/i.test(userAgent);
  const isAppleMobile =
    /iPad|iPhone|iPod/i.test(userAgent) ||
    (userAgent.includes("Macintosh") && navigator.maxTouchPoints > 1);

  if (isAndroid) return playStoreUrl;
  if (isAppleMobile) return appStoreUrl;
  return null;
}
