import { useEffect, useRef } from "react";
import { Play, Square } from "lucide-react";

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onAbort: () => void;
  isRunning: boolean;
  disabled?: boolean;
};

export default function QueryInput({ value, onChange, onSubmit, onAbort, isRunning, disabled }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto-grow up to 6 lines
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 6 * 24 + 16) + "px";
  }, [value]);

  return (
    <div className="flex flex-col gap-2">
      <textarea
        ref={ref}
        rows={2}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.preventDefault();
            if (!isRunning && value.trim()) onSubmit();
          }
        }}
        disabled={disabled}
        placeholder="Ask a question in plain English — e.g. 'Top 10 customers by total spend in 2022'"
        className="w-full resize-none bg-bg-soft border border-bg-soft hover:border-accent-weak focus:border-accent
                   focus:ring-1 focus:ring-accent rounded-md px-3 py-2 text-sm
                   placeholder:text-ink-faint outline-none transition-colors"
      />
      <div className="flex items-center justify-between text-xs text-ink-muted">
        <span>⌘/Ctrl + Enter to submit</span>
        {isRunning ? (
          <button
            onClick={onAbort}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-err/10 text-err border border-err/30 hover:bg-err/20"
          >
            <Square size={14} /> Stop
          </button>
        ) : (
          <button
            onClick={onSubmit}
            disabled={disabled || !value.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent/10 text-accent border border-accent/30 hover:bg-accent/20 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Play size={14} /> Run
          </button>
        )}
      </div>
    </div>
  );
}
