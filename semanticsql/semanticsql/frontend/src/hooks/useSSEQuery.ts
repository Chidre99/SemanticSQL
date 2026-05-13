import { useCallback, useRef, useState } from "react";
import type { RetrievalChunk, SSEvent, Status, ValidationReport } from "../lib/types";

/**
 * State machine wrapper around a streaming POST /query.
 *
 * Why not EventSource?
 *   - EventSource only does GET. Our request body has the question.
 *   - It also can't be aborted mid-stream in any nice way.
 *
 * Implementation: fetch() with `body`, read `res.body` as a stream, parse
 * the SSE framing (`data: <json>\n\n`) by hand. ~40 lines of code, gives us
 * POST + AbortController for free.
 */

export type SSEState = {
  status: Status;
  attempt: number;
  retrievedChunks: RetrievalChunk[];
  streamingSql: string;
  finalSql: string;
  validationReport: ValidationReport | null;
  rows: Record<string, unknown>[];
  columns: string[];
  error: string | null;
  elapsedMs: number | null;
};

const INITIAL: SSEState = {
  status: "idle",
  attempt: 0,
  retrievedChunks: [],
  streamingSql: "",
  finalSql: "",
  validationReport: null,
  rows: [],
  columns: [],
  error: null,
  elapsedMs: null,
};

export function useSSEQuery() {
  const [state, setState] = useState<SSEState>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const reset = useCallback(() => {
    abort();
    setState(INITIAL);
  }, [abort]);

  const run = useCallback(async (question: string, database: string) => {
    abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({ ...INITIAL, status: "retrieving" });

    let res: Response;
    try {
      res = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ question, database }),
        signal: controller.signal,
      });
    } catch (err: any) {
      if (err?.name === "AbortError") return;
      setState((s) => ({ ...s, status: "error", error: String(err?.message || err) }));
      return;
    }

    if (!res.ok || !res.body) {
      const text = await res.text().catch(() => "");
      setState((s) => ({ ...s, status: "error", error: `HTTP ${res.status}: ${text}` }));
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        // SSE framing: events separated by "\n\n"
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const line = frame.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          try {
            const ev: SSEvent = JSON.parse(line.slice(6));
            applyEvent(setState, ev);
          } catch {
            // ignore malformed frames
          }
        }
      }
    } catch (err: any) {
      if (err?.name !== "AbortError") {
        setState((s) => ({ ...s, status: "error", error: String(err?.message || err) }));
      }
    } finally {
      abortRef.current = null;
    }
  }, [abort]);

  return { state, run, abort, reset };
}

function applyEvent(setState: React.Dispatch<React.SetStateAction<SSEState>>, ev: SSEvent) {
  setState((s) => {
    switch (ev.type) {
      case "retrieval_start":
        return { ...s, status: "retrieving", error: null };
      case "retrieval_complete":
        return { ...s, retrievedChunks: ev.data.chunks };
      case "generation_start":
        return { ...s, status: "generating", attempt: ev.data.attempt, streamingSql: "" };
      case "sql_token":
        return { ...s, streamingSql: s.streamingSql + ev.data.token };
      case "sql_complete":
        return { ...s, finalSql: ev.data.sql, streamingSql: ev.data.sql };
      case "validation_start":
        return { ...s, status: "validating" };
      case "validation_complete":
        return { ...s, validationReport: ev.data.report };
      case "retry":
        return { ...s, status: "retrying", attempt: ev.data.attempt };
      case "execution_start":
        return { ...s, status: "executing", rows: [] };
      case "row":
        return { ...s, rows: [...s.rows, ev.data.row] };
      case "execution_complete":
        return { ...s, columns: ev.data.columns, elapsedMs: ev.data.elapsed_ms };
      case "error":
        return { ...s, status: "error", error: ev.data.message };
      case "done":
        return { ...s, status: ev.data.ok ? "done" : (s.status === "error" ? "error" : "error"), elapsedMs: ev.data.elapsed_ms ?? s.elapsedMs };
      default:
        return s;
    }
  });
}
