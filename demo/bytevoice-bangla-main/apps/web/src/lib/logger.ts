type LogLevel = "debug" | "info" | "warn" | "error";
type LogContext = Record<string, unknown>;

const LEVEL_PRIORITY: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 };

function minimumLevel(): LogLevel {
  return process.env.NODE_ENV === "production" ? "info" : "debug";
}

function serializeError(error: unknown): unknown {
  if (error instanceof Error) {
    return { name: error.name, message: error.message };
  }
  return error;
}

function write(level: LogLevel, scope: string, message: string, context?: LogContext): void {
  if (LEVEL_PRIORITY[level] < LEVEL_PRIORITY[minimumLevel()]) {
    return;
  }
  const entry = {
    level,
    scope,
    message,
    time: new Date().toISOString(),
    ...(context ? Object.fromEntries(Object.entries(context).map(([key, value]) => [key, serializeError(value)])) : {}),
  };
  const sink = level === "error" ? console.error : level === "warn" ? console.warn : level === "info" ? console.info : console.debug;
  sink(JSON.stringify(entry));
}

export interface Logger {
  debug: (message: string, context?: LogContext) => void;
  info: (message: string, context?: LogContext) => void;
  warn: (message: string, context?: LogContext) => void;
  error: (message: string, context?: LogContext) => void;
}

export function createLogger(scope: string): Logger {
  return {
    debug: (message, context) => write("debug", scope, message, context),
    info: (message, context) => write("info", scope, message, context),
    warn: (message, context) => write("warn", scope, message, context),
    error: (message, context) => write("error", scope, message, context),
  };
}
