import type { z } from "zod";

export class RepositoryError extends Error {
  constructor(operation: string, detail: string) {
    super(`${operation} failed: ${detail}`);
    this.name = "RepositoryError";
  }
}

export function parseRows<Schema extends z.ZodType>(schema: Schema, rows: unknown, operation: string): z.infer<Schema>[] {
  if (!Array.isArray(rows)) {
    return [];
  }
  return rows.map((row) => {
    const parsed = schema.safeParse(row);
    if (!parsed.success) {
      throw new RepositoryError(operation, parsed.error.message);
    }
    return parsed.data;
  });
}

export function parseRow<Schema extends z.ZodType>(schema: Schema, row: unknown, operation: string): z.infer<Schema> | null {
  if (row === null || row === undefined) {
    return null;
  }
  const parsed = schema.safeParse(row);
  if (!parsed.success) {
    throw new RepositoryError(operation, parsed.error.message);
  }
  return parsed.data;
}
