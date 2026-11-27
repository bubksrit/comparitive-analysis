import { useEffect, useState } from "react";
import { ConfigurationPanel } from "./features/simulation/ConfigurationPanel";
import { defaultPolicies, defaultSimulationConfig } from "./features/simulation/defaults";
import { ResultsDashboard } from "./features/simulation/ResultsDashboard";
import { RunLifecyclePanel } from "./features/simulation/RunLifecyclePanel";
import { useSimulationRun } from "./features/simulation/useSimulationRun";
import { simulationApi } from "./services/simulationApi";
import type { HealthResponse, SimulationConfig, SimulationPolicy } from "./types/api";

type ApiHealth = "checking" | "online" | "offline";

export default function App() {
  const [health, setHealth] = useState<ApiHealth>("checking");
  const [config, setConfig] = useState<SimulationConfig>(() => structuredClone(defaultSimulationConfig));
  const [policies, setPolicies] = useState<SimulationPolicy[]>([...defaultPolicies]);
  const [replications, setReplications] = useState(10);
  const lifecycle = useSimulationRun();
  const busy =
    lifecycle.submitting ||
    lifecycle.run?.status === "queued" ||
    lifecycle.run?.status === "running" ||
    lifecycle.run?.status === "cancelling";

  useEffect(() => {
    const controller = new AbortController();
    simulationApi
      .health(controller.signal)
      .then((result: HealthResponse) => setHealth(result.status === "ok" ? "online" : "offline"))
      .catch(() => {
        if (!controller.signal.aborted) setHealth("offline");
      });
    return () => controller.abort();
  }, []);

  const startRun = () => {
    void lifecycle.start({ ...config, policies: [...policies], replications });
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>
          <div>
            <p className="brand-kicker">Research workspace <span>·</span> Study B</p>
            <h1>Simulated load balancing</h1>
          </div>
        </div>
        <div className={`api-health health-${health}`}><span className="status-dot" />API {health}</div>
      </header>

      <div className="page-content">
        <section className="hero-row">
          <div>
            <p className="hero-overline">Discrete-event experiment console</p>
            <h2>Compare routing policies under paired traffic.</h2>
            <p className="hero-description">
              Configure a reproducible scenario, run the approved traditional policies, and inspect
              measured simulation results.
            </p>
          </div>
          <div className="hero-aside">
            <div className="hero-aside-line"><span className="hero-number">03</span><span>Routing policies</span></div>
            <div className="hero-policy-list">Round Robin <i /> Least Connections <i /> Weighted</div>
          </div>
        </section>

        <div className="workspace-grid">
          <ConfigurationPanel
            config={config}
            setConfig={setConfig}
            policies={policies}
            setPolicies={setPolicies}
            replications={replications}
            setReplications={setReplications}
            busy={Boolean(busy)}
            onSubmit={startRun}
          />
          <div className="side-column">
            <RunLifecyclePanel
              run={lifecycle.run}
              error={lifecycle.error}
              submitting={lifecycle.submitting}
              cancelling={lifecycle.cancelling}
              loadingResults={lifecycle.loadingResults}
              onCancel={() => void lifecycle.cancel()}
              onRetryResults={lifecycle.retryResults}
            />
            <section className="guardrail-card">
              <div className="guardrail-icon">i</div>
              <div>
                <strong>Simulation guardrails</strong>
                <p>CPU is shown only as a simulated busy-slot proxy. Physical CPU and memory are not measured.</p>
              </div>
            </section>
          </div>
        </div>

        {lifecycle.results && <ResultsDashboard data={lifecycle.results} />}

        <footer className="page-footer">
          <span>Study B · simulated load balancing</span>
          <span>Paired traces · seeded scenarios · local research API</span>
        </footer>
      </div>
    </main>
  );
}
