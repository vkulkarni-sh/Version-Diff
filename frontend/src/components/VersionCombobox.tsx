import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown, Check } from 'lucide-react'
import type { Version } from '../types'

// Searchable version picker. The dropdown list is rendered into document.body
// via a portal and positioned with getBoundingClientRect — the hard-won lesson
// from the Latency Analyser: an absolutely-positioned list gets clipped by any
// ancestor's overflow and looks like "missing items". Portaling side-steps that.
interface Props {
  value: string
  onChange: (key: string) => void
  versions: Version[]
  placeholder?: string
  disabled?: boolean
}

function labelFor(v: Version): string {
  const oasys = v.oasys_label ? ` · ${v.oasys_label}` : ''
  return `${v.label}${oasys}`
}

export default function VersionCombobox({ value, onChange, versions, placeholder, disabled }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const btnRef = useRef<HTMLButtonElement>(null)
  const popRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [rect, setRect] = useState<{ left: number; top: number; width: number } | null>(null)

  const selected = versions.find(v => v.key === value)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return versions
    return versions.filter(v =>
      labelFor(v).toLowerCase().includes(q) || (v.section ?? '').toLowerCase().includes(q),
    )
  }, [versions, query])

  const reposition = () => {
    const r = btnRef.current?.getBoundingClientRect()
    if (r) setRect({ left: r.left, top: r.bottom + 4, width: r.width })
  }

  useLayoutEffect(() => { if (open) reposition() }, [open])

  useEffect(() => {
    if (!open) return
    const onScrollResize = () => reposition()
    const onClick = (e: MouseEvent) => {
      const t = e.target as Node
      if (btnRef.current?.contains(t) || popRef.current?.contains(t)) return
      setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('scroll', onScrollResize, true)
    window.addEventListener('resize', onScrollResize)
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('scroll', onScrollResize, true)
      window.removeEventListener('resize', onScrollResize)
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  useEffect(() => {
    if (open) {
      setQuery('')
      setHighlight(0)
      requestAnimationFrame(() => searchRef.current?.focus())
    }
  }, [open])

  useEffect(() => {
    if (!open || !listRef.current) return
    listRef.current.querySelector<HTMLElement>(`[data-idx="${highlight}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [highlight, open])

  const pick = (key: string) => { onChange(key); setOpen(false) }

  const onSearchKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setHighlight(h => Math.min(filtered.length - 1, h + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight(h => Math.max(0, h - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); if (filtered[highlight]) pick(filtered[highlight].key) }
  }

  return (
    <div className="relative">
      <button
        ref={btnRef}
        type="button"
        disabled={disabled}
        onClick={() => setOpen(o => !o)}
        className="input flex items-center justify-between gap-2 text-left w-full disabled:opacity-50 disabled:cursor-not-allowed"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className={selected ? 'truncate text-slate-100' : 'truncate text-slate-500'}>
          {selected ? labelFor(selected) : (placeholder || 'Select a version…')}
        </span>
        <ChevronDown className={`w-4 h-4 text-slate-400 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && rect && createPortal(
        <div
          ref={popRef}
          style={{ position: 'fixed', left: rect.left, top: rect.top, width: rect.width, zIndex: 1000 }}
          className="rounded-lg border border-slate-700 bg-slate-900 shadow-xl shadow-black/50 overflow-hidden"
          role="listbox"
        >
          <div className="p-2 border-b border-slate-700/70 bg-slate-900/95">
            <input
              ref={searchRef}
              value={query}
              onChange={e => { setQuery(e.target.value); setHighlight(0) }}
              onKeyDown={onSearchKey}
              placeholder={`Search ${versions.length} versions…`}
              className="w-full bg-slate-800/80 border border-slate-700 rounded px-2.5 py-1.5 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-amelia-500/60"
            />
          </div>
          <div ref={listRef} className="max-h-80 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <div className="px-3 py-2 text-xs text-slate-500 italic">No versions match “{query}”.</div>
            ) : filtered.map((v, idx) => {
              const isSel = v.key === value
              const active = idx === highlight
              return (
                <button
                  type="button"
                  key={v.key}
                  data-idx={idx}
                  onMouseEnter={() => setHighlight(idx)}
                  onClick={() => pick(v.key)}
                  className={`flex items-center justify-between w-full text-left px-3 py-1.5 text-sm transition-colors ${
                    isSel ? 'bg-amelia-500/20 text-amelia-100'
                      : active ? 'bg-slate-700/60 text-slate-100' : 'text-slate-200 hover:bg-slate-800/80'
                  }`}
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{labelFor(v)}</span>
                    <span className="block truncate text-[11px] text-slate-500">
                      {v.section || v.project}{v.release_date ? ` · ${v.release_date}` : v.released ? '' : ' · unreleased'}
                    </span>
                  </span>
                  {isSel && <Check className="w-3.5 h-3.5 text-amelia-300 shrink-0 ml-2" />}
                </button>
              )
            })}
          </div>
          <div className="px-3 py-1.5 text-[10.5px] text-slate-500 border-t border-slate-700/70 bg-slate-950/50">
            {filtered.length} of {versions.length} · ↑↓ navigate · Enter select · Esc close
          </div>
        </div>,
        document.body,
      )}
    </div>
  )
}
