export function getEngineLabel(searchSource: string): string {
  return searchSource === "scopus" ? "Scopus (Elsevier)" : "Semantic Scholar + OpenAlex + KCI";
}
