import type { Dispatch, SetStateAction } from "react";
import type {
  FailureEvent,
  ServerConfig,
  SimulationConfig,
  SimulationPolicy,
  WorkloadConfig,
  WorkloadKind,
} from "../../types/api";

const policyOptions: Array<{ id: SimulationPolicy; name: string; note: string }> = [
  { id: "round_robin", name: "Round Robin", note: "Rotate through eligible servers" },
  {
    id: "least_connections",
    name: "Least Connections",
    note: "Choose the eligible server with fewest active requests",
  },
  {
    id: "weighted",
    name: "Weighted Load Balancing",
    note: "Capacity-aware outstanding workload",
  },
];

type Props = {
  config: SimulationConfig;
  setConfig: Dispatch<SetStateAction<SimulationConfig>>;
  policies: SimulationPolicy[];
  setPolicies: Dispatch<SetStateAction<SimulationPolicy[]>>;
  replications: number;
  setReplications: (value: number) => void;
  busy: boolean;
  onSubmit: () => void;
};

export function ConfigurationPanel({
  config,
  setConfig,
  policies,
  setPolicies,
  replications,
  setReplications,
  busy,
  onSubmit,
}: Props) {
  const setRoot = <K extends keyof SimulationConfig>(key: K, value: SimulationConfig[K]) =>
    setConfig((current) => ({ ...current, [key]: value }));
  const setWorkload = <K extends keyof WorkloadConfig>(key: K, value: WorkloadConfig[K]) =>
    setConfig((current) => ({ ...current, workload: { ...current.workload, [key]: value } }));
  const setFailure = <K extends keyof FailureEvent>(key: K, value: FailureEvent[K]) => {
    const current = config.failure_schedule[0];
    if (current) setRoot("failure_schedule", [{ ...current, [key]: value }]);
  };
  const updateServer = <K extends keyof ServerConfig>(
    index: number,
    key: K,
    value: ServerConfig[K],
  ) => {
    setRoot(
      "servers",
      config.servers.map((server, serverIndex) =>
        serverIndex === index ? { ...server, [key]: value } : server,
      ),
    );
  };

  const togglePolicy = (policy: SimulationPolicy) => {
    setPolicies((current) =>
      current.includes(policy) ? current.filter((item) => item !== policy) : [...current, policy],
    );
  };

  const toggleFailure = (enabled: boolean) => {
    setRoot(
      "failure_schedule",
      enabled
        ? [
            {
              server_id: config.servers[1]?.server_id ?? config.servers[0]?.server_id ?? "server-1",
              failure_time_seconds: 300,
              recovery_time_seconds: 360,
            },
          ]
        : [],
    );
  };

  return (
    <section className="panel config-panel" aria-labelledby="configuration-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Experiment setup</p>
          <h2 id="configuration-title">Simulation configuration</h2>
          <p className="subtle">Tune paired traffic, servers, failures and policy selection.</p>
        </div>
        <span className="section-index">01</span>
      </div>

      <div className="form-section">
        <div className="section-title-row">
          <h3>Traffic scenario</h3>
          <span className="hint">Arrivals are generated once per replication and shared across policies.</span>
        </div>
        <div className="field-grid field-grid-three">
          <Field label="Traffic pattern">
            <select
              value={config.workload.kind}
              onChange={(event) => setWorkload("kind", event.target.value as WorkloadKind)}
            >
              <option value="stable">Stable</option>
              <option value="increasing">Increasing</option>
              <option value="bursty">Bursty</option>
            </select>
          </Field>
          <NumberField
            label="Arrival horizon"
            suffix="seconds"
            value={config.workload.duration_seconds}
            onChange={(value) => setWorkload("duration_seconds", value)}
          />
          <Field label="Scenario ID">
            <input
              value={config.scenario_id}
              onChange={(event) => setRoot("scenario_id", event.target.value)}
              placeholder="stable-default"
            />
          </Field>
        </div>

        {config.workload.kind === "stable" && (
          <div className="field-grid field-grid-three scenario-fields">
            <NumberField
              label="Arrival rate"
              suffix="requests / second"
              value={config.workload.stable_rate_per_second}
              onChange={(value) => setWorkload("stable_rate_per_second", value)}
            />
          </div>
        )}
        {config.workload.kind === "increasing" && (
          <div className="field-grid field-grid-three scenario-fields">
            <NumberField
              label="Starting arrival rate"
              suffix="requests / second"
              value={config.workload.increasing_start_rate_per_second}
              onChange={(value) => setWorkload("increasing_start_rate_per_second", value)}
            />
            <NumberField
              label="Ending arrival rate"
              suffix="requests / second"
              value={config.workload.increasing_end_rate_per_second}
              onChange={(value) => setWorkload("increasing_end_rate_per_second", value)}
            />
            <div className="field-note">
              Linear ramp across the full arrival horizon. Approved default: 30 → 150 requests/s
              over 600 seconds.
            </div>
          </div>
        )}
        {config.workload.kind === "bursty" && (
          <div className="field-grid field-grid-three scenario-fields">
            <NumberField
              label="Low-rate period"
              suffix="requests / second"
              value={config.workload.burst_low_rate_per_second}
              onChange={(value) => setWorkload("burst_low_rate_per_second", value)}
            />
            <NumberField
              label="High-rate period"
              suffix="requests / second"
              value={config.workload.burst_high_rate_per_second}
              onChange={(value) => setWorkload("burst_high_rate_per_second", value)}
            />
            <NumberField
              label="Cycle length"
              suffix="seconds"
              value={config.workload.burst_period_seconds}
              onChange={(value) => setWorkload("burst_period_seconds", value)}
            />
            <NumberField
              label="High-rate duration"
              suffix="seconds"
              value={config.workload.burst_high_duration_seconds}
              onChange={(value) => setWorkload("burst_high_duration_seconds", value)}
            />
          </div>
        )}
      </div>

      <div className="form-section">
        <div className="section-title-row">
          <h3>Server fleet</h3>
          <button
            className="text-button"
            type="button"
            onClick={() =>
              setRoot("servers", [
                ...config.servers,
                {
                  server_id: `server-${config.servers.length + 1}`,
                  capacity_slots: 2,
                  service_rate_per_slot_per_second: 10,
                  routing_weight: 1,
                },
              ])
            }
          >
            + Add server
          </button>
        </div>
        <div className="server-list">
          {config.servers.map((server, index) => (
            <div className="server-row" key={`${index}-${server.server_id}`}>
              <div className="server-identity">
                <span className="server-dot" />
                <input
                  aria-label={`Server ${index + 1} ID`}
                  value={server.server_id}
                  onChange={(event) => updateServer(index, "server_id", event.target.value)}
                />
              </div>
              <NumberField
                label="Service slots"
                value={server.capacity_slots}
                onChange={(value) => updateServer(index, "capacity_slots", value)}
              />
              <NumberField
                label="Rate per slot"
                suffix="work units/s"
                value={server.service_rate_per_slot_per_second}
                onChange={(value) =>
                  updateServer(index, "service_rate_per_slot_per_second", value)
                }
              />
              <div className="capacity-readout">
                <span>Effective capacity</span>
                <strong>
                  {formatNumber(
                    server.capacity_slots * server.service_rate_per_slot_per_second,
                  )}{" "}
                  <small>work units/s</small>
                </strong>
              </div>
              <button
                aria-label={`Remove ${server.server_id}`}
                className="icon-button remove-button"
                type="button"
                onClick={() => setRoot("servers", config.servers.filter((_, i) => i !== index))}
                title="Remove server"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="form-section">
        <div className="section-title-row">
          <h3>Failure scenario</h3>
          <label className="switch-label">
            <input
              type="checkbox"
              checked={config.failure_schedule.length > 0}
              onChange={(event) => toggleFailure(event.target.checked)}
            />
            <span>{config.failure_schedule.length ? "Enabled" : "No failures"}</span>
          </label>
        </div>
        {config.failure_schedule[0] ? (
          <div className="field-grid field-grid-three">
            <Field label="Target server">
              <select
                value={config.failure_schedule[0].server_id}
                onChange={(event) => setFailure("server_id", event.target.value)}
              >
                {config.servers.map((server) => (
                  <option key={server.server_id} value={server.server_id}>
                    {server.server_id}
                  </option>
                ))}
              </select>
            </Field>
            <NumberField
              label="Failure timestamp"
              suffix="seconds from start"
              value={config.failure_schedule[0].failure_time_seconds}
              onChange={(value) => setFailure("failure_time_seconds", value)}
            />
            <NumberField
              label="Recovery timestamp"
              suffix="seconds from start"
              value={config.failure_schedule[0].recovery_time_seconds}
              onChange={(value) => setFailure("recovery_time_seconds", value)}
            />
            <p className="hint field-span-all">
              The selected server’s in-flight requests are dropped at failure. Queued requests
              remain in order and the server returns idle at recovery.
            </p>
          </div>
        ) : (
          <p className="muted-callout">Default experiment has no server failures.</p>
        )}
      </div>

      <div className="form-section">
        <div className="section-title-row">
          <h3>Comparison settings</h3>
          <span className="hint">All selected policies use paired traces.</span>
        </div>
        <div className="field-grid field-grid-three">
          <NumberField
            label="Random seed"
            value={config.seed}
            onChange={(value) => setRoot("seed", value)}
          />
          <NumberField
            label="Replications"
            value={replications}
            onChange={setReplications}
          />
          <div className="field-note">
            Warm-up {config.warmup_seconds}s · measure after warm-up · drain {config.drain_seconds}s
          </div>
        </div>
        <div className="policy-options">
          {policyOptions.map((policy) => (
            <label className={`policy-option ${policies.includes(policy.id) ? "selected" : ""}`} key={policy.id}>
              <input
                type="checkbox"
                checked={policies.includes(policy.id)}
                onChange={() => togglePolicy(policy.id)}
              />
              <span className="policy-check" aria-hidden="true">✓</span>
              <span>
                <strong>{policy.name}</strong>
                <small>{policy.note}</small>
              </span>
            </label>
          ))}
        </div>
      </div>

      <div className="config-footer">
        <p>Backend validation is authoritative. Invalid settings will be returned with field details.</p>
        <button className="primary-button" disabled={busy} onClick={onSubmit} type="button">
          {busy ? <span className="spinner" /> : <PlayIcon />}
          {busy ? "Starting run…" : "Run paired comparison"}
        </button>
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function NumberField({
  label,
  suffix,
  value,
  onChange,
}: {
  label: string;
  suffix?: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label}>
      <span className="input-with-suffix">
        <input
          type="number"
          step="any"
          value={Number.isFinite(value) ? value : ""}
          onChange={(event) => onChange(event.target.value === "" ? 0 : Number(event.target.value))}
        />
        {suffix && <small>{suffix}</small>}
      </span>
    </Field>
  );
}

function PlayIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" fill="currentColor" className="button-icon">
      <path d="M4.25 2.5a.75.75 0 0 1 1.12-.65l7 5a.75.75 0 0 1 0 1.3l-7 5A.75.75 0 0 1 4.25 12.5z" />
    </svg>
  );
}

function formatNumber(value: number) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
}
