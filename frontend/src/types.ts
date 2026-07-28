export interface Version {
  key: string
  label: string
  oasys_label?: string | null
  jira_version_id?: string | null
  project?: string | null
  section?: string | null
  released: boolean
  release_date?: string | null
  url?: string | null
  order_index?: number
}

export interface Ticket {
  key: string
  summary: string
  status: string
  issuetype: string
  priority: string
  category: 'bug' | 'enhancement' | 'other'
  url: string
}

export interface VersionBucket {
  version: Version
  bugs: Ticket[]
  enhancements: Ticket[]
  other: Ticket[]
  error?: string | null
}

export interface DiffResponse {
  source: Version
  destination: Version
  range_keys: string[]
  buckets: VersionBucket[]
  total_bugs: number
  total_enhancements: number
  total_other: number
}

export interface VersionsResponse {
  versions: Version[]
  count: number
}

export interface Health {
  ok: boolean
  confluence_configured: boolean
  jira_configured: boolean
  anthropic_configured: boolean
  jira_project: string
  release_schedule_page_id: string
}
