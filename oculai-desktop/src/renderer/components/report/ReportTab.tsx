import { useStore } from "../../store/index.js";
import { Download, FileText } from "lucide-react";

export function ReportTab() {
  const reportHtml = useStore((s) => s.reportHtml);
  const activeRunId = useStore((s) => s.activeRunId);

  const handleExport = async () => {
    if (!activeRunId) return;
    try {
      const result = await window.oculai.exportReport({
        runId: activeRunId,
        format: "html",
      });
      const data = result as { html_content?: string };
      if (data.html_content) {
        useStore.getState().setReportHtml(data.html_content);
      }
    } catch (err) {
      console.error("Export failed:", err);
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
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <FileText className="w-16 h-16 text-gray-700 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-gray-300 mb-2">
            Report Not Generated
          </h2>
          <p className="text-sm text-gray-500 mb-4 max-w-sm">
            The final report will be available after the pipeline completes
            (evaluation + audit phases). You can also export manually.
          </p>
          {activeRunId && (
            <button className="btn-primary flex items-center gap-2 mx-auto" onClick={handleExport}>
              <Download className="w-4 h-4" />
              Generate Report Now
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between p-3 bg-gray-900 border-b border-gray-800">
        <span className="text-sm text-gray-400">
          HTML Report Preview
        </span>
        <div className="flex items-center gap-2">
          <button
            className="btn-secondary flex items-center gap-1 text-xs"
            onClick={handleExport}
          >
            <Download className="w-3.5 h-3.5" />
            Regenerate
          </button>
          <button
            className="btn-primary flex items-center gap-1 text-xs"
            onClick={handleDownload}
          >
            <Download className="w-3.5 h-3.5" />
            Download HTML
          </button>
        </div>
      </div>
      <div className="flex-1">
        <iframe
          srcDoc={reportHtml}
          className="w-full h-full border-0"
          sandbox="allow-scripts allow-same-origin"
          title="Oculai Report"
        />
      </div>
    </div>
  );
}
