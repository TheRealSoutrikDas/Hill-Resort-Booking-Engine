// The one bold element on the page: terraced hills with rows of coffee and a band of
// mist, drawn as an SVG (no photos are invented, A-157). Decorative only.
export function EstateHills({ className }: { className?: string }) {
  const rows = Array.from({ length: 7 }, (_, i) => i);
  return (
    <svg
      className={className}
      viewBox="0 50 1200 270"
      preserveAspectRatio="xMidYMax slice"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M0 150 C 180 70, 330 60, 520 120 S 860 40, 1200 110 L1200 320 L0 320 Z" fill="#b9c8b6" />
      <path d="M0 200 C 220 130, 420 150, 640 190 S 980 120, 1200 170 L1200 320 L0 320 Z" fill="#7f9a7c" />
      <defs>
        <linearGradient id="estate-mist" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#eef1ec" stopOpacity="0" />
          <stop offset="0.5" stopColor="#eef1ec" stopOpacity="0.75" />
          <stop offset="1" stopColor="#eef1ec" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="0" y="150" width="1200" height="70" fill="url(#estate-mist)" />
      <path d="M0 250 C 260 190, 520 210, 760 240 S 1060 200, 1200 225 L1200 320 L0 320 Z" fill="#3f5e45" />
      {rows.map((i) => (
        <path
          key={i}
          d={`M0 ${262 + i * 9} C 300 ${212 + i * 9}, 560 ${232 + i * 9}, 800 ${258 + i * 9} S 1080 ${222 + i * 9}, 1200 ${246 + i * 9}`}
          fill="none"
          stroke="#2a4a33"
          strokeWidth="3"
          strokeDasharray="2 14"
          strokeLinecap="round"
        />
      ))}
      <circle cx="914" cy="246" r="3.5" fill="#b3262e" />
      <circle cx="922" cy="249" r="3" fill="#b3262e" />
    </svg>
  );
}
