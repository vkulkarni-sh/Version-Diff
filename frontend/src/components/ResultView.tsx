import { AlertTriangle, Bug, Sparkles, ExternalLink } from 'lucide-react'
import type { DiffResponse, Ticket, VersionBucket } from '../types'

function statusBadge(status: string): string {
  const s = status.toLowerCase()
  if (s === 'done' || s === 'closed' || s === 'resolved' || s === 'released')
    return 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/25'
  if (s === 'in progress' || s === 'in review')
    return 'bg-amber-500/15 text-amber-300 border border-amber-500/25'
  return 'bg-slate-600/25 text-slate-300 border border-slate-500/25'
}

function TicketRow({ t }: { t: Ticket }) {
  return (
    <li className="flex items-start gap-3 py-1.5 border-b border-slate-800/60 last:border-0">
      <a
        href={t.url}
        target="_blank"
        rel="noopener noreferrer"
        className="shrink-0 font-mono text-[12.5px] text-amelia-300 hover:text-amelia-200 hover:underline inline-flex items-center gap-1"
        title="Open in Jira"
      >
        {t.key}<ExternalLink className="w-3 h-3 opacity-70" />
      </a>
      <span className="flex-1 text-sm text-slate-200 leading-snug">{t.summary}</span>
      <span className={`badge shrink-0 ${statusBadge(t.status)}`}>{t.status || '—'}</span>
    </li>
  )
}

function Group({ title, icon, tickets, tone }: {
  title: string; icon: React.ReactNode; tickets: Ticket[]; tone: string
}) {
  if (tickets.length === 0) return null
  return (
    <div className="mt-3 first:mt-0">
      <div className={`flex items-center gap-2 text-xs font-semibold uppercase tracking-wide ${tone}`}>
        {icon}{title}<span className="text-slate-500 font-normal">· {tickets.length}</span>
      </div>
      <ul className="mt-1.5">
        {tickets.map(t => <TicketRow key={t.key} t={t} />)}
      </ul>
    </div>
  )
}

function VersionSection({ b }: { b: VersionBucket }) {
  const v = b.version
  const empty = b.bugs.length + b.enhancements.length + b.other.length === 0
  return (
    <div className="card">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h3 className="text-base font-semibold text-slate-100">
          {v.url ? (
            <a href={v.url} target="_blank" rel="noopener noreferrer" className="hover:text-amelia-200 hover:underline inline-flex items-center gap-1">
              {v.label}<ExternalLink className="w-3.5 h-3.5 opacity-70" />
            </a>
          ) : v.label}
          {v.oasys_label && <span className="ml-2 text-sm font-normal text-amelia-300">{v.oasys_label}</span>}
        </h3>
        <span className="text-xs text-slate-500">
          {v.section}{v.release_date ? ` · released ${v.release_date}` : v.released ? '' : ' · unreleased'}
        </span>
      </div>

      {b.error ? (
        <div className="mt-2 flex items-center gap-2 text-sm text-amber-300">
          <AlertTriangle className="w-4 h-4" /> Could not load tickets: {b.error}
        </div>
      ) : empty ? (
        <div className="mt-2 text-sm text-slate-500 italic">No bugs or enhancements recorded for this version.</div>
      ) : (
        <>
          <Group title="Bugs" tone="text-rose-300" icon={<Bug className="w-3.5 h-3.5" />} tickets={b.bugs} />
          <Group title="Enhancements" tone="text-emerald-300" icon={<Sparkles className="w-3.5 h-3.5" />} tickets={b.enhancements} />
          <Group title="Other" tone="text-slate-400" icon={<span className="w-3.5 h-3.5 inline-block" />} tickets={b.other} />
        </>
      )}
    </div>
  )
}

export default function ResultView({ diff }: { diff: DiffResponse }) {
  return (
    <div className="space-y-4">
      <div className="card bg-amelia-600/10 border-amelia-500/30">
        <p className="text-sm text-slate-300">
          Upgrading from{' '}
          <span className="font-semibold text-slate-100">{diff.source.label}</span> to{' '}
          <span className="font-semibold text-slate-100">{diff.destination.label}</span>{' '}
          spans <span className="font-semibold text-amelia-200">{diff.range_keys.length}</span> version(s):
        </p>
        <div className="mt-2 flex flex-wrap gap-4 text-sm">
          <span className="text-rose-300"><b>{diff.total_bugs}</b> bugs</span>
          <span className="text-emerald-300"><b>{diff.total_enhancements}</b> enhancements</span>
          {diff.total_other > 0 && <span className="text-slate-400"><b>{diff.total_other}</b> other</span>}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
          <span className="uppercase tracking-wide text-slate-500 mr-0.5">Versions:</span>
          {diff.buckets.map((b, i) => (
            <span key={b.version.key} className="inline-flex items-center gap-1.5">
              <span className="px-1.5 py-0.5 rounded bg-slate-800/70 border border-slate-700 text-slate-200 font-medium">
                {b.version.label}
              </span>
              {i < diff.buckets.length - 1 && <span className="text-slate-600">→</span>}
            </span>
          ))}
        </div>
      </div>

      {diff.buckets.map(b => <VersionSection key={b.version.key} b={b} />)}
    </div>
  )
}
