import { AlertCircle, CheckCircle2, Circle, Info, Loader2 } from "lucide-react";
import type React from "react";
import type { RunStatus } from "../../../shared/types.js";

export function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

/* ─── Empty State · Refined ─── */
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
    <div className="flex h-full min-h-[160px] items-center justify-center p-8 text-center">
      <div className="max-w-xs">
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-warm-100">
          <Icon className="h-6 w-6 text-warm-500" aria-hidden="true" />
        </div>
        <h3 className="text-[15px] font-semibold text-ink tracking-tight">{title}</h3>
        {description && (
          <p className="mt-1.5 text-[13px] leading-5 text-ink-muted">{description}</p>
        )}
        {action && <div className="mt-5 flex justify-center">{action}</div>}
      </div>
    </div>
  );
}

/* ─── Loading · Breath Animation ─── */
export function LoadingInline({ label = "加载中" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-[13px] text-ink-muted" role="status" aria-live="polite">
      <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" aria-hidden="true" />
      {label}
    </span>
  );
}

/* ─── Run Status Badge · Softer Palette ─── */
export function RunStatusBadge({ status }: { status: RunStatus | string }) {
  const map: Record<string, { label: string; className: string }> = {
    draft:     { label: "草稿",   className: "badge-neutral" },
    running:   { label: "运行中", className: "badge-success" },
    paused:    { label: "已暂停", className: "badge-warning" },
    reviewing: { label: "审核中", className: "badge-accent" },
    completed: { label: "已完成", className: "badge badge border border-blue-200 bg-blue-50 text-blue-700" },
    aborted:   { label: "已中止", className: "badge-error" },
  };
  const item = map[status] ?? { label: status, className: "badge-neutral" };
  return <span className={item.className}>{item.label}</span>;
}

/* ─── Score Pill · Visual Weight ─── */
export function ScorePill({ score, size = "sm" }: { score?: number; size?: "sm" | "md" }) {
  if (score === undefined || score === null) {
    return (
      <span className={cx(
        "badge-neutral font-mono",
        size === "md" ? "text-xs px-3 py-1" : "text-[10px]",
      )}>
        未评分
      </span>
    );
  }

  const pct = Math.round(score);
  const isHigh = pct >= 80;
  const isMid = pct >= 60;
  const isLow = pct >= 40;

  const colorVar = isHigh
    ? "var(--oc-success)"
    : isMid
      ? "var(--oc-warning)"
      : isLow
        ? "#C2853A"
        : "var(--oc-error)";

  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 font-mono font-semibold tracking-tight",
        size === "md" ? "text-sm" : "text-xs",
      )}
      style={{ color: colorVar }}
    >
      <svg width={size === "md" ? 14 : 12} height={size === "md" ? 14 : 12} viewBox="0 0 14 14" className="shrink-0">
        <circle cx="7" cy="7" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.3" />
        <circle
          cx="7" cy="7" r="5.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeDasharray={`${(pct / 100) * 34.56} 34.56`}
          strokeLinecap="round"
          transform="rotate(-90 7 7)"
          opacity="0.9"
        />
      </svg>
      {pct}
    </span>
  );
}

/* ─── Evidence Tier Badge ─── */
export function EvidenceTierBadge({ tier }: { tier?: number }) {
  const safeTier = tier ?? 4;
  const map: Record<number, string> = {
    1: "badge-success",
    2: "badge badge border border-blue-200 bg-blue-50 text-blue-700",
    3: "badge-warning",
    4: "badge-neutral",
  };
  return <span className={map[safeTier] ?? "badge-neutral"}>T{safeTier}</span>;
}

/* ─── Switch · Refined Toggle ─── */
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
    <div className="flex items-center justify-between gap-4 rounded-xl border border-rule bg-surface px-4 py-3.5 transition-colors duration-150 hover:border-rule-hover">
      <div className="min-w-0">
        <div className="text-[13px] font-medium text-ink">{label}</div>
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
          "relative h-6 w-11 shrink-0 rounded-full transition-all duration-250",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-white",
          checked ? "bg-accent shadow-[0_2px_6px_rgba(232,93,63,0.3)]" : "bg-rule-strong",
        )}
        onClick={() => onChange(!checked)}
      >
        <span
          className={cx(
            "absolute top-1 h-4 w-4 rounded-full bg-white shadow-sm transition-all duration-250 ease-[var(--oc-spring-bouncy)]",
            checked ? "translate-x-6" : "translate-x-1",
          )}
        />
      </button>
    </div>
  );
}

/* ─── Health Dot · Status Indicator ─── */
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
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors duration-200",
        ok && "bg-success-soft text-success border border-success-muted",
        pending && "bg-warning-soft text-warning border border-warning-muted",
        error && "bg-error-soft text-error border border-error-muted",
        !ok && !pending && !error && "bg-surface-hover text-ink-muted border border-rule",
      )}
      title={`${label}: ${status ?? "unknown"}`}
    >
      <Icon className={cx("h-3 w-3", pending && "animate-spin")} aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}

/* ─── Progress Bar · Smooth ─── */
export function ProgressBar({ value, max = 100, className }: { value: number; max?: number; className?: string }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className={cx("h-1.5 rounded-full bg-rule overflow-hidden", className)}>
      <div
        className="h-full rounded-full bg-accent transition-all duration-500 ease-[var(--oc-spring-smooth)]"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/* ─── Section Header ─── */
export function SectionHeader({
  icon: Icon,
  title,
  subtitle,
  action,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 mb-4">
      <div className="flex items-center gap-2.5 min-w-0">
        {Icon && <Icon className="h-4 w-4 text-accent shrink-0" aria-hidden="true" />}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink tracking-tight">{title}</h3>
          {subtitle && <p className="text-[11px] text-ink-muted mt-0.5 truncate">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}
