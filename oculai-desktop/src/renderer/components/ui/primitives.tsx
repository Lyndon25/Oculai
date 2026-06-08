import { AlertCircle, CheckCircle2, Circle, Info, Loader2 } from "lucide-react";
import type React from "react";
import type { RunStatus } from "../../../shared/types.js";

export function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

/* ─── Empty State ─── */
export function EmptyState({
  icon: Icon = Info,
  title,
  description,
  action,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex h-full min-h-[160px] items-center justify-center p-6 text-center">
      <div className="max-w-sm">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-rule bg-surface-hover">
          <Icon className="h-5 w-5 text-ink-muted" aria-hidden="true" />
        </div>
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        {description && (
          <p className="mt-1 text-xs leading-5 text-ink-muted">{description}</p>
        )}
        {action && <div className="mt-4 flex justify-center">{action}</div>}
      </div>
    </div>
  );
}

/* ─── Loading ─── */
export function LoadingInline({ label = "加载中" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-xs" role="status" aria-live="polite">
      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
      {label}
    </span>
  );
}

/* ─── Run Status Badge ─── */
export function RunStatusBadge({ status }: { status: RunStatus | string }) {
  const map: Record<string, { label: string; className: string }> = {
    draft: { label: "草稿", className: "badge-neutral" },
    running: { label: "运行中", className: "badge-success" },
    paused: { label: "已暂停", className: "badge-warning" },
    reviewing: { label: "审核中", className: "badge-accent" },
    completed: { label: "已完成", className: "badge badge border border-blue-200 bg-blue-50 text-blue-700" },
    aborted: { label: "已中止", className: "badge-error" },
  };
  const item = map[status] ?? { label: status, className: "badge-neutral" };
  return <span className={item.className}>{item.label}</span>;
}

/* ─── Score Pill ─── */
export function ScorePill({ score }: { score?: number }) {
  if (score === undefined || score === null) {
    return <span className="badge badge-neutral">未评分</span>;
  }
  const className =
    score >= 80
      ? "badge badge-success"
      : score >= 60
        ? "badge badge-warning"
        : score >= 40
          ? "badge badge border border-orange-200 bg-orange-50 text-orange-700"
          : "badge badge-error";
  return <span className={cx("font-mono", className)}>{Math.round(score)}</span>;
}

/* ─── Evidence Tier Badge ─── */
export function EvidenceTierBadge({ tier }: { tier?: number }) {
  const safeTier = tier ?? 4;
  const className =
    safeTier <= 1
      ? "badge badge-success"
      : safeTier === 2
        ? "badge badge border border-blue-200 bg-blue-50 text-blue-700"
        : safeTier === 3
          ? "badge badge-warning"
          : "badge badge-neutral";
  return <span className={className}>T{safeTier}</span>;
}

/* ─── Switch ─── */
export function Switch({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-rule bg-surface px-3.5 py-3">
      <div className="min-w-0">
        <div className="text-xs font-medium text-ink">{label}</div>
        {description && (
          <div className="mt-0.5 text-[11px] leading-4 text-ink-muted">{description}</div>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={`${label}: ${checked ? "已启用" : "已停用"}`}
        className={cx(
          "relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-white",
          checked ? "bg-accent" : "bg-rule-strong",
        )}
        onClick={() => onChange(!checked)}
      >
        <span
          className={cx(
            "absolute top-1 h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200",
            checked ? "translate-x-6" : "translate-x-1",
          )}
        />
      </button>
    </div>
  );
}

/* ─── Health Dot ─── */
export function HealthDot({
  status,
  label,
}: {
  status: string | undefined;
  label: string;
}) {
  const ok = status === "connected" || status === "ready" || status === "configured";
  const pending = status === "connecting" || status === "starting";
  const error = status === "error";
  const Icon = ok ? CheckCircle2 : error ? AlertCircle : pending ? Loader2 : Circle;

  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        ok && "border-emerald-200 bg-emerald-50 text-emerald-700",
        pending && "border-amber-200 bg-amber-50 text-amber-700",
        error && "border-red-200 bg-red-50 text-red-700",
        !ok && !pending && !error && "border-rule bg-surface-hover text-ink-muted",
      )}
      title={`${label}: ${status ?? "unknown"}`}
    >
      <Icon className={cx("h-3 w-3", pending && "animate-spin")} aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}
