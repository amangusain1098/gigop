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
  rank_position?: number | null
  page_number?: number | null
  is_first_page?: boolean
  search_url?: string
  why_on_page_one?: string[]
  captured_at?: string
}

export interface KeywordScore {
  enabled: boolean
  keyword: string
  score: number
  difficulty: string
  summary: string
  components?: Record<string, number>
}

export interface ScraperLogRecord {
  id: number
  job_id?: string
  keyword?: string
  status: string
  gigs_found?: number | null
  duration_ms?: number | null
  error_msg?: string
  meta_json?: Record<string, any>
  created_at?: string
  updated_at?: string
}

export interface ScraperSummary {
  total_runs: number
  success_rate: number
  failure_rate: number
  avg_duration_ms: number
  last_success_at?: string | null
  last_error?: string
}

export interface ComparisonTimelinePoint {
  id: number
  created_at?: string
  keyword: string
  optimization_score?: number | null
  competitor_count?: number | null
  keyword_score?: number | null
  keyword_difficulty?: string
  top_ranked_title?: string
  top_action?: string
}

export interface ComparisonDiffPayload {
  available: boolean
  summary: string
  left?: Record<string, any>
  right?: Record<string, any>
  changes: Array<{ label: string; before: any; after: any }>
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

export interface DatasetRecord {
  id: string
  gig_id: string
  filename: string
  stored_path: string
  content_type: string
  size_bytes: number
  checksum: string
  source: string
  status: string
  preview: string
  metadata?: Record<string, any>
  created_at?: string
  updated_at?: string
}

export interface FailedLoginAttemptRecord {
  id: string
  username: string
  remote_addr: string
  user_agent: string
  failure_count: number
  capture_required: boolean
  capture_status: string
  capture_error?: string
  photo_available?: boolean
  photo_url?: string
  created_at?: string
  photo_captured_at?: string
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
  scraper_logs?: ScraperLogRecord[]
  scraper_summary?: ScraperSummary
  timeline?: ComparisonTimelinePoint[]
  comparison_diff?: ComparisonDiffPayload
  datasets?: DatasetRecord[]
  memory?: Record<string, any>
  assistant_history?: Array<Record<string, any>>
  hostinger?: Record<string, any>
  security?: {
    capture_threshold: number
    failed_login_attempts: FailedLoginAttemptRecord[]
  }
  extension_install?: {
    enabled: boolean
    installed?: boolean
    download_url: string
    guide_url: string
    token_configured: boolean
    api_token?: string
    api_base_url?: string
    source_dir_present?: boolean
  }
  workers: WorkerSnapshot
  health: HealthPayload
  queued_job?: JobRun
}

export interface DashboardEvent {
  type: string
  payload: any
}
