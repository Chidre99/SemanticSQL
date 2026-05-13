import { Database } from "lucide-react";
import type { DatabaseInfo } from "../lib/types";

type Props = {
  databases: DatabaseInfo[];
  selected: string;
  onSelect: (db: string) => void;
};

export default function DatabaseSelector({ databases, selected, onSelect }: Props) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <Database size={14} className="text-accent" />
      <select
        value={selected}
        onChange={(e) => onSelect(e.target.value)}
        className="bg-bg-soft border border-bg-soft hover:border-accent-weak rounded-md px-2 py-1
                   text-sm outline-none focus:border-accent focus:ring-1 focus:ring-accent"
      >
        {databases.map((d) => (
          <option key={d.name} value={d.name}>
            {d.name} ({d.dialect}, {d.table_count} tables)
          </option>
        ))}
        {databases.length === 0 && <option>loading…</option>}
      </select>
    </div>
  );
}
