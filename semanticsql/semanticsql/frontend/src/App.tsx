import { useEffect, useState } from "react";
import { Sparkles, ThumbsUp, ThumbsDown } from "lucide-react";
import QueryInput from "./components/QueryInput";
import SQLPreview from "./components/SQLPreview";
import ResultsTable from "./components/ResultsTable";
import SchemaExplorer from "./components/SchemaExplorer";
import StatusBar from "./components/StatusBar";
import DatabaseSelector from "./components/DatabaseSelector";
import RetrievalPanel from "./components/RetrievalPanel";
import { useSSEQuery } from "./hooks/useSSEQuery";
import { api } from "./lib/api";
import type { DatabaseInfo } from "./lib/types";

export default function App() {
  const [databases, setDatabases] = useState<DatabaseInfo[]>([]);
  const [database, setDatabase] = useState<string>("pagila");
  const [question, setQuestion] = useState("");
  const [sqlOverride, setSqlOverride] = useState<string | null>(null); // user edits in editor
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);

  const { state, run, abort, reset } = useSSEQuery();

  // Load databases at mount
  useEffect(() => {
    api.databases().then((list) => {
      setDatabases(list);
      if (list.length && !list.some((d) => d.name === database)) {
        setDatabase(list[0].name);
      }
    }).catch(() => setDatabases([]));
  }, []);

  // Clear results when DB changes
  useEffect(() => {
    reset();
    setSqlOverride(null);
    setFeedback(null);
  }, [database]);

  const isRunning = ["retrieving", "generating", "validating", "retrying", "executing"].includes(state.status);
  const displayedSql = sqlOverride ?? state.streamingSql ?? "";

  const submit = () => {
    setSqlOverride(null);
    setFeedback(null);
    run(question, database);
  };

  const sendFeedback = async (was_correct: boolean) => {
    if (!state.finalSql) return;
    try {
      await api.feedback({ question, sql: state.finalSql, database, was_correct });
      setFeedback(was_correct ? "up" : "down");
    } catch {/* ignore */}
  };

  return (
    <div className="h-full flex flex-col">
      {/* Top bar */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-bg-soft">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-accent" />
          <span className="font-semibold tracking-tight">SemanticSQL</span>
          <span className="text-ink-faint text-xs ml-2">natural language → safe SQL</span>
        </div>
        <DatabaseSelector databases={databases} selected={database} onSelect={setDatabase} />
      </header>

      {/* Main layout */}
      <div className="flex-1 grid grid-cols-[260px_1fr] min-h-0">
        {/* Sidebar */}
        <aside className="border-r border-bg-soft p-3 min-h-0 flex flex-col">
          <SchemaExplorer database={database} />
        </aside>

        {/* Main */}
        <main className="flex flex-col p-4 gap-4 min-h-0 overflow-auto">
          {/* 1. Query input */}
          <QueryInput
            value={question}
            onChange={setQuestion}
            onSubmit={submit}
            onAbort={abort}
            isRunning={isRunning}
          />

          {/* 2. Status bar — visible only while something is happening or done */}
          {state.status !== "idle" && (
            <div className="flex items-center justify-between">
              <StatusBar status={state.status} attempt={state.attempt} />
              {state.elapsedMs != null && state.status === "done" && (
                <span className="text-xs text-ink-muted">{state.elapsedMs.toLocaleString()} ms total</span>
              )}
            </div>
          )}

          {/* 3. Retrieved context (collapsible) */}
          <RetrievalPanel chunks={state.retrievedChunks} />

          {/* 4. SQL editor + validation report */}
          {(displayedSql || state.status !== "idle") && (
            <SQLPreview
              value={displayedSql}
              onChange={(v) => setSqlOverride(v)}
              database={database}
              externalReport={state.validationReport}
            />
          )}

          {/* 5. Error banner */}
          {state.error && (
            <div className="rounded-md border border-err/30 bg-err/5 px-3 py-2 text-sm text-err">
              {state.error}
            </div>
          )}

          {/* 6. Results table */}
          {(state.rows.length > 0 || state.status === "executing") && (
            <ResultsTable
              columns={state.columns}
              rows={state.rows}
              elapsedMs={state.elapsedMs}
            />
          )}

          {/* 7. Feedback */}
          {state.status === "done" && state.finalSql && (
            <div className="flex items-center gap-3 pt-2 border-t border-bg-soft text-sm">
              <span className="text-ink-muted">Was this answer correct?</span>
              <button
                onClick={() => sendFeedback(true)}
                disabled={feedback !== null}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-md border text-xs transition-colors
                  ${feedback === "up"
                    ? "border-ok bg-ok/10 text-ok"
                    : "border-bg-soft hover:border-ok/40 text-ink-muted hover:text-ok"}`}
              >
                <ThumbsUp size={12} /> Yes
              </button>
              <button
                onClick={() => sendFeedback(false)}
                disabled={feedback !== null}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-md border text-xs transition-colors
                  ${feedback === "down"
                    ? "border-err bg-err/10 text-err"
                    : "border-bg-soft hover:border-err/40 text-ink-muted hover:text-err"}`}
              >
                <ThumbsDown size={12} /> No
              </button>
              {feedback && <span className="text-ink-faint text-xs italic">thanks for the feedback</span>}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
