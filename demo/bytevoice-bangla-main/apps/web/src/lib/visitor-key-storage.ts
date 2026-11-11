import { VISITOR_KEY_STORAGE_KEY } from "@/constants/call";
import { createLogger } from "@/lib/logger";

const logger = createLogger("visitor-key-storage");

export function readTestedVisitorKey(): string | null {
  try {
    return window.sessionStorage.getItem(VISITOR_KEY_STORAGE_KEY);
  } catch (error) {
    logger.debug("Session storage unavailable", { error });
    return null;
  }
}

export function saveTestedVisitorKey(apiKey: string): void {
  try {
    window.sessionStorage.setItem(VISITOR_KEY_STORAGE_KEY, apiKey);
  } catch (error) {
    logger.debug("Session storage unavailable", { error });
  }
}

export function forgetVisitorKey(): void {
  try {
    window.sessionStorage.removeItem(VISITOR_KEY_STORAGE_KEY);
  } catch (error) {
    logger.debug("Session storage unavailable", { error });
  }
}
