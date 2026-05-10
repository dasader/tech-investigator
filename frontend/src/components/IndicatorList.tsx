interface Indicator { id: number; name: string; unit: string; description: string; confirmed_by_user: boolean; }
interface Props {
  indicators: Indicator[];
  onUpdate: (id: number, data: Partial<Indicator>) => void;
  onDelete: (id: number) => void;
}

export default function IndicatorList({ indicators, onUpdate, onDelete }: Props) {
  return (
    <ul className="space-y-2">
      {indicators.map(ind => (
        <li key={ind.id} className="flex items-center gap-2 border rounded-lg p-3 bg-green-50">
          <input
            className="flex-1 text-sm font-medium bg-transparent border-b border-transparent focus:border-green-400 outline-none"
            value={ind.name}
            onChange={e => onUpdate(ind.id, { name: e.target.value })}
          />
          <input
            className="w-20 text-xs text-gray-500 bg-transparent border-b border-transparent focus:border-green-400 outline-none text-right"
            value={ind.unit || ""}
            placeholder="단위"
            onChange={e => onUpdate(ind.id, { unit: e.target.value })}
          />
          <button onClick={() => onDelete(ind.id)} className="text-red-400 hover:text-red-600 text-lg leading-none">×</button>
        </li>
      ))}
    </ul>
  );
}
