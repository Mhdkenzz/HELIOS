import { useEffect, useState } from "react";
import { Play, RefreshCw, Terminal, Clock, AlertTriangle } from "lucide-react";

interface Event {
  ts: string;
  type: string;
  detail: string;
  pid?: number;
}

interface Stats {
  peak_rss_mb: number;
  mean_cpu_pct: number;
  num_events: number;
}

export default function App() {
  const [events, setEvents] = useState<Event[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [runId, setRunId] = useState("");
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.host}/ws`);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.events) setEvents((prev) => [...prev, ...data.events]);
      if (data.stats) setStats(data.stats);
      if (data.run_id) setRunId(data.run_id);
    };
    return () => ws.close();
  }, []);

  const eventColors: Record<string, string> = {
    "shell.start": "text-green-400",
    "shell.done": "text-blue-400",
    "shell.output": "text-gray-400",
    "fs.create": "text-emerald-400",
    "fs.modify": "text-yellow-400",
    "fs.delete": "text-red-400",
    "fs.move": "text-purple-400",
    "system": "text-cyan-400",
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 font-mono">
      {/* Header */}
      <header className="flex items-center justify-between mb-8 border-b border-slate-700 pb-4">
        <div className="flex items-center gap-2">
          <Terminal className="w-6 h-6 text-cyan-400" />
          <h1 className="text-xl font-bold tracking-tight">Helios</h1>
          {runId && <span className="text-sm text-slate-500 ml-2">{runId}</span>}
        </div>
        <div className="flex items-center gap-4 text-sm">
          <div className={`flex items-center gap-1 ${connected ? "text-emerald-400" : "text-red-400"}`}>
            <div className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-400" : "bg-red-400"}`} />
            {connected ? "Live" : "Disconnected"}
          </div>
          <button
            onClick={() => window.location.reload()}
            className="flex items-center gap-1 px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 transition"
          >
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>
      </header>

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <StatCard label="Events" value={stats.num_events} icon={<Play className="w-4 h-4" />} />
          <StatCard label="Peak RSS" value={`${stats.peak_rss_mb.toFixed(1)} MB`} icon={<AlertTriangle className="w-4 h-4" />} />
          <StatCard label="Mean CPU" value={`${stats.mean_cpu_pct.toFixed(1)}%`} icon={<Clock className="w-4 h-4" />} />
        </div>
      )}

      {/* Timeline */}
      <div className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
        <div className="p-3 text-sm text-slate-400 border-b border-slate-700">Timeline</div>
        <div className="h-[60vh] overflow-y-auto p-2 space-y-1">
          {events.map((e, i) => (
            <div key={i} className="flex gap-3 text-xs py-1 hover:bg-slate-800/50 rounded px-2">
              <span className="text-slate-500 w-28 shrink-0">
                {e.ts.slice(11, 23)}
              </span>
              <span className={`w-32 shrink-0 font-semibold ${eventColors[e.type] || "text-white"}`}>
                {e.type}
              </span>
              <span className="text-slate-300 flex-1">{e.detail}</span>
            </div>
          ))}
          {events.length === 0 && (
            <div className="text-center text-slate-600 py-12">
              Waiting for events…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return (
    <div className="bg-slate-900 rounded-lg border border-slate-700 p-4 flex items-center gap-3">
      <span className="text-slate-400">{icon}</span>
      <div>
        <div className="text-xs text-slate-500 uppercase tracking-wider">{label}</div>
        <div className="text-lg font-bold">{value}</div>
      </div>
    </div>
  );
}