import { useState, useEffect } from "react";
import IndicatorList from "../components/IndicatorList";
import { generateIndicators, updateIndicator, deleteIndicator, startJob } from "../api/client";

interface Indicator { id: number; name: string; unit: string; description: string; confirmed_by_user: boolean; }
interface Props { queryId: number; onNext: (jobId: number) => void; }

export default function IndicatorEditorPage({ queryId, onNext }: Props) {
  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    generateIndicators(queryId)
      .then((data: Indicator[]) => { setIndicators(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [queryId]);

  const handleUpdate = (id: number, data: Partial<Indicator>) => {
    setIndicators(prev => prev.map(i => i.id === id ? { ...i, ...data } : i));
    void updateIndicator(id, data);
  };

  const handleDelete = (id: number) => {
    setIndicators(prev => prev.filter(i => i.id !== id));
    void deleteIndicator(id);
  };

  const handleConfirm = async () => {
    await Promise.all(indicators.map(i => updateIndicator(i.id, { confirmed_by_user: true })));
    const job = await startJob(queryId) as { id: number };
    onNext(job.id);
  };

  if (loading) return <div className="p-8 text-center">AI가 지표를 생성하고 있습니다...</div>;

  return (
    <div className="max-w-xl mx-auto p-8">
      <h2 className="text-xl font-bold mb-2">지표 확인 및 편집</h2>
      <p className="text-sm text-gray-500 mb-4">이름·단위를 수정하거나 불필요한 지표를 삭제하세요.</p>
      <IndicatorList indicators={indicators} onUpdate={handleUpdate} onDelete={handleDelete} />
      <button
        onClick={handleConfirm}
        disabled={indicators.length === 0}
        className="mt-6 w-full bg-green-600 text-white py-2 rounded-lg hover:bg-green-700 disabled:opacity-50"
      >
        확정 후 분석 시작 →
      </button>
    </div>
  );
}
