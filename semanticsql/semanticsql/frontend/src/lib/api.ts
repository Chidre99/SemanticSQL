import type { DatabaseInfo, TableInfo, TableDetail, ValidationReport } from "./types";

const BASE = "/api";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text || path}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health:    () => json<{ ok: boolean }>(`/health`),
  databases: () => json<DatabaseInfo[]>(`/schemas`),
  tables:    (db: string) => json<{ database: string; dialect: string; tables: TableInfo[] }>(`/schemas/${db}`),
  table:     (db: string, table: string) => json<TableDetail>(`/schemas/${db}/${table}`),
  validate:  (sql: string, database: string) =>
    json<ValidationReport>(`/validate`, { method: "POST", body: JSON.stringify({ sql, database }) }),
  feedback:  (payload: { question: string; sql: string; database: string; was_correct: boolean; comments?: string }) =>
    json<{ ok: boolean }>(`/feedback`, { method: "POST", body: JSON.stringify(payload) }),
};
