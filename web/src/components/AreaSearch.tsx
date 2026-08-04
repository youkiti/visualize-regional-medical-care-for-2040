import { useMemo, useRef, useState } from 'react';
import type { AreaIndicator } from '../types';

interface AreaSearchProps {
  areas: AreaIndicator[];
  onSelect: (areaCode: string) => void;
}

const MAX_RESULTS = 20;

export default function AreaSearch({ areas, onSelect }: AreaSearchProps) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length === 0) return [];
    return areas
      .filter(
        (a) =>
          a.area_name.toLowerCase().includes(q) ||
          a.pref_name.toLowerCase().includes(q) ||
          a.area_code.includes(q)
      )
      .slice(0, MAX_RESULTS);
  }, [areas, query]);

  const commit = (areaCode: string) => {
    onSelect(areaCode);
    setOpen(false);
    setQuery('');
    setHighlight(0);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || results.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((h) => (h + 1) % results.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) => (h - 1 + results.length) % results.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const picked = results[highlight];
      if (picked) commit(picked.area_code);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className="area-search">
      <label htmlFor="area-search-input" className="visually-hidden">
        区域を検索（区域名・都道府県名・コード）
      </label>
      <input
        id="area-search-input"
        ref={inputRef}
        type="text"
        role="combobox"
        aria-expanded={open && results.length > 0}
        aria-controls="area-search-listbox"
        aria-autocomplete="list"
        placeholder="区域名・都道府県名・コードで検索"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setHighlight(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          // Allow click on a list item to register before closing.
          window.setTimeout(() => setOpen(false), 120);
        }}
        onKeyDown={handleKeyDown}
      />
      {open && query.trim().length > 0 && (
        <ul id="area-search-listbox" role="listbox" className="area-search-list">
          {results.length === 0 ? (
            <li className="area-search-empty">該当する区域がありません</li>
          ) : (
            results.map((a, i) => (
              <li
                key={a.area_code}
                role="option"
                aria-selected={i === highlight}
                onMouseDown={(e) => {
                  // onMouseDown fires before the input's onBlur; prevents
                  // the list from closing before the click registers.
                  e.preventDefault();
                  commit(a.area_code);
                }}
                onMouseEnter={() => setHighlight(i)}
              >
                <span>{a.area_name}</span>
                <span className="pref">
                  {a.pref_name} {a.area_code}
                </span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
