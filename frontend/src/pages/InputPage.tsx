import { useState } from "react";
import CategorySelect from "../components/CategorySelect";
import { createTechInput } from "../api/client";

interface Props { onNext: (queryId: number) => void; }

const SOURCE_OPTIONS = [
  { value: "semantic_scholar", label: "Semantic Scholar" },
  { value: "scopus",           label: "Scopus (Elsevier)" },
  { value: "openalex",         label: "OpenAlex" },
] as const;

type SearchSource = typeof SOURCE_OPTIONS[number]["value"];

export default function InputPage({ onNext }: Props) {
  const [category,      setCategory]      = useState("");
  const [description,   setDescription]   = useState("");
  const [email,         setEmail]         = useState("");
  const [searchSource,  setSearchSource]  = useState<SearchSource>("semantic_scholar");
  const [loading,       setLoading]       = useState(false);
  const [error,         setError]         = useState("");

  const handleSubmit = async () => {
    if (!category || !description) return;
    setLoading(true);
    setError("");
    try {
      const query = await createTechInput({
        category,
        description,
        user_email: email || undefined,
        search_source: searchSource,
      });
      onNext(query.id);
    } catch {
      setError("입력 저장에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setLoading(false);
    }
  };

  const sourceLabel =
    SOURCE_OPTIONS.find((o) => o.value === searchSource)?.label ?? "Semantic Scholar";

  return (
    <div className="min-h-[calc(100vh-61px)] flex items-center justify-center px-4 py-16">
      <div className="w-full max-w-xl fade-up">
        <div className="mb-10 text-center">
          <h1
            className="text-3xl font-bold tracking-tight mb-3"
            style={{ fontFamily: "var(--font-heading)", color: "var(--color-navy-dark)" }}
          >
            국가전략기술 Spec 조사
          </h1>
          <p className="text-sm" style={{ color: "var(--color-text-3)" }}>
            기술 분야와 세부 설명을 입력하면 AI가 핵심 지표를 추출하고 논문 기반 수치를 분석합니다
          </p>
        </div>

        <div
          className="rounded-2xl shadow-sm overflow-hidden"
          style={{ background: "var(--color-surface)", border: "1px solid var(--color-border-subtle)" }}
        >
          <div
            className="px-7 py-4 text-xs font-semibold tracking-widest uppercase"
            style={{ background: "var(--color-navy-dark)", color: "rgba(180,205,240,0.6)" }}
          >
            분석 설정
          </div>
          <div className="px-7 py-7 space-y-5">

            {/* 논문 데이터 소스 선택 */}
            <div>
              <label
                className="block text-xs font-semibold mb-2 uppercase tracking-widest"
                style={{ color: "var(--color-text-3)" }}
              >
                논문 데이터 소스
              </label>
              <div className="flex rounded-lg overflow-hidden" style={{ border: "1.5px solid var(--color-border)" }}>
                {SOURCE_OPTIONS.map((opt, i) => {
                  const active = searchSource === opt.value;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setSearchSource(opt.value)}
                      className="flex-1 py-2 text-sm font-medium transition-colors duration-150"
                      style={{
                        background: active ? "var(--color-navy-dark)" : "var(--color-surface-2)",
                        color: active ? "var(--color-text-inv)" : "var(--color-text-3)",
                        borderRight: i < SOURCE_OPTIONS.length - 1 ? "1px solid var(--color-border)" : undefined,
                      }}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <label
                className="block text-xs font-semibold mb-2 uppercase tracking-widest"
                style={{ color: "var(--color-text-3)" }}
              >
                기술 분야
              </label>
              <CategorySelect value={category} onChange={setCategory} />
            </div>

            <div>
              <label
                className="block text-xs font-semibold mb-2 uppercase tracking-widest"
                style={{ color: "var(--color-text-3)" }}
              >
                세부 설명
              </label>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="예: HBM 고대역폭 메모리 적층 기술, 이형접합 기판 기반의 글로벌 Spec 조사"
                className="w-full rounded-lg px-3 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 transition-shadow"
                style={{
                  background: "var(--color-surface-2)",
                  border: "1.5px solid var(--color-border)",
                  color: "var(--color-text)",
                  fontFamily: "var(--font-body)",
                  lineHeight: "1.6",
                  minHeight: "120px",
                }}
              />
            </div>

            <div>
              <label
                className="block text-xs font-semibold mb-2 uppercase tracking-widest"
                style={{ color: "var(--color-text-3)" }}
              >
                이메일 <span className="normal-case font-normal">(완료 알림, 선택)</span>
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="example@email.com"
                className="w-full rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 transition-shadow"
                style={{
                  background: "var(--color-surface-2)",
                  border: "1.5px solid var(--color-border)",
                  color: "var(--color-text)",
                  fontFamily: "var(--font-body)",
                }}
              />
            </div>

            {error && (
              <p className="text-sm px-3 py-2 rounded-lg" style={{ background: "#fff1f0", color: "#c0392b", border: "1px solid #ffd0cc" }}>
                {error}
              </p>
            )}

            <button
              onClick={handleSubmit}
              disabled={loading || !category || !description}
              className="w-full py-3 rounded-xl text-sm font-semibold transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
              style={{
                background: loading || !category || !description
                  ? undefined
                  : "var(--color-navy-dark)",
                color: "var(--color-text-inv)",
                letterSpacing: "0.02em",
              }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  저장 중...
                </span>
              ) : "지표 생성하기 →"}
            </button>
          </div>
        </div>

        <p className="text-center text-xs mt-6" style={{ color: "var(--color-text-3)" }}>
          {sourceLabel} 논문 데이터 기반 · Gemini AI 수치 추출 · 분석 소요 5–15분
        </p>
      </div>
    </div>
  );
}
