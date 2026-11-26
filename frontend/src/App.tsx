import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HealthResponse } from "./types/api";

export default function App() {
  const [health, setHealth] = useState<"checking" | "online" | "offline">("checking");

  useEffect(() => {
    let active = true;
    fetch("/api/v1/health")
      .then((response) => {
        if (!response.ok) throw new Error("API unavailable");
        return response.json() as Promise<HealthResponse>;
      })
      .then((result) => {
        if (active) setHealth(result.status === "ok" ? "online" : "offline");
      })
      .catch(() => {
        if (active) setHealth("offline");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="min-h-screen bg-mist text-ink">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal">
              Research workspace
            </p>
            <h1 className="mt-1 text-xl font-semibold">Intelligent Network Load Balancing</h1>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1.5 text-sm text-slate-600">
            API {health}
          </span>
        </div>
      </header>

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <section className="grid gap-5 md:grid-cols-2">
          <StudyCard
            eyebrow="Study A · CIC-IDS2017"
            title="Feature selection"
            description="Real dataset classification with a shared Random Forest evaluator."
            methods="Full-feature baseline · GA · Binary PSO · ACO"
          />
          <StudyCard
            eyebrow="Study B · Discrete-event simulation"
            title="Load balancing"
            description="Compare routing policies on reproducible simulated traffic and server scenarios."
            methods="Round Robin · Least Connections · Weighted · RF · GA · PSO · ACO"
          />
        </section>

        <section className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="font-semibold">Experiment metrics</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Results will appear after an experiment is implemented and run.
                </p>
              </div>
              <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800">
                No runs yet
              </span>
            </div>
            <div className="mt-5 h-48" aria-label="Empty experiment chart">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={[]}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="run" />
                  <YAxis />
                  <Tooltip />
                  <Line dataKey="value" stroke="#0d9488" />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="text-center text-xs text-slate-400">No experimental data to plot</p>
          </div>

          <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="font-semibold">Research guardrails</h2>
            <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-600">
              <li>Test data stays sealed until model and feature choices are frozen.</li>
              <li>Simulated routing metrics are not physical network measurements.</li>
              <li>Every run should record its seed, configuration, and provenance.</li>
            </ul>
            <p className="mt-5 border-t border-slate-100 pt-4 text-xs text-slate-400">
              Skeleton only · algorithms and experiment workflows are not implemented.
            </p>
          </aside>
        </section>
      </div>
    </main>
  );
}

function StudyCard({
  eyebrow,
  title,
  description,
  methods,
}: {
  eyebrow: string;
  title: string;
  description: string;
  methods: string;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-teal">{eyebrow}</p>
      <h2 className="mt-3 text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
      <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">{methods}</p>
    </section>
  );
}
