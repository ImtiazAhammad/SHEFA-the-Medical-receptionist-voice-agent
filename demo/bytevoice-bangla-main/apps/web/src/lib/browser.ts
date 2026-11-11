import type { BrowserName } from "@/types/call";

export function detectBrowser(userAgent: string): BrowserName {
  if (/Edg\//.test(userAgent)) {
    return "edge";
  }
  if (/Firefox\//.test(userAgent)) {
    return "firefox";
  }
  if (/Chrome\//.test(userAgent) || /CriOS\//.test(userAgent)) {
    return "chrome";
  }
  if (/Safari\//.test(userAgent)) {
    return "safari";
  }
  return "other";
}
