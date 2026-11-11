import type { SUPPORTED_LANGUAGES } from "@/constants/app";
import type { bn } from "@/i18n/bn";

export type Language = (typeof SUPPORTED_LANGUAGES)[number];

type Widen<Value> = Value extends string
  ? string
  : Value extends readonly (infer Item)[]
    ? readonly Widen<Item>[]
    : Value extends object
      ? { readonly [Key in keyof Value]: Widen<Value[Key]> }
      : Value;

export type Dictionary = Widen<typeof bn>;
