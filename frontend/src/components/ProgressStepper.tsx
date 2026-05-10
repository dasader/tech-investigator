interface Props { currentStep: string | null; progressPct: number; status: string; }

export default function ProgressStepper({ currentStep, progressPct, status }: Props) {
  return (
    <div className="space-y-4">
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div
          className="bg-blue-500 h-2 rounded-full transition-all duration-500"
          style={{ width: `${progressPct}%` }}
        />
      </div>
      <p className="text-center text-sm text-gray-600">{currentStep || "대기 중..."}</p>
      {status === "done" && <p className="text-center text-green-600 font-medium">분석 완료!</p>}
      {status === "failed" && <p className="text-center text-red-600">오류가 발생했습니다.</p>}
    </div>
  );
}
