export type HealthResponse = {
  status: string;
  service: string;
};

export type FeatureAlgorithm = "ga" | "binary_pso" | "aco";

export type FeatureSelectionConfig = {
  algorithm: FeatureAlgorithm;
  seed: number;
  population_size: number;
  max_model_evaluations: number;
  max_iterations: number;
  min_features: number;
  max_features: number | null;
  fitness_performance_weight: number;
  fitness_size_weight: number;
  repeats: number;
};

export type SimulationPolicy =
  | "round_robin"
  | "least_connections"
  | "weighted"
  | "random_forest"
  | "ga"
  | "pso"
  | "aco";

export type SimulationMetrics = {
  mean_response_time_seconds: number | null;
  p95_latency_seconds: number | null;
  p99_latency_seconds: number | null;
  throughput_requests_per_second: number;
  utilization_fraction: number;
  load_imbalance_cv: number;
  dropped_request_count: number;
  timed_out_request_count: number;
  recovery_time_seconds: Array<number | null>;
  policy_decision_wall_seconds: number;
};
