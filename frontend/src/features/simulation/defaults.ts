import type { SimulationConfig, SimulationPolicy } from "../../types/api";

// Initial form values match SimulationConfig defaults in the FastAPI model.
// The backend remains authoritative for validation and every submitted run.
export const defaultSimulationConfig: SimulationConfig = {
  seed: 42,
  scenario_id: "stable-default",
  workload: {
    kind: "stable",
    duration_seconds: 600,
    stable_rate_per_second: 60,
    increasing_start_rate_per_second: 30,
    increasing_end_rate_per_second: 150,
    burst_low_rate_per_second: 30,
    burst_high_rate_per_second: 150,
    burst_period_seconds: 60,
    burst_high_duration_seconds: 15,
  },
  servers: [
    {
      server_id: "server-1",
      capacity_slots: 2,
      service_rate_per_slot_per_second: 10,
      routing_weight: 1,
    },
    {
      server_id: "server-2",
      capacity_slots: 4,
      service_rate_per_slot_per_second: 10,
      routing_weight: 1,
    },
    {
      server_id: "server-3",
      capacity_slots: 6,
      service_rate_per_slot_per_second: 10,
      routing_weight: 1,
    },
  ],
  failure_schedule: [],
  warmup_seconds: 60,
  drain_seconds: 60,
  queue_limit_requests: 1000,
  request_deadline_seconds: 30,
  service_demand_distribution: "exponential",
  service_demand_parameters: { mean_work_units: 1 },
};

export const defaultPolicies: SimulationPolicy[] = [
  "round_robin",
  "least_connections",
  "weighted",
];
