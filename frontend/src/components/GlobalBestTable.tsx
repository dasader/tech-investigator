import type { ParsedTable } from "../utils/markdownTable";

function renderCell(cell: string) {
  const doiMatch = cell.match(/10\.\d{4,9}\/[^\s)\]]+/);
  if (doiMatch) {
    const doi = doiMatch[0].replace(/[.,;]+$/, "");
    const before = cell.slice(0, doiMatch.index!);
    const after  = cell.slice(doiMatch.index! + doi.length);
    return (
      <>
        {before}
        <a
          href={`https://doi.org/${doi}`}
          target="_blank"
          rel="noreferrer"
          className="hover:underline underline-offset-2"
          style={{ color: "var(--color-blue-data)" }}
        >
          {doi}
        </a>
        {after}
      </>
    );
  }
  return cell;
}

export default function GlobalBestTable({ data }: { data: ParsedTable }) {
  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: "var(--color-surface)", border: "1px solid var(--color-border-subtle)" }}
    >
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr style={{ background: "var(--color-navy-dark)" }}>
              {data.headers.map((h, i) => (
                <th
                  key={i}
                  className="px-4 py-3 text-left text-[11px] font-semibold tracking-wider uppercase"
                  style={{ color: "rgba(180,210,250,0.85)", fontFamily: "var(--font-heading)" }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, ri) => (
              <tr
                key={ri}
                style={{
                  borderBottom: ri < data.rows.length - 1 ? "1px solid var(--color-border-subtle)" : undefined,
                  background: ri % 2 === 1 ? "var(--color-surface-2)" : undefined,
                }}
              >
                {row.map((cell, ci) => (
                  <td
                    key={ci}
                    className="px-4 py-3 text-[13px]"
                    style={{
                      color: "var(--color-text-2)",
                      fontFamily: ci === 0 ? "var(--font-heading)" : "var(--font-body)",
                      fontWeight: ci === 0 ? 600 : 400,
                    }}
                  >
                    {renderCell(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
