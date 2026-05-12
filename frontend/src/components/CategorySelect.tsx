const CATEGORIES = [
  "반도체·디스플레이", "이차전지", "첨단 모빌리티", "차세대 원자력",
  "첨단 바이오", "우주·항공", "사이버 보안", "인공지능",
  "차세대 통신", "첨단 로봇·제조", "양자", "첨단소재",
];

interface Props { value: string; onChange: (v: string) => void; }

export default function CategorySelect({ value, onChange }: Props) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full rounded-lg px-3 py-2.5 text-sm font-medium focus:outline-none focus:ring-2 transition-shadow"
      style={{
        background: "var(--color-surface)",
        border: "1.5px solid var(--color-border)",
        color: value ? "var(--color-text)" : "var(--color-text-3)",
        fontFamily: "var(--font-body)",
      }}
    >
      <option value="">분야를 선택하세요</option>
      {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
    </select>
  );
}
