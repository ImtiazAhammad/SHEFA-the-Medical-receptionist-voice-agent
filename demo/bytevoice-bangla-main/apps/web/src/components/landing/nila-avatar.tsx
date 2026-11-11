import { useId } from "react";

interface NilaAvatarProps {
  className?: string;
  speaking?: boolean;
}

export function NilaAvatar({ className, speaking = false }: NilaAvatarProps) {
  const idPrefix = useId().replace(/:/g, "");
  const backdropId = `${idPrefix}-backdrop`;
  const topId = `${idPrefix}-top`;
  const frameId = `${idPrefix}-frame`;
  return (
    <svg viewBox="0 0 200 200" className={className} role="img" aria-label="Nila">
      <defs>
        <linearGradient id={backdropId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#9be8dc" />
          <stop offset="1" stopColor="#26b8a6" />
        </linearGradient>
        <linearGradient id={topId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0e7c70" />
          <stop offset="1" stopColor="#0a302d" />
        </linearGradient>
        <clipPath id={frameId}>
          <circle cx="100" cy="100" r="96" />
        </clipPath>
      </defs>
      <circle cx="100" cy="100" r="96" fill={`url(#${backdropId})`} />
      <g clipPath={`url(#${frameId})`}>
        <path d="M30 210c4-42 34-64 70-64s66 22 70 64z" fill={`url(#${topId})`} />
        <path d="M84 150c4 10 28 10 32 0l-2-18H86z" fill="#b97c5a" />
        <path d="M70 154c10 14 50 14 60 0" fill="none" stroke="#f4a63a" strokeWidth="5" strokeLinecap="round" />
        <circle cx="100" cy="36" r="17" fill="#2a1712" />
        <path d="M58 86c0-30 18-48 42-48s42 18 42 48c0 10-2 20-6 28H64c-4-8-6-18-6-28z" fill="#2a1712" />
        <ellipse cx="100" cy="96" rx="32" ry="38" fill="#c98b66" />
        <path d="M68 84c6-22 22-30 36-30 14 0 26 8 30 28-12-10-28-14-44-12-8 1-16 6-22 14z" fill="#2a1712" />
        <ellipse cx="88" cy="96" rx="3.4" ry="4" fill="#2a1712" />
        <ellipse cx="112" cy="96" rx="3.4" ry="4" fill="#2a1712" />
        <path d="M82 88q6-3 11 0M107 88q6-3 11 0" stroke="#2a1712" strokeWidth="2" fill="none" strokeLinecap="round" />
        <circle cx="100" cy="91" r="1.6" fill="#e0565b" />
        <path d="M98 104q2 4 5 0" stroke="#9c6347" strokeWidth="2" fill="none" strokeLinecap="round" />
        <path
          d={speaking ? "M90 115q10 10 20 0q-10 4-20 0z" : "M90 115q10 7 20 0"}
          fill={speaking ? "#7a3436" : "none"}
          stroke="#7a3436"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
        <ellipse cx="80" cy="110" rx="6" ry="3.5" fill="#e0565b" opacity="0.18" />
        <ellipse cx="120" cy="110" rx="6" ry="3.5" fill="#e0565b" opacity="0.18" />
        <path d="M64 96c0-26 16-44 36-44s36 18 36 44" fill="none" stroke="#05211f" strokeWidth="5" strokeLinecap="round" />
        <rect x="58" y="88" width="12" height="22" rx="6" fill="#05211f" />
        <rect x="130" y="88" width="12" height="22" rx="6" fill="#05211f" />
        <path d="M64 108c0 14 8 20 22 20h6" fill="none" stroke="#05211f" strokeWidth="3.5" strokeLinecap="round" />
        <rect x="90" y="124" width="10" height="7" rx="3.5" fill="#f4a63a" />
      </g>
      <circle cx="100" cy="100" r="96" fill="none" stroke="#fbfcfb" strokeOpacity="0.6" strokeWidth="3" />
    </svg>
  );
}
