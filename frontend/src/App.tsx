import { useEffect, useState } from 'react'
import { ArrowRight, GitCompareArrows, Loader2, RefreshCw, Sparkles, AlertTriangle } from 'lucide-react'
import VersionCombobox from './components/VersionCombobox'
import ResultView from './components/ResultView'
import { getHealth, getVersions, postDiff, postSummary } from './services/api'
import type { DiffResponse, Health, Version } from './types'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [versions, setVersions] = useState<Version[]>([])
  const [loadingVersions, setLoadingVersions] = useState(true)
  const [versionsError, setVersionsError] = useState<string | null>(null)

  const [source, setSource] = useState('')
  const [destination, setDestination] = useState('')

  const [diff, setDiff] = useState<DiffResponse | null>(null)
  const [comparing, setComparing] = useState(false)
  const [diffError, setDiffError] = useState<string | null>(null)

  const [summary, setSummary] = useState<string | null>(null)
  const [summarizing, setSummarizing] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  const loadVersions = async (refresh = false) => {
    setLoadingVersions(true)
    setVersionsError(null)
    try {
      const res = await getVersions(refresh)
      setVersions(res.versions)
    } catch (e) {
      setVersionsError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoadingVersions(false)
    }
  }

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null))
    loadVersions()
  }, [])

  const compare = async () => {
    if (!source || !destination) return
    setComparing(true)
    setDiffError(null)
    setDiff(null)
    setSummary(null)
    setSummaryError(null)
    try {
      setDiff(await postDiff(source, destination))
    } catch (e) {
      setDiffError(e instanceof Error ? e.message : String(e))
    } finally {
      setComparing(false)
    }
  }

  const summarize = async () => {
    if (!diff) return
    setSummarizing(true)
    setSummaryError(null)
    try {
      const res = await postSummary(diff.source.key, diff.destination.key)
      setSummary(res.summary)
    } catch (e) {
      setSummaryError(e instanceof Error ? e.message : String(e))
    } finally {
      setSummarizing(false)
    }
  }

  const configMissing = health && (!health.confluence_configured || !health.jira_configured)

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
          <GitCompareArrows className="w-6 h-6 text-amelia-400" /> Version Diff
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          What bugs and enhancements were fixed between two OASYS releases — sourced live from the
          release-schedule Confluence page and Jira.
        </p>
      </header>

      {configMissing && (
        <div className="card border-amber-500/40 bg-amber-500/10 mb-4 flex items-start gap-2 text-sm text-amber-200">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>
            Server integrations are not fully configured
            {!health?.confluence_configured && ' · Confluence token missing'}
            {!health?.jira_configured && ' · Jira token missing'}.
            Add them to <code>/opt/amelia-tools/.env</code> and restart the service.
          </span>
        </div>
      )}

      <div className="card">
        <div className="flex items-end gap-3 flex-col sm:flex-row">
          <div className="flex-1 w-full">
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-400 mb-1.5">Source version</label>
            <VersionCombobox
              value={source}
              onChange={setSource}
              versions={versions}
              disabled={loadingVersions || !!versionsError}
              placeholder={loadingVersions ? 'Loading versions…' : 'Select source…'}
            />
          </div>
          <ArrowRight className="w-5 h-5 text-slate-500 shrink-0 mb-2.5 hidden sm:block" />
          <div className="flex-1 w-full">
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-400 mb-1.5">Destination version</label>
            <VersionCombobox
              value={destination}
              onChange={setDestination}
              versions={versions}
              disabled={loadingVersions || !!versionsError}
              placeholder={loadingVersions ? 'Loading versions…' : 'Select destination…'}
            />
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button className="btn-primary inline-flex items-center gap-2" onClick={compare}
                  disabled={!source || !destination || comparing}>
            {comparing ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitCompareArrows className="w-4 h-4" />}
            Compare
          </button>
          <button className="btn-secondary inline-flex items-center gap-2" onClick={() => loadVersions(true)}
                  disabled={loadingVersions} title="Re-pull the version list from Confluence + Jira">
            <RefreshCw className={`w-4 h-4 ${loadingVersions ? 'animate-spin' : ''}`} /> Refresh versions
          </button>
          {versions.length > 0 && <span className="text-xs text-slate-500">{versions.length} versions loaded</span>}
        </div>

        {versionsError && (
          <p className="mt-3 text-sm text-rose-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> {versionsError}
          </p>
        )}
      </div>

      {diffError && (
        <div className="card border-rose-500/40 bg-rose-500/10 mt-4 flex items-start gap-2 text-sm text-rose-200">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" /> {diffError}
        </div>
      )}

      {diff && (
        <div className="mt-6 space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h2 className="text-lg font-semibold text-slate-100">Changes</h2>
            {health?.anthropic_configured && (
              <button className="btn-secondary inline-flex items-center gap-2" onClick={summarize} disabled={summarizing}>
                {summarizing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4 text-amelia-300" />}
                Summarize in English
              </button>
            )}
          </div>

          {summaryError && (
            <div className="card border-amber-500/40 bg-amber-500/10 flex items-start gap-2 text-sm text-amber-200">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" /> {summaryError}
            </div>
          )}
          {summary && (
            <div className="card border-amelia-500/40 bg-amelia-600/10">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-amelia-300 mb-2">
                <Sparkles className="w-3.5 h-3.5" /> AI summary
              </div>
              <div className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">{summary}</div>
            </div>
          )}

          <ResultView diff={diff} />
        </div>
      )}
    </div>
  )
}
