export interface Meta {
  agents?: { name: string; title: string; available: boolean }[]
  version: string
  user: string
  login: boolean
  brand: string
  access?: {
    context_token?: string
    user?: string
    tenant?: { id: string; name?: string }
    capabilities?: { read?: boolean; write?: boolean }
  }
}

export interface Project {
  key: string
  name: string
}

export interface Ticket {
  key: string
  title: string
  status?: string
  assignee?: string
}

export interface Criterion {
  id: string
  text: string
  check: string
}

export interface DevelopmentInfo {
  ticket: string
  state: string
  revision: number
  digest: string
  payload: {
    summary?: string
    design?: string
    test_plan?: string
    criteria?: Criterion[]
    questions?: unknown[]
  }
  work: TeamItem
}

export interface TeamItem {
  ticket: Ticket
  assignment: { assignee: string; reviewer: string; revision: number }
  candidate: CandidateView | null
  candidate_error?: string
  requirement_hash?: string
  can_submit?: boolean
  repository_ready?: boolean
  repository_reason?: string
  state?: string
  can_review?: boolean
  [key: string]: unknown
}

export interface GateFindings {
  tests_added: string[]
  tests_changed: string[]
  tests_deleted: string[]
  gate_files: string[]
  weakening: string[]
  blocking: boolean
  sha256: string
}

export interface VerificationCommand {
  kind?: string
  command?: string
  cmd?: string
  exit_code?: number | null
  output?: string
  tail?: string
}

export interface Verification {
  check?: string
  checked_commit?: string
  checked_base?: string
  commands?: VerificationCommand[]
  baseline_tests?: VerificationCommand[]
  [key: string]: unknown
}

export interface AssessmentResult {
  id: string
  status: string
  evidence?: string
}

export interface ControlPoint {
  name: string
  state: string
  why?: string
}

export interface CandidateView {
  id: number
  ticket: string
  run_id: number
  author: string
  base_commit: string
  commit: string
  ref?: string
  requirement_hash?: string
  criteria: Criterion[]
  summary: string
  current: boolean
  blocked: string[]
  verification: Verification | null
  verification_passed: boolean
  verification_hash: string
  preview: Record<string, unknown> | null
  preview_ready: boolean
  preview_url: string
  assessment: { results?: AssessmentResult[]; author?: string; [key: string]: unknown } | null
  technical_acceptance: boolean
  ready_for_human: boolean
  missing: string[]
  evidence_hash: string
  human_decision: { author?: string; created?: string; note?: string; result?: string } | null
  human_accepted: boolean
  state: string
  gate_findings: GateFindings
  gate_ack: { reason?: string; actor?: string; created?: string; [key: string]: unknown } | null
  control_points: ControlPoint[]
  boundary: string
  recheck?: { running?: boolean; [key: string]: unknown } | null
  [key: string]: unknown
}

export interface ResolveResult {
  base: { name: string; commit: string; resolved: boolean }
  commit: { name: string; commit: string; resolved: boolean }
}

export interface TeamActionResult {
  result: unknown
  item: TeamItem
}

export interface ReportFile {
  name: string
  bytes: number
  sha256: string
}

export interface ReportManifest {
  export_id: string
  files: ReportFile[]
  [key: string]: unknown
}

export interface ReportSegment {
  data_base64: string
  next_offset: number | null
  [key: string]: unknown
}
