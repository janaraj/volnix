import { useState } from 'react';
import { Search } from 'lucide-react';
import { useDebounce } from '@/hooks/use-debounce';
import { DEBOUNCE_MS_SEARCH } from '@/constants/defaults';

// ---------------------------------------------------------------------------
// Filter option data — Record-driven, no if/switch
// ---------------------------------------------------------------------------

const STATUS_OPTIONS: Record<string, string> = {
  '': 'All statuses',
  created: 'Created',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  stopped: 'Stopped',
};

const PRESET_OPTIONS: Record<string, string> = {
  '': 'All presets',
  ideal: 'Ideal',
  messy: 'Messy',
  hostile: 'Hostile',
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export type FilterValues = {
  status: string;
  preset: string;
  tag: string;
};

export const FILTER_DEFAULTS: FilterValues = {
  status: '',
  preset: '',
  tag: '',
};

interface RunFiltersProps {
  filters: FilterValues;
  onChange: (updates: Partial<FilterValues>) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RunFilters({ filters, onChange }: RunFiltersProps) {
  const [tagInput, setTagInput] = useState(filters.tag);
  const debouncedTag = useDebounce(tagInput, DEBOUNCE_MS_SEARCH);

  // Sync debounced value to URL state
  if (debouncedTag !== filters.tag) {
    onChange({ tag: debouncedTag });
  }

  return (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      {/* Status dropdown */}
      <select
        value={filters.status}
        onChange={(e) => onChange({ status: e.target.value })}
        className="rounded-lg border border-border/40 bg-bg-surface px-3 py-1.5 text-sm text-text-primary shadow-xs transition-all duration-200 focus:border-accent/50 focus:outline-none focus:ring-1 focus:ring-accent/30"
      >
        {Object.entries(STATUS_OPTIONS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>

      {/* Reality preset dropdown */}
      <select
        value={filters.preset}
        onChange={(e) => onChange({ preset: e.target.value })}
        className="rounded-lg border border-border/40 bg-bg-surface px-3 py-1.5 text-sm text-text-primary shadow-xs transition-all duration-200 focus:border-accent/50 focus:outline-none focus:ring-1 focus:ring-accent/30"
      >
        {Object.entries(PRESET_OPTIONS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>

      {/* Tag search */}
      <div className="relative">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          type="text"
          placeholder="Search tags..."
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          className="rounded-lg border border-border/40 bg-bg-surface py-1.5 pl-8 pr-3 text-sm text-text-primary shadow-xs transition-all duration-200 placeholder:text-text-muted focus:border-accent/50 focus:outline-none focus:ring-1 focus:ring-accent/30"
        />
      </div>
    </div>
  );
}
