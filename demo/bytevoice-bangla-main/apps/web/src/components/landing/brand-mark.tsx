export function BrandMark({ tone = "light" }: { tone?: "light" | "dark" }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <span aria-hidden className="relative inline-flex h-7 w-7 items-center justify-center">
        <span className="absolute inset-0 rounded-full bg-teal/25" />
        <span className="h-4 w-4 rounded-full bg-[radial-gradient(circle_at_35%_30%,#d6fff7,#26b8a6_45%,#0e7c70)]" />
      </span>
      <span className={`text-[1.05rem] font-semibold tracking-tight ${tone === "light" ? "text-white" : "text-ink"}`}>
        ByteVoice <span className={tone === "light" ? "text-mint" : "text-teal-deep"}>বাংলা</span>
      </span>
    </span>
  );
}
