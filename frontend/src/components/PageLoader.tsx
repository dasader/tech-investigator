import type { ReactNode } from "react";

export default function PageLoader({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-[calc(100vh-61px)] flex flex-col items-center justify-center gap-4">
      <div
        className="w-10 h-10 rounded-full border-4 border-t-transparent animate-spin"
        style={{ borderColor: "var(--color-border)", borderTopColor: "var(--color-amber)" }}
      />
      <p className="text-sm" style={{ color: "var(--color-text-3)" }}>{children}</p>
    </div>
  );
}
