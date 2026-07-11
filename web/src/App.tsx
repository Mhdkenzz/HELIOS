import React, { useEffect, useState, useCallback, useRef, useMemo } from "react";
import {
  Terminal,
  AlertTriangle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Sun,
  Moon,
} from "lucide-react";

interface Body {
  command?: string;
  output?: string;
  exit_code?: number;
  elapsed_s?: number;
  mode?: string;
  action?: string;
  path?: string;
  from?: string;
  to?: string;
  msg?: string;
  detail?: string;
}

interface Event {
  ts: number;
  type: string;
  body: Body;
}

interface Stats {
  peak_rss_mb: number;
  mean_cpu_pct: number;
  num_events: number;
}

// ── Dark theme tokens ────────────────────────────────────────────────────────

const DARK = {
  bg: "slate-950",
  surface: "slate-900",
  surfaceHover: "slate-800",
  border: "slate-800",
  text: "slate-100",
  textDim: "slate-500",
  accent: "cyan-400",
  green: "emerald-400",
  amber: "amber-400",
  red: "red-400",
} as const;

// ── Component tokens ────────────────────────────────────────────────────────

const BADGE_BASE =
  "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold border uppercase tracking-wider";
const CODE_BLOCK_CLS =
  "bg-slate-950 text-xs text-slate-200 p-2.5 rounded border border-slate-700/50 overflow-x-auto font-mono leading-relaxed";
const ROW_BASE =
  "flex items-start gap-3 py-1.5 border-b border-slate-800/40";

function Badge({ action }: { action?: string }) {
  const colors: Record<string, string> = {
    created: "bg-emerald-500/20 text-emerald-400 border-emerald-500/40",
    modified: "bg-amber-500/20 text-amber-400 border-amber-500/40",
    deleted: "bg-red-500/20 text-red-400 border-red-500/40",
    moved: "bg-purple-500/20 text-purple-400 border-purple-500/40",
  };
  const c = colors[action || ""] || "bg-slate-500/20 text-slate-400 border-slate-500/40";
  return (
    <span className={`${BADGE_BASE} ${c}`}>
      {action === "created" && "+"}
      {action === "modified" && "~"}
      {action === "deleted" && "\u2715"}
      {action === "moved" && "\u21C4"}
      {action}
    </span>
  );
}

function CodeBlock({ text }: { text: string }) {
  return <pre className={CODE_BLOCK_CLS}>{text}</pre>;
}

function TimeAgo({ ts }: { ts: number }) {
  const d = new Date(ts * 1000);
  return (
    <span className="text-slate-500 tabular-nums">
      {d.toISOString().slice(11, 23)}
    </span>
  );
}

// ── Virtual scroll constants ────────────────────────────────────────────────

const ROW_HEIGHT = 44; // px, approximate height of one event row
const VIEWPORT_BUFFER = 20; // extra rows above/below viewport

function EventRow({
  event,
  onHoverFile,
}: {
  event: Event;
  onHoverFile: (path?: string) => void;
}) {
  const { type, body } = event;

  if (type === "cmd") {
    const isStart = "command" in body && !("exit_code" in body);
    const isDone = "exit_code" in body;
    const colorClass = isStart
      ? "text-cyan-400"
      : isDone
        ? "text-blue-400"
        : "text-slate-500";
    return (
      <div className={ROW_BASE} style={{ height: ROW_HEIGHT }}>
        <TimeAgo ts={event.ts} />
        <span
          className={`w-24 shrink-0 text-[10px] font-bold uppercase tracking-wider pt-0.5 ${colorClass}`}
        >
          {isStart ? "\u25B6 cmd" : isDone ? "\u25A0 done" : "\u25B8 cmd"}
        </span>
        <div className="flex-1 min-w-0">
          {body.command && <CodeBlock text={body.command} />}
          {body.output && <CodeBlock text={body.output} />}
          {body.exit_code !== undefined && (
            <span className="text-[10px] text-slate-500">
              exit {body.exit_code} \u00b7 {body.elapsed_s}s
            </span>
          )}
        </div>
      </div>
    );
  }

  if (type === "file") {
    return (
      <div
        className={`${ROW_BASE} cursor-pointer hover:bg-slate-800/30`}
        style={{ height: ROW_HEIGHT }}
        onMouseEnter={() => onHoverFile(body.path)}
        onMouseLeave={() => onHoverFile(undefined)}
      >
        <TimeAgo ts={event.ts} />
        <Badge action={body.action} />
        <span className="text-sm text-slate-300 font-mono truncate">
          {body.path}
        </span>
      </div>
    );
  }

  if (type === "alert") {
    return (
      <div className="flex items-start gap-3 py-1.5 border-b border-amber-900/30 bg-amber-500/5">
        <TimeAgo ts={event.ts} />
        <span className="text-amber-400 pt-0.5">\u26A0\uFE0F</span>
        <span className="text-sm text-amber-300">{body.msg}</span>
      </div>
    );
  }

  if (type === "system") {
    return (
      <div className={ROW_BASE}>
        <TimeAgo ts={event.ts} />
        <span className="text-cyan-600 pt-0.5 text-[10px] uppercase tracking-wider">
          system
        </span>
        <span className="text-sm text-slate-500">{body.msg}</span>
      </div>
    );
  }

  return <div style={{ height: ROW_HEIGHT }} />;
}

// ── Main component ──────────────────────────────────────────────────────────

export default function App() {
  const [events, setEvents] = useState<Event[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [runId, setRunId] = useState("");
  const [connected, setConnected] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [hoveredPath, setHoveredPath] = useState<string | undefined>();
  const [diffResult, setDiffResult] = useState<string | null>(null);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [selectedTag, setSelectedTag] = useState("");
  const [rollbackResult, setRollbackResult] = useState<string | null>(null);
  const [rollbackError, setRollbackError] = useState<string | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // ── WebSocket connection ──────────────────────────────────────────────────

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      ws = new WebSocket(`ws://${window.location.host}/ws`);

      ws.onopen = () => {
        setConnected(true);
        setRetryCount(0);
      };

      ws.onclose = () => {
        setConnected(false);
        const delay = Math.min(1000 * Math.pow(2, retryCount), 30000);
        reconnectTimer = setTimeout(() => {
          setRetryCount((c) => c + 1);
          connect();
        }, delay);
      };

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === "info") return;

          if (data.type && data.body !== undefined) {
            setEvents((prev) => {
              const key = `${data.ts}-${data.type}-${JSON.stringify(data.body)}`;
              if (
                prev.some(
                  (ev) =>
                    `${ev.ts}-${ev.type}-${JSON.stringify(ev.body)}` === key
                )
              )
                return prev;
              return [...prev, data as Event];
            });
          } else if (data.events) {
            setEvents(data.events);
          }
          if (data.stats) {
            setStats(data.stats);
          }
        } catch {
          /* ignore malformed frames */
        }
      };
    };

    connect();
    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [retryCount]);

  // ── Diff fetch on hover ───────────────────────────────────────────────────

  useEffect(() => {
    if (!hoveredPath) {
      setDiffResult(null);
      setDiffError(null);
      return;
    }

    const controller = new AbortController();
    const fetchDiff = async () => {
      try {
        const resp = await fetch(
          `/diff?path=${encodeURIComponent(hoveredPath)}`,
          { signal: controller.signal }
        );
        const json = await resp.json();
        if (controller.signal.aborted) return;
        setDiffResult(json.diff || json.error || "No diff available.");
        setDiffError(json.error || null);
      } catch (e) {
        if (!controller.signal.aborted) setDiffError("Failed to fetch diff.");
      }
    };

    const id = setTimeout(fetchDiff, 300);
    return () => {
      controller.abort();
      clearTimeout(id);
    };
  }, [hoveredPath]);

  // ── Rollback ──────────────────────────────────────────────────────────────

  const handleRollback = useCallback(async () => {
    if (!selectedTag) return;
    setRollbackError(null);
    setRollbackResult(null);
    try {
      const resp = await fetch(`/rollback?tag=${encodeURIComponent(selectedTag)}`, {
        method: "POST",
      });
      const json = await resp.json();
      if (json.status === "error") {
        setRollbackError(json.message);
      } else {
        setRollbackResult(`\u2713 Rolled back to ${selectedTag}`);
      }
    } catch (e) {
      setRollbackError("Network error during rollback.");
    }
  }, [selectedTag]);

  // ── Virtual scroll computation ─────────────────────────────────────────────

  const totalRows = events.length;
  const viewportHeight = 600;
  const visibleCount =
    Math.ceil(viewportHeight / ROW_HEIGHT) + VIEWPORT_BUFFER * 2;
  const startIndex = Math.max(
    0,
    Math.floor(scrollTop / ROW_HEIGHT) - VIEWPORT_BUFFER
  );
  const endIndex = Math.min(totalRows, startIndex + visibleCount);
  const topSpacerHeight = startIndex * ROW_HEIGHT;
  const bottomSpacerHeight = (totalRows - endIndex) * ROW_HEIGHT;

  const visibleEvents = useMemo(
    () => events.slice(startIndex, endIndex),
    [events, startIndex, endIndex]
  );

  const handleScroll = useCallback(
    (e: React.UIEvent<HTMLDivElement>) => {
      setScrollTop(e.currentTarget.scrollTop);
    },
    []
  );

  // ── Stats bar values ──────────────────────────────────────────────────────

  const cmdCount = useMemo(
    () => events.filter((e) => e.type === "cmd").length,
    [events]
  );
  const fileCount = useMemo(
    () => events.filter((e) => e.type === "file").length,
    [events]
  );
  const alertCount = useMemo(
    () => events.filter((e) => e.type === "alert").length,
    [events]
  );

  // ── Layout ────────────────────────────────────────────────────────────────

  return (
    <div
      className={`min-h-screen bg-${DARK.bg} text-${DARK.text} flex flex-col`}
    >
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header
        className={`flex items-center justify-between px-6 py-3 border-b border-${DARK.border} bg-${DARK.surface}/70 backdrop-blur`}
      >
        <div className="flex items-center gap-3">
          <Terminal className="w-5 h-5 text-cyan-400" />
          <h1 className="text-lg font-bold tracking-tight">Helios</h1>
          {runId && (
            <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded">
              {runId}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          <span
            className={`flex items-center gap-1.5 text-xs px-2 py-0.5 rounded ${
              connected
                ? `bg-${DARK.green}/20 text-${DARK.green}`
                : `bg-${DARK.red}/20 text-${DARK.red}`
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                connected ? `bg-${DARK.green}` : `bg-${DARK.red}`
              }`}
            />
            {connected ? "Live" : "Reconnecting\u2026"}
          </span>
          <button
            onClick={() => setEvents([])}
            className={`flex items-center gap-1 px-2.5 py-0.5 text-xs bg-${DARK.surfaceHover} hover:bg-${DARK.border} rounded transition`}
          >
            <RefreshCw className="w-3 h-3" /> Clear
          </button>
        </div>
      </header>

      {/* ── Stats Bar ───────────────────────────────────────────────────── */}
      {stats && (
        <div
          className={`grid grid-cols-4 gap-3 px-6 py-3 bg-${DARK.surface}/50 border-b border-${DARK.border}`}
        >
          <Stat label="Events" value={stats.num_events} />
          <Stat label="File" value={fileCount} />
          <Stat label="Peak RSS" value={`${stats.peak_rss_mb.toFixed(1)} MB`} />
          <Stat label="Mean CPU" value={`${stats.mean_cpu_pct.toFixed(1)}%`} />
        </div>
      )}

      {/* ── Rollback bar ────────────────────────────────────────────────── */}
      <div
        className={`px-6 py-2 bg-${DARK.surface}/30 border-b border-${DARK.border} flex items-center gap-3`}
      >
        <span className="text-xs text-slate-500 uppercase tracking-wider">
          Restore:
        </span>
        <input
          type="text"
          placeholder="helios-YYYYMMDDTHHMMSSZ"
          value={selectedTag}
          onChange={(e) => setSelectedTag(e.target.value)}
          className={`bg-${DARK.bg} border border-${DARK.border} rounded px-2 py-1 text-xs text-slate-200 w-64 font-mono placeholder-slate-600 focus:outline-none focus:border-cyan-500`}
        />
        <button
          onClick={handleRollback}
          disabled={!selectedTag}
          className="px-3 py-1 bg-amber-600 hover:bg-amber-500 disabled:bg-slate-700 disabled:text-slate-500 rounded text-xs font-bold transition"
        >
          \u21BA Restore to here
        </button>
        {rollbackResult && (
          <span className="text-emerald-400 text-xs">{rollbackResult}</span>
        )}
        {rollbackError && (
          <span className="text-red-400 text-xs">{rollbackError}</span>
        )}
      </div>

      {/* ── Timeline (virtually scrolled) ────────────────────────────────── */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <div
          className="flex-1 overflow-y-auto scrollbar-thin"
          onScroll={handleScroll}
          ref={containerRef}
        >
          <div
            className="px-6 py-2 text-xs text-slate-500 uppercase tracking-wider border-b border-slate-800/40 bg-slate-900/40 flex items-center gap-2"
            style={{ maxHeight: "600px" }}
          >
            <span>Timeline</span>
            <span className="text-slate-600">({events.length} events)</span>
          </div>
          {events.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-600 text-sm">
              Waiting for events\u2026
            </div>
          ) : (
            <div
              className="relative"
              style={{ height: totalRows * ROW_HEIGHT }}
            >
              <div style={{ height: topSpacerHeight }} />
              <div className="divide-y divide-slate-800/40">
                {visibleEvents.map((event, i) => (
                  <EventRow
                    key={startIndex + i}
                    event={event}
                    onHoverFile={setHoveredPath}
                  />
                ))}
              </div>
              <div style={{ height: bottomSpacerHeight }} />
            </div>
          )}
        </div>
      </div>

      {/* ── Diff Pop-up ──────────────────────────────────────────────────── */}
      {hoveredPath && (diffResult || diffError) && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 w-[600px] max-w-[90vw] max-h-[40vh] bg-slate-900 border border-slate-600 rounded-lg shadow-2xl overflow-hidden z-50">
          <div className="flex items-center justify-between px-4 py-2 bg-slate-800 border-b border-slate-700">
            <span className="text-xs font-bold text-cyan-400 font-mono">
              git diff {"\u2014"} {hoveredPath}
            </span>
            <button
              onClick={() => setHoveredPath(undefined)}
              className="text-slate-500 hover:text-white text-xs"
            >
              \u2715
            </button>
          </div>
          <div className="p-3 overflow-auto max-h-[32vh]">
            {diffError ? (
              <span className="text-amber-400 text-xs">
                \u26A0\uFE0F {diffError}
              </span>
            ) : (
              <CodeBlock text={diffResult || "No changes detected."} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="px-4 py-2">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider">
        {label}
      </div>
      <div className="text-sm font-bold">{value}</div>
    </div>
  );
}