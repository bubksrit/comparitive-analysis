import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  SimulationPolicy,
  SimulationResult,
  SimulationRunResultsResponse,
} from "../../types/api";
import { formatPolicyTimingMilliseconds } from "./policyTimingFormat.mjs";

const palette: Record<SimulationPolicy, string> = {
  round_robin: "#52d6bd",
  least_connections: "#77a9ff",
  weighted: "#c99cff",
};

const policyName: Record<SimulationPolicy, string> = {
  round_robin: "Round Robin",
  least_connections: "Least Connections",
  weighted: "Weighted Load Balancing",
};

const latencyFields = [
  ["mean_response_time_seconds", "Mean"],
  ["median_response_time_seconds", "Median"],
  ["p95_latency_seconds", "P95"],
  ["p99_latency_seconds", "P99"],
] as const;

const overheadFields = [
  ["policy_decision_count", "Decision count", "count"],
  ["policy_decision_wall_seconds", "Total overhead (ms)", "time"],
  ["mean_policy_decision_wall_seconds", "Mean (ms)", "time"],
  ["median_policy_decision_wall_seconds", "Median (ms)", "time"],
  ["p95_policy_decision_wall_seconds", "P95 (ms)", "time"],
  ["p99_policy_decision_wall_seconds", "P99 (ms)", "time"],
  ["max_policy_decision_wall_seconds", "Maximum (ms)", "time"],
] as const;

type Props = { data: SimulationRunResultsResponse };

export function ResultsDashboard({ data }: Props) {
  const policies = data.policies;
  const resultsByPolicy = Object.fromEntries(
    policies.map((policy) => [policy, data.results.filter((result) => result.policy === policy)]),
  ) as Record<SimulationPolicy, SimulationResult[]>;
  const latencyData = policies.map((policy) => ({
    policy: policyName[policy],
    mean: summaryMean(data, policy, "mean_response_time_seconds"),
    median: summaryMean(data, policy, "median_response_time_seconds"),
    p95: summaryMean(data, policy, "p95_latency_seconds"),
    p99: summaryMean(data, policy, "p99_latency_seconds"),
  }));
  const throughputData = policies.map((policy) => ({
    policy: policyName[policy],
    throughput: summaryMean(data, policy, "throughput_requests_per_second"),
  }));
  const dropData = policies.map((policy) => ({
    policy: policyName[policy],
    "Queue overflow": average(resultsByPolicy[policy], (result) => result.metrics.queue_overflow_drop_count),
    "Failure drops": average(resultsByPolicy[policy], (result) => result.metrics.failure_drop_count),
    Timeouts: average(resultsByPolicy[policy], (result) => result.metrics.timed_out_request_count),
  }));
  const serverIds = data.configuration.servers.map((server) => server.server_id);
  const utilizationData = serverIds.map((serverId) => ({
    server: serverId,
    ...Object.fromEntries(
      policies.map((policy) => [
        policy,
        average(resultsByPolicy[policy], (result) => result.per_server[serverId]?.utilization_fraction),
      ]),
    ),
  }));
  const distributionData = serverIds.map((serverId) => ({
    server: serverId,
    ...Object.fromEntries(
      policies.map((policy) => [
        policy,
        average(resultsByPolicy[policy], (result) => result.per_server[serverId]?.dispatched_request_count),
      ]),
    ),
  }));

  return (
    <section className="results-section" aria-labelledby="results-title">
      <div className="results-heading">
        <div>
          <p className="eyebrow">Completed experiment</p>
          <h2 id="results-title">Policy comparison</h2>
          <p className="subtle">
            Means across {data.replications} paired replications. Each policy received the same
            generated traffic and failure schedule per replication.
          </p>
        </div>
        <span className="completed-pill"><span className="status-dot" /> Results ready</span>
      </div>

      <div className="provenance-strip">
        <InfoChip label="Scenario" value={data.configuration.scenario_id} />
        <InfoChip label="Master seed" value={String(data.master_seed)} />
        <InfoChip label="Replications" value={String(data.replications)} />
        <InfoChip label="Policy runs" value={String(data.results.length)} />
        <InfoChip label="Replication seeds" value={data.replication_seeds.join(", ")} />
      </div>

      <div className="metric-table-wrap panel">
        <div className="panel-subheading">
          <div><h3>Response time</h3><p>Completed measurement-cohort requests · seconds</p></div>
          <span className="unit-badge">Mean across replications</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Policy</th><th>Mean</th><th>Median</th><th>P95</th><th>P99</th><th>Completed throughput</th></tr>
            </thead>
            <tbody>
              {policies.map((policy) => (
                <tr key={policy}>
                  <td><PolicyLabel policy={policy} /></td>
                  {latencyFields.map(([key]) => (
                    <td key={key}>{formatValue(summaryMean(data, policy, key), "s")}</td>
                  ))}
                  <td>{formatValue(summaryMean(data, policy, "throughput_requests_per_second"), "req/s")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="table-footnote">
          Latency statistics are unavailable when a replication has no completed measurement-cohort
          requests; no missing value is treated as zero.
        </p>
      </div>

      <div className="chart-grid">
        <ChartPanel title="Response-time summary" description="Mean, median and tail latency · seconds">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={latencyData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid stroke="#283448" vertical={false} />
              <XAxis dataKey="policy" tick={{ fill: "#9eabc0", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#77869e", fontSize: 11 }} axisLine={false} tickLine={false} unit="s" />
              <Tooltip contentStyle={tooltipStyle} formatter={(value) => formatValue(value, "s")} />
              <Legend />
              <Bar dataKey="mean" name="Mean" fill="#52d6bd" radius={[4, 4, 0, 0]} />
              <Bar dataKey="median" name="Median" fill="#77a9ff" radius={[4, 4, 0, 0]} />
              <Bar dataKey="p95" name="P95" fill="#c99cff" radius={[4, 4, 0, 0]} />
              <Bar dataKey="p99" name="P99" fill="#ffb86b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Completion throughput" description="Completed cohort requests / measurement second">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={throughputData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid stroke="#283448" vertical={false} />
              <XAxis dataKey="policy" tick={{ fill: "#9eabc0", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#77869e", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} formatter={(value) => formatValue(value, "req/s")} />
              <Bar dataKey="throughput" name="Completed throughput" fill="#52d6bd" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Server utilization" description="Busy service-slot seconds / healthy available slot seconds">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={utilizationData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid stroke="#283448" vertical={false} />
              <XAxis dataKey="server" tick={{ fill: "#9eabc0", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 1]} tick={{ fill: "#77869e", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(value) => `${Math.round(value * 100)}%`} />
              <Tooltip contentStyle={tooltipStyle} formatter={(value) => formatPercent(value)} />
              <Legend />
              {policies.map((policy) => (
                <Bar key={policy} dataKey={policy} name={policyName[policy]} fill={palette[policy]} radius={[4, 4, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Request distribution" description="Mean measurement-cohort dispatches by server">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={distributionData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid stroke="#283448" vertical={false} />
              <XAxis dataKey="server" tick={{ fill: "#9eabc0", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#77869e", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} formatter={(value) => formatValue(value, "requests")} />
              <Legend />
              {policies.map((policy) => (
                <Bar key={policy} dataKey={policy} name={policyName[policy]} fill={palette[policy]} radius={[4, 4, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Request outcomes" description="Mean count per replication · measurement cohort">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={dropData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid stroke="#283448" vertical={false} />
              <XAxis dataKey="policy" tick={{ fill: "#9eabc0", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#77869e", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} formatter={(value) => formatValue(value, "requests")} />
              <Legend />
              <Bar dataKey="Queue overflow" stackId="outcomes" fill="#ffb86b" />
              <Bar dataKey="Failure drops" stackId="outcomes" fill="#ff6d7a" />
              <Bar dataKey="Timeouts" stackId="outcomes" fill="#c99cff" />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <section className="panel imbalance-panel">
          <div className="panel-subheading">
            <div><h3>Load imbalance</h3><p>Coefficient of variation across eligible server utilization</p></div>
          </div>
          <div className="imbalance-list">
            {policies.map((policy) => (
              <div className="imbalance-row" key={policy}>
                <PolicyLabel policy={policy} />
                <strong>{formatValue(summaryMean(data, policy, "load_imbalance_cv"), "")}</strong>
              </div>
            ))}
          </div>
          <div className="proxy-note">
            <span className="proxy-mark">SIM</span>
            <p><strong>Simulated CPU proxy:</strong> occupied-slot fraction from the model. It is not actual hardware CPU usage.</p>
          </div>
        </section>
      </div>

      <div className="panel metric-table-wrap">
        <div className="panel-subheading">
          <div><h3>Per-server request distribution</h3><p>Dispatches and share of all measurement-cohort dispatches</p></div>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Policy</th><th>Server</th><th>Mean dispatch count</th><th>Mean dispatch share</th><th>Mean utilization</th><th>Mean simulated CPU proxy</th></tr></thead>
            <tbody>
              {policies.flatMap((policy) => serverIds.map((serverId) => (
                <tr key={`${policy}-${serverId}`}>
                  <td><PolicyLabel policy={policy} /></td>
                  <td>{serverId}</td>
                  <td>{formatValue(average(resultsByPolicy[policy], (result) => result.per_server[serverId]?.dispatched_request_count), "")}</td>
                  <td>{formatPercent(average(resultsByPolicy[policy], (result) => result.per_server[serverId]?.dispatch_share))}</td>
                  <td>{formatPercent(average(resultsByPolicy[policy], (result) => result.per_server[serverId]?.utilization_fraction))}</td>
                  <td>{formatPercent(average(resultsByPolicy[policy], (result) => result.per_server[serverId]?.simulated_cpu_proxy_fraction))}</td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
        <p className="table-footnote">The CPU proxy is a simulated busy-slot fraction. The application does not measure physical CPU or memory.</p>
      </div>

      <div className="panel metric-table-wrap">
        <div className="panel-subheading">
          <div><h3>Recovery analysis</h3><p>Duration and achieved simulation timestamp are separate from scheduled server recovery.</p></div>
        </div>
        {data.configuration.failure_schedule.length === 0 ? (
          <p className="muted-callout">No failure events were configured for this scenario.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Policy</th><th>Failed server</th><th>Scheduled recovery</th><th>Recovery duration</th><th>Achieved timestamp</th><th>Available replications</th></tr></thead>
              <tbody>
                {policies.flatMap((policy) => data.configuration.failure_schedule.map((failure, index) => {
                  const runs = resultsByPolicy[policy];
                  const durations = runs.map((result) => result.metrics.recovery_time_seconds[index]).filter(isNumber);
                  const timestamps = runs.map((result) => result.metrics.recovery_timestamp_seconds[index]).filter(isNumber);
                  return (
                    <tr key={`${policy}-${index}`}>
                      <td><PolicyLabel policy={policy} /></td>
                      <td>{failure.server_id}</td>
                      <td>{formatValue(failure.recovery_time_seconds, "s")}</td>
                      <td>{formatValue(meanOrNull(durations), "s")}</td>
                      <td>{formatValue(meanOrNull(timestamps), "s")}</td>
                      <td>{durations.length} / {data.replications}</td>
                    </tr>
                  );
                }))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel metric-table-wrap">
        <div className="panel-subheading">
          <div><h3>Policy decision overhead</h3><p>Host wall-clock timing per run, averaged over replications. All timing values are shown in milliseconds.</p></div>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Policy</th>{overheadFields.map(([, label]) => <th key={label}>{label}</th>)}</tr></thead>
            <tbody>
              {policies.map((policy) => (
                <tr key={policy}>
                  <td><PolicyLabel policy={policy} /></td>
                  {overheadFields.map(([key, , kind]) => (
                    <td key={key}>
                      {kind === "count"
                        ? formatValue(summaryMean(data, policy, key), "")
                        : formatPolicyTimingMilliseconds(summaryMean(data, policy, key))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="table-footnote">Timing is measured on the API host and does not advance simulation time or represent server CPU.</p>
      </div>

      <details className="panel details-panel">
        <summary>Run assumptions and provenance</summary>
        <div className="details-content">
          <div><strong>Configuration</strong><pre>{JSON.stringify(data.configuration, null, 2)}</pre></div>
          <div><strong>Assumptions</strong><ul>{data.results[0]?.assumptions.map((item) => <li key={item}>{item}</li>)}</ul></div>
          <div><strong>Bootstrap summary</strong><p>{data.summary.bootstrap_resamples.toLocaleString()} resamples · bootstrap seed {data.summary.bootstrap_seed}</p></div>
        </div>
      </details>
    </section>
  );
}

function ChartPanel({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="panel chart-panel">
      <div className="panel-subheading"><div><h3>{title}</h3><p>{description}</p></div></div>
      <div className="chart-area">{children}</div>
    </section>
  );
}

function PolicyLabel({ policy }: { policy: SimulationPolicy }) {
  return <span className="policy-label"><i style={{ background: palette[policy] }} />{policyName[policy]}</span>;
}

function InfoChip({ label, value }: { label: string; value: string }) {
  return <div className="info-chip"><span>{label}</span><strong>{value || "—"}</strong></div>;
}

function summaryMean(
  data: SimulationRunResultsResponse,
  policy: SimulationPolicy,
  metric: string,
): number | null {
  return data.summary.by_policy[policy]?.[metric]?.mean ?? null;
}

function average(results: SimulationResult[], getValue: (result: SimulationResult) => number | undefined) {
  return meanOrNull(results.map(getValue).filter(isNumber));
}

function meanOrNull(values: number[]): number | null {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function isNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function formatValue(value: unknown, unit: string) {
  if (!isNumber(value as number | null)) return "Unavailable";
  const formatted = new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(value as number);
  return unit ? `${formatted} ${unit}` : formatted;
}

function formatPercent(value: unknown) {
  if (!isNumber(value as number | null)) return "Unavailable";
  return `${((value as number) * 100).toFixed(1)}%`;
}

const tooltipStyle = {
  background: "#111b2a",
  border: "1px solid #344156",
  borderRadius: 10,
  color: "#eaf0f8",
};
