export interface AuthState {
  enabled: boolean
  authenticated: boolean
  username: string
  csrf_token: string
}

export interface MetricHistoryPoint {
  timestamp: string
  impressions: number
  clicks: number
  orders: number
  ctr: number
  conversion_rate: number
}

export interface AgentHealth {
  agent_name: string
  status: string
  last_run_at?: string | null
  last_error?: string
  cost_per_run?: number
}

export interface QueueRecord {
  id: string
  agent_name: string
  action_type: string
  current_value: string
  proposed_value: string
  confidence_score: number
  validator_issues: Array<{ code: string; message: string; severity?: string }>
  status: string
  created_at?: string
  reviewed_at?: string | null
  reviewer_notes?: string
}

export interface JobRun {
  run_id: string
  job_id?: string | null
  run_type: string
  status: string
  current_agent?: string | null
  current_stage?: string | null
  progress: number
  input_payload?: Record<string, unknown>
  result_payload?: Record<string, unknown>
  error_message?: string
  output_summary?: string
  created_at?: string
  started_at?: string | null
  finished_at?: string | null
}

export interface CompetitorRecord {
  id?: number
  run_id?: string | null
  source?: string
  url: string
  title: string
  seller_name: string
  starting_price?: number | null
  rating?: number | null
  reviews_count?: number | null
  delivery_days?: number | null
  badges?: string[]
  snippet?: string
  matched_term?: string
  conversion_proxy_score?: number
  win_reasons?: string[]
  captured_at?: string
}

export interface LegacyState {
  snapshot_path: string
  latest_report: Record<string, any> | null
  gig_comparison: Record<string, any> | null
  comparison_history: Array<Record<string, any>>
  metrics_history: MetricHistoryPoint[]
  agent_health: AgentHealth[]
  recent_reports: Array<Record<string, any>>
  scraper_run: Record<string, any>
  queue: QueueRecord[]
  connector_status: Array<Record<string, any>>
  setup_health: Record<string, any>
  notifications?: Record<string, any>
  auth: AuthState
  security_warnings?: string[]
}

export interface WorkerSnapshot {
  backend: string
  mode: string
  detail: string
  local_threads: number
}

export interface HealthPayload {
  status: string
  app: string
  version: string
  auth_enabled: boolean
  scheduler_status: string
  components: Record<string, any>
}

export interface BootstrapPayload {
  state: LegacyState
  job_runs: JobRun[]
  queue: QueueRecord[]
  competitors: CompetitorRecord[]
  workers: WorkerSnapshot
  health: HealthPayload
  queued_job?: JobRun
}

export interface DashboardEvent {
  type: string
  payload: any
}
