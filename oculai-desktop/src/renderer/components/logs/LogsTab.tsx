import { useStore } from "../../store/index.js";
import { useEffect, useRef } from "react";
import { Terminal, Wrench, Brain, AlertTriangle } from "lucide-react";

export function LogsTab() {
  const messages = useStore((s) => s.messages);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length]);

  const getIcon = (msg: (typeof messages)[number]) => {
    if (msg.isError) return <AlertTriangle className="w-3.5 h-3.5 text-red-400" />;
    if (msg.isThinking) return <Brain className="w-3.5 h-3.5 text-purple-400" />;
    if (msg.role === "tool") return <Wrench className="w-3.5 h-3.5 text-yellow-400" />;
    if (msg.role === "assistant") return <Terminal className="w-3.5 h-3.5 text-blue-400" />;
    return null;
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between p-3 bg-gray-900 border-b border-gray-800">
        <span className="text-sm text-gray-400 flex items-center gap-2">
          <Terminal className="w-4 h-4" />
          Agent Activity Log ({messages.length} messages)
        </span>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 font-mono text-xs">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <p className="text-gray-600">No activity yet. Start a sourcing run to see the agent at work.</p>
          </div>
        ) : (
          <div className="space-y-1">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`p-2 rounded ${
                  msg.isError
                    ? "bg-red-900/20 border border-red-800/30"
                    : msg.isThinking
                      ? "bg-purple-900/10"
                      : msg.role === "tool"
                        ? "bg-gray-800/30"
                        : "bg-gray-800/10"
                }`}
              >
                <div className="flex items-center gap-2 mb-0.5">
                  {getIcon(msg)}
                  <span className="text-gray-600">
                    {new Date(msg.timestamp).toLocaleTimeString()}
                  </span>
                  <span className="text-gray-500 font-medium">
                    {msg.role === "tool" ? "TOOL" : msg.role.toUpperCase()}
                  </span>
                  {msg.toolName && (
                    <span className="text-blue-400">{msg.toolName}</span>
                  )}
                </div>
                <div
                  className={`pl-5 ${
                    msg.isThinking
                      ? "text-gray-500 italic"
                      : msg.isError
                        ? "text-red-300"
                        : msg.role === "tool"
                          ? "text-gray-400"
                          : "text-gray-300"
                  }`}
                >
                  {msg.content.length > 500
                    ? msg.content.slice(0, 500) + "..."
                    : msg.content}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
