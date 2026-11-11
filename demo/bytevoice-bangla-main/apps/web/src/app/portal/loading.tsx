export default function PortalLoading() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true" aria-label="Loading">
      <div className="h-9 w-56 animate-pulse rounded-lg bg-line/70" />
      <div className="h-24 animate-pulse rounded-2xl bg-line/50" />
      <div className="h-72 animate-pulse rounded-2xl bg-line/40" />
    </div>
  );
}
