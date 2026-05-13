// Mirrors backend/app/orchestrator.py Event union. Kept in lockstep manually —
// the cost of a code-generator isn't worth it for ~15 event types.

export type RetrievalChunk = {
  table: string;
  doc_type: "table" | "enum" | "examples" | string;
  score: number;
  text: string;
};

export type ValidationIssue = {
  kind: "unknown_table" | "unknown_column" | "ambiguous_column";
  identifier: string;
  table: string | null;
  did_you_mean: string[];
};

export type ValidationReport = {
  ok: boolean;
  parse:       { ok: boolean; error: string | null };
  policy:      { ok: boolean; violations: string[] };
  identifiers: { ok: boolean; issues: ValidationIssue[]; referenced_tables: string[]; referenced_columns: [string, string][] };
  dryrun:      { ok: boolean; error: string | null };
};

export type SSEvent =
  | { type: "retrieval_start";    data: { question: string; database: string } }
  | { type: "retrieval_complete"; data: { chunks: RetrievalChunk[] } }
  | { type: "generation_start";   data: { attempt: number } }
  | { type: "sql_token";          data: { token: string } }
  | { type: "sql_complete";       data: { sql: string; attempt: number } }
  | { type: "validation_start";   data: { attempt: number } }
  | { type: "validation_complete";data: { report: ValidationReport; attempt: number } }
  | { type: "retry";              data: { attempt: number; previous_errors: string } }
  | { type: "execution_start";    data: { sql: string } }
  | { type: "row";                data: { row: Record<string, unknown> } }
  | { type: "execution_complete"; data: { columns: string[]; row_count: number; elapsed_ms: number } }
  | { type: "error";              data: { message: string; sql?: string; report?: ValidationReport } }
  | { type: "done";               data: { ok: boolean; elapsed_ms?: number } };

// UI status — derived from event stream.
export type Status =
  | "idle"
  | "retrieving"
  | "generating"
  | "validating"
  | "retrying"
  | "executing"
  | "done"
  | "error";

export type DatabaseInfo = { name: string; dialect: string; table_count: number };
export type TableInfo    = { name: string; column_count: number };
export type TableDetail  = {
  database: string;
  table: string;
  columns: string[];
  samples: Record<string, unknown>[];
  sample_error: string | null;
};
