import { useStore } from "../../store/index.js";
import { useEffect, useRef, useCallback } from "react";
import { Terminal, Wrench, Brain, AlertTriangle, Info } from "lucide-react";
import { EmptyState, cx } from "../ui/primitives.js";

export function LogsTab() {
  const messages = useStore((s) => s.messages);
  const scrollRef = useRef<HTMLDivElement>(null);
  const isAtBottom = useRef(true);

  const checkAtBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const threshold = 40; // px from bottom to consider "at bottom"
    isAtBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.addEventListener("scroll", checkAtBottom, { passive: true });
    return () => el.removeEventListener("scroll", checkAtBottom);
  }, [checkAtBottom]);

  useEffect(() => {
    if (isAtBottom.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length]);

  const getIcon = (msg: (typeof messages)[number]) => {
    if (msg.isError) return <AlertTriangle className="h-3.5 w-3.5 text-red-500" aria-hidden="true" />;
    if (msg.isThinking) return <Brain className="h-3.5 w-3.5 text-purple-500" aria-hidden="true" />;
    if (msg.role === "tool") return <Wrench className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />;
    if (msg.role === "system") return <Info className="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />;
    return <Terminal className="h-3.5 w-3.5 text-accent" aria-hidden="true" />;
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center border-b border-rule bg-surface px-4 py-2.5">
        <span className="flex items-center gap-2 text-sm font-semibold text-ink">
          <Terminal className="h-4 w-4" aria-hidden="true" />
          Agent / System Logs
          <span className="font-mono text-xs font-normal text-ink-muted">{messages.length}</span>
        </span>
      </div>
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto p-4 font-mono text-xs">
        {messages.length === 0 ? (
          <EmptyState
            icon={Terminal}
            title="暂无日志"
            description="启动寻访后，Pi 输出、工具调用与系统状态会显示在这里。"
          />
        ) : (
          <div className="space-y-2">
            {messages.map((msg, i) => (
              <div
                key={`${msg.timestamp}-${i}`}
                className={cx(
                  "rounded-lg border p-2",
                  msg.isError
                    ? "border-red-200 bg-red-50/60"
                    : msg.isThinking
                      ? "border-purple-200 bg-purple-50/40"
                      : msg.role === "tool"
                        ? "border-amber-200 bg-amber-50/40"
                        : msg.role === "system"
                          ? "border-rule bg-surface-hover"
                          : "border-rule bg-surface",
                )}
              >
                <div className="mb-1 flex items-center gap-2">
                  {getIcon(msg)}
                  <span className="text-ink-muted">
                    {new Date(msg.timestamp).toLocaleTimeString()}
                  </span>
                  <span className="font-semibold text-ink-secondary">
                    {msg.role === "tool" ? "TOOL" : msg.role.toUpperCase()}
                  </span>
                  {msg.toolName && (
                    <span className="truncate text-accent">{msg.toolName}</span>
                  )}
                </div>
                <div
                  className={cx(
                    "whitespace-pre-wrap break-words pl-5 leading-5",
                    msg.isThinking
                      ? "italic text-ink-muted"
                      : msg.isError
                        ? "text-red-700"
                        : msg.role === "tool"
                          ? "text-ink-muted"
                          : "text-ink-secondary",
                  )}
                >
                  {msg.content.length > 800 ? `${msg.content.slice(0, 800)}...` : msg.content}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
