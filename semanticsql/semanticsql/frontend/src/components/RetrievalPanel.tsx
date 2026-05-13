import { useState } from "react";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import type { RetrievalChunk } from "../lib/types";

type Props = { chunks: RetrievalChunk[] };

export default function RetrievalPanel({ chunks }: Props) {
  const [open, setOpen] = useState(false);
  if (!chunks.length) return null;

  return (
    <div className="border border-bg-soft rounded-md bg-bg-soft/40">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider text-ink-muted hover:text-ink"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Search size={12} />
        Retrieved context · {chunks.length} chunks
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-2 max-h-72 overflow-auto">
          {chunks.map((c, i) => (
            <div key={i} className="border border-bg-soft rounded p-2 bg-bg/50">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-ink-muted mb-1">
                <span className="px-1.5 py-0.5 rounded bg-accent/10 text-accent">{c.doc_type}</span>
                <span>{c.table}</span>
                <span className="ml-auto font-mono">{c.score.toFixed(3)}</span>
              </div>
              <pre className="text-[11px] text-ink-muted whitespace-pre-wrap font-mono">{c.text}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
