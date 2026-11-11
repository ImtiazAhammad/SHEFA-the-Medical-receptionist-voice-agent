"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { DEFAULT_LANGUAGE, LANGUAGE_STORAGE_KEY, SUPPORTED_LANGUAGES } from "@/constants/app";
import { bn } from "@/i18n/bn";
import { en } from "@/i18n/en";
import { createLogger } from "@/lib/logger";
import type { Dictionary, Language } from "@/types/i18n";

const logger = createLogger("i18n");

const DICTIONARIES: Record<Language, Dictionary> = { bn, en };

interface LanguageContextValue {
  language: Language;
  dictionary: Dictionary;
  setLanguage: (language: Language) => void;
  toggleLanguage: () => void;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);
const listeners = new Set<() => void>();
let memoryLanguage: Language = DEFAULT_LANGUAGE;

function isLanguage(value: string | null): value is Language {
  return value !== null && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

function readLanguage(): Language {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return isLanguage(stored) ? stored : memoryLanguage;
  } catch (error) {
    logger.debug("Language preference unavailable", { error });
    return memoryLanguage;
  }
}

function writeLanguage(language: Language): void {
  memoryLanguage = language;
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch (error) {
    logger.debug("Language preference not saved", { error });
  }
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function serverLanguage(): Language {
  return DEFAULT_LANGUAGE;
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const language = useSyncExternalStore(subscribe, readLanguage, serverLanguage);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const setLanguage = useCallback((next: Language) => writeLanguage(next), []);
  const toggleLanguage = useCallback(() => writeLanguage(language === "bn" ? "en" : "bn"), [language]);

  const value = useMemo<LanguageContextValue>(
    () => ({ language, dictionary: DICTIONARIES[language], setLanguage, toggleLanguage }),
    [language, setLanguage, toggleLanguage],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return context;
}
