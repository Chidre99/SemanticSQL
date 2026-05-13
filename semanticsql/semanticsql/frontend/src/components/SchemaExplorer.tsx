import { useEffect, useState } from "react";
import { ChevronRight, Table2, Loader2, Columns3 } from "lucide-react";
import { api } from "../lib/api";
import type { TableInfo, TableDetail } from "../lib/types";

type Props = {
  database: string;
};

export default function SchemaExplorer({ database }: Props) {
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<TableDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setExpanded(null);
    setDetail(null);
    api
      .tables(database)
      .then((res) => { if (!cancelled) setTables(res.tables); })
      .catch(() => { if (!cancelled) setTables([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [database]);

  const toggle = async (name: string) => {
    if (expanded === name) {
      setExpanded(null);
      setDetail(null);
      return;
    }
    setExpanded(name);
    setDetail(null);
    setDetailLoading(true);
    try {
      const d = await api.table(database, name);
      setDetail(d);
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-1 min-h-0">
      <div className="text-xs uppercase tracking-wider text-ink-muted px-2 mb-1">Schema · {database}</div>
      {loading && (
        <div className="flex items-center gap-2 px-2 text-ink-muted text-sm">
          <Loader2 size={14} className="animate-spin" /> loading…
        </div>
      )}
      <div className="overflow-y-auto min-h-0 flex-1">
        {tables.map((t) => {
          const isOpen = expanded === t.name;
          return (
            <div key={t.name}>
              <button
                onClick={() => toggle(t.name)}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded hover:bg-bg-soft text-left text-sm transition-colors"
              >
                <ChevronRight size={12} className={isOpen ? "rotate-90 transition-transform" : "transition-transform"} />
                <Table2 size={14} className="text-accent" />
                <span className="flex-1 truncate">{t.name}</span>
                <span className="text-ink-faint text-xs">{t.column_count}</span>
              </button>
              {isOpen && (
                <div className="pl-7 pr-2 pb-2">
                  {detailLoading && <div className="text-xs text-ink-muted py-1">loading…</div>}
                  {detail && detail.table === t.name && (
                    <div className="text-xs space-y-0.5">
                      {detail.columns.map((c) => (
                        <div key={c} className="flex items-center gap-2 text-ink-muted">
                          <Columns3 size={10} className="text-ink-faint" />
                          <span className="font-mono">{c}</span>
                        </div>
                      ))}
                      {detail.sample_error && (
                        <div className="text-err text-xs italic mt-1">samples unavailable: {detail.sample_error}</div>
                      )}
                      {detail.samples?.length > 0 && (
                        <details className="mt-2">
                          <summary className="cursor-pointer text-ink-faint hover:text-ink">
                            sample rows ({detail.samples.length})
                          </summary>
                          <pre className="mt-1 max-h-40 overflow-auto text-[10px] text-ink-muted">
                            {JSON.stringify(detail.samples, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
