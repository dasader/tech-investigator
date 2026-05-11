export function getEngineLabel(searchSource: string): string {
  return searchSource === "scopus" ? "Scopus (Elsevier) + Gemini" : "Semantic Scholar + Gemini";
}
