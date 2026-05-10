import { useState } from "react";
import CategorySelect from "../components/CategorySelect";
import { createTechInput, generateIndicators } from "../api/client";

interface Props { onNext: (queryId: number) => void; }

export default function InputPage({ onNext }: Props) {
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!category || !description) return;
    setLoading(true);
    try {
      const query = await createTechInput({ category, description, user_email: email || undefined });
      await generateIndicators(query.id);
      onNext(query.id);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-6">국가전략기술 Spec 조사</h1>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">기술 분야 선택</label>
          <CategorySelect value={category} onChange={setCategory} />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">세부 설명</label>
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="예: HBM 고대역폭 메모리 적층 기술, 이형접합 기판 기반..."
            className="w-full border rounded-lg p-2 text-sm h-28 resize-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">이메일 (완료 알림, 선택)</label>
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="w-full border rounded-lg p-2 text-sm"
          />
        </div>
        <button
          onClick={handleSubmit}
          disabled={loading || !category || !description}
          className="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "지표 생성 중..." : "지표 생성 →"}
        </button>
      </div>
    </div>
  );
}
