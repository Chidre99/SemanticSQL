import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import type { Status } from "../lib/types";

const STEPS: { key: Status; label: string }[] = [
  { key: "retrieving", label: "Retrieve" },
  { key: "generating", label: "Generate" },
  { key: "validating", label: "Validate" },
  { key: "executing",  label: "Execute" },
];

// Pipeline order for "has passed" comparisons.
const ORDER: Status[] = ["idle", "retrieving", "generating", "retrying", "validating", "executing", "done", "error"];

type Props = {
  status: Status;
  attempt: number;
};

export default function StatusBar({ status, attempt }: Props) {
  const currentIdx = ORDER.indexOf(status);
  return (
    <div className="flex items-center gap-1 text-xs">
      {STEPS.map((step, i) => {
        const stepIdx = ORDER.indexOf(step.key);
        const active = step.key === status || (status === "retrying" && step.key === "generating");
        const passed = status === "done" || (currentIdx > stepIdx && stepIdx >= 0);
        const errored = status === "error" && active;
        return (
          <div key={step.key} className="flex items-center">
            <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md
              ${active ? "bg-accent/10 text-accent" : passed ? "text-ok" : errored ? "text-err" : "text-ink-faint"}`}>
              {errored ? <XCircle size={12} /> :
               active  ? <Loader2 size={12} className="animate-spin" /> :
               passed  ? <CheckCircle2 size={12} /> :
                         <Circle size={12} />}
              <span>{step.label}</span>
              {step.key === "generating" && attempt > 0 && active && (
                <span className="text-warn">·retry {attempt}</span>
              )}
            </div>
            {i < STEPS.length - 1 && <div className="w-3 h-px bg-bg-soft" />}
          </div>
        );
      })}
    </div>
  );
}
