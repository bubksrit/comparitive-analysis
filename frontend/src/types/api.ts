export type HealthResponse = {
  status: string;
  service: string;
};

export type SimulationPolicy = "round_robin" | "least_connections" | "weighted";
export type WorkloadKind = "stable" | "increasing" | "bursty";
export type RunStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelling"
  | "cancelled";

export type ServerConfig = {
  server_id: string;
  capacity_slots: number;
  service_rate_per_slot_per_second: number;
  routing_weight: number;
};

export type FailureEvent = {
  server_id: string;
  failure_time_seconds: number;
  recovery_time_seconds: number;
};

export type WorkloadConfig = {
  kind: WorkloadKind;
  duration_seconds: number;
  stable_rate_per_second: number;
  increasing_start_rate_per_second: number;
  increasing_end_rate_per_second: number;
  burst_low_rate_per_second: number;
  burst_high_rate_per_second: number;
  burst_period_seconds: number;
  burst_high_duration_seconds: number;
};

export type SimulationConfig = {
  seed: number;
  scenario_id: string;
  workload: WorkloadConfig;
  servers: ServerConfig[];
  failure_schedule: FailureEvent[];
  warmup_seconds: number;
  drain_seconds: number;
  queue_limit_requests: number;
  request_deadline_seconds: number;
  service_demand_distribution: "exponential" | "deterministic";
  service_demand_parameters: { mean_work_units: number };
};

export type SimulationRunRequest = SimulationConfig & {
  policies: SimulationPolicy[];
  replications: number;
};

export type SimulationRunProgress = {
  completed_replications: number;
  total_replications: number;
  completed_policy_runs: number;
  total_policy_runs: number;
};

export type SimulationRunError = {
  code: string;
  message: string;
};

export type SimulationRunStatusResponse = {
  run_id: string;
  status: RunStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  progress: SimulationRunProgress;
  error: SimulationRunError | null;
};

export type RunMetadata = {
  experiment_id: string;
  seed: number;
  created_at: string;
  code_revision: string | null;
  software_versions: Record<string, string>;
  hardware_description: string | null;
};

export type SimulationMetrics = {
  mean_response_time_seconds: number | null;
  median_response_time_seconds: number | null;
  p95_latency_seconds: number | null;
  p99_latency_seconds: number | null;
  throughput_requests_per_second: number;
  utilization_fraction: number;
  simulated_cpu_proxy_fraction: number;
  load_imbalance_cv: number | null;
  offered_request_count: number;
  completed_request_count: number;
  queue_overflow_drop_count: number;
  failure_drop_count: number;
  dropped_request_count: number;
  timed_out_request_count: number;
  queue_overflow_drop_rate: number;
  failure_drop_rate: number;
  timed_out_request_rate: number;
  total_request_loss_rate: number;
  recovery_time_seconds: Array<number | null>;
  recovery_timestamp_seconds: Array<number | null>;
  recovery_unavailable_reasons: Array<string | null>;
  policy_decision_count: number;
  policy_decision_wall_seconds: number;
  mean_policy_decision_wall_seconds: number;
  median_policy_decision_wall_seconds: number;
  p95_policy_decision_wall_seconds: number;
  p99_policy_decision_wall_seconds: number;
  max_policy_decision_wall_seconds: number;
};

export type ServerSimulationMetrics = {
  utilization_fraction: number;
  simulated_cpu_proxy_fraction: number;
  healthy_available_seconds: number;
  unavailable_seconds: number;
  dispatched_request_count: number;
  completed_request_count: number;
  dispatch_share: number;
};

export type SimulationSnapshot = {
  time_seconds: number;
  server_health: Record<string, boolean>;
  active_requests_by_server: Record<string, number>;
  shared_queue_depth: number;
};

export type SimulationResult = {
  metadata: RunMetadata;
  study_label: "simulated load balancing";
  policy: SimulationPolicy;
  scenario_id: string;
  trace_seed: number;
  configuration: SimulationConfig;
  metrics: SimulationMetrics;
  per_server: Record<string, ServerSimulationMetrics>;
  snapshots: SimulationSnapshot[];
  assumptions: string[];
};

export type MetricEstimate = {
  mean: number | null;
  standard_deviation: number | null;
  confidence_interval_95: [number, number] | null;
  sample_count: number;
};

export type ComparisonSummary = {
  by_policy: Record<string, Record<string, MetricEstimate>>;
  paired_mean_differences: Record<string, Record<string, MetricEstimate>>;
  bootstrap_resamples: number;
  bootstrap_seed: number;
};

export type SimulationRunResultsResponse = {
  run_id: string;
  status: "completed";
  master_seed: number;
  replication_seeds: number[];
  replications: number;
  policies: SimulationPolicy[];
  configuration: SimulationConfig;
  results: SimulationResult[];
  summary: ComparisonSummary;
  metric_definitions: Record<string, string>;
};
