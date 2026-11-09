// Terraced hills with rows of coffee, drawn over the bottom of the hero photo so the
// photo settles into the page like mist into a valley (D-57). Decorative only.
// The front ridge is the page colour (--mist), so the photo ends in the hills' outline.
export function EstateHills({ className }: { className?: string }) {
  const rows = Array.from({ length: 6 }, (_, i) => i);
  return (
    <svg
      className={className}
      viewBox="0 120 1200 200"
      preserveAspectRatio="xMidYMax slice"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M0 190 C 220 130, 420 150, 640 185 S 980 120, 1200 165 L1200 320 L0 320 Z"
        fill="#eef1ec"
        fillOpacity="0.35"
      />
      <path
        d="M0 235 C 260 180, 520 200, 760 228 S 1060 190, 1200 212 L1200 320 L0 320 Z"
        fill="#eef1ec"
        fillOpacity="0.6"
      />
      <path d="M0 268 C 300 228, 560 246, 800 266 S 1080 236, 1200 254 L1200 320 L0 320 Z" fill="#eef1ec" />
      {rows.map((i) => (
        <path
          key={i}
          d={`M0 ${284 + i * 7} C 300 ${244 + i * 7}, 560 ${262 + i * 7}, 800 ${282 + i * 7} S 1080 ${252 + i * 7}, 1200 ${270 + i * 7}`}
          fill="none"
          stroke="#cfd8cd"
          strokeWidth="3"
          strokeDasharray="2 14"
          strokeLinecap="round"
        />
      ))}
      <circle cx="914" cy="272" r="3.5" fill="#b3262e" />
      <circle cx="922" cy="275" r="3" fill="#b3262e" />
    </svg>
  );
}
