import { useQuery } from "@tanstack/react-query";
import { Empty, MonthBar, PageHead, QueryState, StatusStamp, useCategoryName, useMonth } from "../../components/ui";
import { get } from "../../lib/api";
import { monthName, titleCase } from "../../lib/format";
import type { Insight } from "../../lib/types";

export default function Insights() {
  const [month, setMonth] = useMonth();
  const catName = useCategoryName();
  const q = useQuery({ queryKey: ["insights", month], queryFn: () => get<Insight[]>("/me/insights", { month }) });
  return (
    <>
      <PageHead title={`Notes · ${monthName(month)}`} sub="What PAM noticed: limits crossed, unusual jumps, bills that changed or went missing." right={<MonthBar month={month} onChange={setMonth} />} />
      <QueryState q={q}>
        {(rows) => rows.length === 0 ? <Empty title="Nothing to flag" hint="No limits crossed and nothing unusual this month." /> : (
          <ul className="border-t border-rule-strong">
            {rows.map((i) => (
              <li key={i.insight_id} className="grid grid-cols-[72px_1fr] sm:grid-cols-[72px_1fr_180px] gap-3 py-3 border-b border-rule">
                <div><StatusStamp status={i.severity} /></div>
                <div>
                  <p>{i.message}</p>
                  <p className="text-xs text-muted mt-0.5">{titleCase(i.insight_type)}{i.category_code && <> · {catName(i.category_code)}</>}</p>
                </div>
                <div className="hidden sm:block text-right text-sm text-muted">{i.severity === "INFO" ? "" : titleCase(i.severity)}</div>
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </>
  );
}
