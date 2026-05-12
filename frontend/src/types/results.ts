export interface MetricValue {
  value: number | null;
  unit: string | null;
  year: number | null;
  country: string | null;
  confidence_score: number;
  paper_title: string | null;
  journal_name: string | null;
  doi: string | null;
  source_url: string | null;
  quote: string | null;
}

export interface IndicatorResult {
  indicator: { name: string; unit: string };
  metric_values: MetricValue[];
}

export interface ResultsData {
  job_id: number;
  analyzed_at: string | null;
  report_markdown: string | null;
  search_source: string;
  category?: string;
  description?: string;
  indicators: IndicatorResult[];
}
