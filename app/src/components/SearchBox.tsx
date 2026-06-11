import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { buildSearchIndex, searchSuburbs } from "../search";
import type { SearchEntry } from "../search";
import type { MetricsArtifact } from "../types";

interface SearchBoxProps {
  artifact: MetricsArtifact;
  onSelect: (entry: SearchEntry) => void;
}

const DEBOUNCE_MS = 120;

export function SearchBox({ artifact, onSelect }: SearchBoxProps) {
  const index = useMemo(() => buildSearchIndex(artifact), [artifact]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchEntry[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Debounced lookup.
  useEffect(() => {
    const t = window.setTimeout(() => {
      setResults(searchSuburbs(index, query));
      setActiveIdx(0);
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [index, query]);

  const showList = open && query.trim() !== "";

  const choose = (entry: SearchEntry) => {
    onSelect(entry);
    setQuery("");
    setOpen(false);
    inputRef.current?.blur();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
      inputRef.current?.blur();
      return;
    }
    if (!showList || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => (i + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => (i - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      const entry = results[activeIdx] ?? results[0];
      if (entry) {
        e.preventDefault();
        choose(entry);
      }
    }
  };

  return (
    <div className="search" role="combobox" aria-expanded={showList} aria-haspopup="listbox">
      <svg className="search-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
        <circle cx="7" cy="7" r="4.6" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="m10.6 10.6 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <input
        ref={inputRef}
        className="search-input"
        type="text"
        placeholder="Search suburbs…"
        value={query}
        spellCheck={false}
        autoComplete="off"
        aria-label="Search suburbs"
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <ul className="panel search-results" role="listbox" aria-label="Suburb matches">
          {results.length === 0 && (
            <li className="search-empty">No suburbs match</li>
          )}
          {results.map((entry, i) => (
            <li key={entry.salCode} role="option" aria-selected={i === activeIdx}>
              <button
                type="button"
                className={`search-result${i === activeIdx ? " is-active" : ""}`}
                // mousedown (not click) so the input's blur doesn't kill the list first
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(entry);
                }}
                onMouseEnter={() => setActiveIdx(i)}
              >
                <span className="search-result-name">{entry.name}</span>
                <span className="search-result-meta">
                  {entry.ambiguous && (
                    <span className="search-result-sal">SAL {entry.salCode}</span>
                  )}
                  <span className="search-result-state">{entry.state}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
