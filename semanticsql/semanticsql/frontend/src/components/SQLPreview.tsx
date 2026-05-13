import { useEffect, useMemo, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { sql, PostgreSQL, MySQL } from "@codemirror/lang-sql";
import { EditorView } from "@codemirror/view";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import type { ValidationReport } from "../lib/types";

type Props = {
  value: string;
  onChange: (v: string) => void;
  database: string;
  /** When the orchestrator emits a report we display it directly. */
  externalReport: ValidationReport | null;
};

const editorTheme = EditorView.theme(
  {
    "&":              { color: "#e8eaed", backgroundColor: "transparent" },
    ".cm-content":    { caretColor: "#7ab7ff" },
    ".cm-line":       { padding: "0 8px" },
    "&.cm-focused .cm-cursor": { borderLeftColor: "#7ab7ff" },
    ".cm-selectionBackground, ::selection": { background: "#2b4a73 !important" },
  },
  { dark: true }
);

export default function SQLPreview({ value, onChange, database, externalReport }: Props) {
  const [localReport, setLocalReport] = useState<ValidationReport | null>(null);
  const [validating, setValidating] = useState(false);

  // Reset local report when external comes in (most recent wins)
  useEffect(() => { if (externalReport) setLocalReport(null); }, [externalReport]);

  // Debounced manual validation on edit
  useEffect(() => {
    if (!value.trim() || externalReport) return;
    const t = setTimeout(async () => {
      try {
        setValidating(true);
        const report = await api.validate(value, database);
        setLocalReport(report);
      } catch {
        // swallow — editor stays usable even if backend is down
      } finally {
        setValidating(false);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [value, database, externalReport]);

  const extensions = useMemo(() => {
    const dialect = database === "chinook" ? MySQL : PostgreSQL;
    return [sql({ dialect, upperCaseKeywords: true }), editorTheme];
  }, [database]);

  const report = externalReport ?? localReport;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between text-xs text-ink-muted px-1">
        <span className="uppercase tracking-wider">Generated SQL</span>
        <StatusPill report={report} validating={validating} />
      </div>
      <div className="border border-bg-soft rounded-md bg-bg-soft min-h-[10rem] overflow-hidden">
        <CodeMirror
          value={value}
          onChange={onChange}
          extensions={extensions}
          theme="dark"
          basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: false }}
        />
      </div>
      {report && !report.ok && <ReportErrors report={report} />}
    </div>
  );
}

function StatusPill({ report, validating }: { report: ValidationReport | null; validating: boolean }) {
  if (validating) {
    return <span className="flex items-center gap-1.5 text-ink-muted"><Loader2 size={12} className="animate-spin" /> validating</span>;
  }
  if (!report) return <span className="text-ink-faint">—</span>;
  if (report.ok) {
    return <span className="flex items-center gap-1.5 text-ok"><CheckCircle2 size={12} /> validates</span>;
  }
  return <span className="flex items-center gap-1.5 text-err"><AlertCircle size={12} /> invalid</span>;
}

function ReportErrors({ report }: { report: ValidationReport }) {
  const items: { tag: string; msg: string }[] = [];
  if (!report.parse.ok && report.parse.error) items.push({ tag: "parse", msg: report.parse.error });
  for (const v of report.policy.violations) items.push({ tag: "policy", msg: v });
  for (const i of report.identifiers.issues) {
    let msg = `${i.kind === "unknown_table" ? "unknown table" : "unknown column"} '${i.identifier}'`;
    if (i.table && i.kind === "unknown_column") msg += ` on '${i.table}'`;
    if (i.did_you_mean?.length) msg += ` — did you mean: ${i.did_you_mean.join(", ")}`;
    items.push({ tag: "ident", msg });
  }
  if (!report.dryrun.ok && report.dryrun.error) items.push({ tag: "dryrun", msg: report.dryrun.error });

  if (!items.length) return null;
  return (
    <div className="rounded-md border border-err/30 bg-err/5 px-3 py-2 text-xs space-y-1">
      {items.map((it, i) => (
        <div key={i} className="flex gap-2">
          <span className="text-err/60 uppercase tracking-wider min-w-[3rem]">{it.tag}</span>
          <span className="text-ink">{it.msg}</span>
        </div>
      ))}
    </div>
  );
}
