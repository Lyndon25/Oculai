import { useStore } from "../../store/index.js";
import { Download, FileText, RefreshCcw } from "lucide-react";
import { useState } from "react";
import { EmptyState, LoadingInline } from "../ui/primitives.js";

export function ReportTab() {
  const reportHtml = useStore((s) => s.reportHtml);
  const activeRunId = useStore((s) => s.activeRunId);
  const setReportHtml = useStore((s) => s.setReportHtml);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExport = async () => {
    if (!activeRunId) return;
    setExporting(true);
    setError(null);
    try {
      const result = await window.oculai.exportReport({
        runId: activeRunId,
        format: "html",
      });
      const data = result as { html_content?: string; html?: string };
      const html = data.html_content ?? data.html;
      if (html) {
        if (!useStore.getState().reportHtml) {
          setReportHtml(html);
        }
      } else {
        setError("报告导出成功但没有返回 HTML 内容。");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setExporting(false);
    }
  };

  const handleDownload = () => {
    if (!reportHtml) return;
    const blob = new Blob([reportHtml], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `oculai-report-${activeRunId?.slice(0, 8)}.html`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!reportHtml) {
    return (
      <div className="h-full">
        <EmptyState
          icon={FileText}
          title="报告尚未生成"
          description="评估与审计完成后自动生成；也可手动导出当前结果。"
          action={
            activeRunId && (
              <button className="btn-primary" onClick={handleExport} disabled={exporting} type="button">
                {exporting ? (
                  <LoadingInline label="生成中" />
                ) : (
                  <>
                    <Download className="h-4 w-4" aria-hidden="true" />
                    生成报告
                  </>
                )}
              </button>
            )
          }
        />
        {error && (
          <p className="px-6 text-center text-[13px] text-error" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-rule bg-surface px-4 py-2.5">
        <div>
          <span className="text-[13px] font-semibold text-ink tracking-tight">HTML 报告预览</span>
          <p className="text-[10px] text-ink-muted mt-0.5">静态沙箱预览；下载后可独立打开。</p>
        </div>
        <div className="flex items-center gap-2">
          {error && (
            <span className="text-[12px] text-error" role="alert">
              {error}
            </span>
          )}
          <button
            className="btn-secondary text-[12px]"
            onClick={handleExport}
            disabled={exporting}
            type="button"
          >
            {exporting ? (
              <LoadingInline label="刷新中" />
            ) : (
              <>
                <RefreshCcw className="h-3.5 w-3.5" aria-hidden="true" />
                重新生成
              </>
            )}
          </button>
          <button className="btn-primary text-[12px]" onClick={handleDownload} type="button">
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            下载 HTML
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 bg-white">
        <iframe
          srcDoc={reportHtml}
          className="h-full w-full border-0"
          sandbox="allow-same-origin"
          title="Oculai Report"
        />
      </div>
    </div>
  );
}
