import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import client from "../api/client";
import Navbar from "../components/Navbar";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer
} from 'recharts';

export default function JobDetailsPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const user = useMemo(
    () => JSON.parse(localStorage.getItem("user") || "{}"),
    []
  );
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const canPublish = user.role === "platform_admin" || user.role === "ml_engineer";

  const loadDetails = async (showLoader = true) => {
    if (showLoader) setLoading(true);
    try {
      const res = await client.get(`/jobs/${jobId}/details`);
      setDetails(res.data);
    } catch (err) {
      if (showLoader) setError(err.response?.data?.detail || "Failed to load job details.");
    } finally {
      if (showLoader) setLoading(false);
    }
  };

  useEffect(() => {
    loadDetails(true);
    
    // LIVE GRAPH SYNC: Automatically poll the API every 3 seconds for new rolling updates
    const intervalId = setInterval(() => {
      loadDetails(false); // Fetch new data silently without flashing the loading screen
    }, 3000);

    return () => clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const publishResults = async () => {
    setMessage("");
    try {
      const res = await client.post(`/jobs/${jobId}/publish`);
      setMessage(res.data.message);
      await loadDetails();
    } catch (err) {
      setMessage(err.response?.data?.detail || "Failed to publish results.");
    }
  };

  const downloadReport = () => {
    const blob = new Blob([JSON.stringify(details, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `federhub-job-${details.job.id}-details.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const finalMetric = details?.final_metric;

  return (
    <div style={styles.page}>
      <Navbar />
      <main style={styles.content}>
        <button style={styles.backBtn} onClick={() => navigate("/dashboard")}>
          Back to Dashboard
        </button>

        {loading && <p style={styles.muted}>Loading job details...</p>}
        {error && <p style={styles.error}>{error}</p>}
        {message && <p style={styles.notice}>{message}</p>}

        {details && (
          <>
            <section style={styles.header}>
              <div>
                <span style={styles.eyebrowBadge}>JOB ID: {details.job.id}</span>
                <h1 style={styles.title}>{details.job.job_name}</h1>
                <p style={styles.muted}>Viewing as: <strong style={{color: '#f8fafc'}}>{user.email}</strong></p>
              </div>
              <span style={styles.status}>{details.job.status}</span>
            </section>

            <section style={styles.actions}>
              <button style={styles.downloadBtn} onClick={downloadReport}>
                Download Full Details
              </button>
              {canPublish && details.job.status === "completed" && !details.job.results_published && (
                <button style={styles.publishBtn} onClick={publishResults}>
                  Publish Results to Clients
                </button>
              )}
              {details.job.results_published && (
                <span style={styles.published}>Published to Client Operators</span>
              )}
            </section>

            <section style={styles.summaryGrid}>
              <SummaryCard label="Total Updates Aggregated" value={details.metrics.length} />
              <SummaryCard label="Latest Accuracy" value={formatMetric(finalMetric?.accuracy)} />
              <SummaryCard label="Latest Loss" value={formatMetric(finalMetric?.loss)} />
              <SummaryCard label="Total Network Samples" value={finalMetric?.total_samples ?? "0"} />
            </section>

            {details.metrics && details.metrics.length > 0 && (
               <MetricsDashboard metrics={details.metrics} finalMetric={finalMetric} />
            )}

            {details.metrics && details.metrics.length > 0 && (
              <ModelVersionsPanel
                metrics={details.metrics}
                submissions={details.submissions}
                jobId={jobId}
                jobName={details.job.job_name}
              />
            )}

            <section style={styles.panel}>
              <h2 style={styles.panelTitle}>Client Round Submissions</h2>
              <div style={styles.tableWrap}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>Client</th>
                      <th style={styles.th}>Round</th>
                      <th style={styles.th}>Samples</th>
                      <th style={styles.th}>Accuracy</th>
                      <th style={styles.th}>Loss</th>
                      <th style={styles.th}>Weights Preview</th>
                    </tr>
                  </thead>
                  <tbody>
                    {details.submissions.map((submission) => (
                      <tr key={submission.id}>
                        <td style={styles.td}>
                          {submission.client_email || submission.client_label}
                        </td>
                        <td style={styles.td}>{submission.round_number}</td>
                        <td style={styles.td}>{submission.sample_count}</td>
                        <td style={styles.td}>{formatMetric(submission.accuracy)}</td>
                        <td style={styles.td}>{formatMetric(submission.loss)}</td>
                        <td style={styles.tdMono}>
                          {submission.weights.slice(0, 5).join(", ")}
                          {submission.weights.length > 5 ? "..." : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}

// --- Custom Recharts Tooltip showing User Names ---
const CustomHoverTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    const dataPoint = payload[0].payload;
    return (
      <div style={{ backgroundColor: '#0f172a', padding: '10px', border: '1px solid #38bdf8', borderRadius: '5px', color: '#f1f5f9', fontSize: '13px' }}>
        <p style={{ margin: '0 0 5px 0', fontWeight: 'bold' }}>{label}</p>
        <p style={{ margin: '0 0 5px 0', color: '#94a3b8' }}>
          <strong>Contributors: </strong> {dataPoint.clients || "System Default"}
        </p>
        <hr style={{ borderColor: '#334155', margin: '5px 0' }}/>
        {payload.map((entry, index) => (
          <p key={index} style={{ color: entry.color, margin: '3px 0' }}>
            {entry.name}: {entry.value?.toFixed(4)}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

// --- Interactive Metrics Dashboard ---
function MetricsDashboard({ metrics, finalMetric }) {
  // A palette of distinct colors for the multi-line weight chart
  const lineColors = ['#38bdf8', '#4ade80', '#fbbf24', '#c084fc', '#f87171', '#a78bfa'];

  // 1. Prepare Chart Data (Accuracy, Loss, AND Weights over time)
  const trendData = metrics.map(m => {
    const snapshot = m.global_weights_snapshot || {};
    const parsedSnapshot = typeof snapshot === 'string' ? JSON.parse(snapshot) : snapshot;
    const clientList = parsedSnapshot.client_labels ? parsedSnapshot.client_labels.join(", ") : "Unknown Clients";

    let dataPoint = {
      round: `Round ${m.round_number}`,
      accuracy: m.accuracy || 0,
      loss: m.loss || 0,
      clients: clientList
    };

    const isStructured = Object.keys(parsedSnapshot).length > 0 && !parsedSnapshot.global_weights;
    if (isStructured) {
      Object.keys(parsedSnapshot).forEach(key => {
        if (key !== 'client_labels' && key !== 'algorithm' && key !== 'round_number') {
          dataPoint[key.replace('.weight', '').replace('.bias', ' (b)')] = parsedSnapshot[key].mean || 0;
        }
      });
    } else {
      const flatWeights = parsedSnapshot.global_weights || m.global_weights || [];
      flatWeights.forEach((w, i) => {
        if (i < 6) dataPoint[`Param ${i+1}`] = w;
      });
    }
    return dataPoint;
  });

  const weightKeys = trendData.length > 0 
    ? Object.keys(trendData[0]).filter(k => k !== 'round' && k !== 'accuracy' && k !== 'loss' && k !== 'clients')
    : [];

  return (
    <section style={styles.panel}>
      <h2 style={styles.panelTitle}>FedAvg Training Dashboard</h2>
      <p style={styles.muted}>Real-time visualization of model convergence and weight distribution.</p>
      
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", marginTop: "20px" }}>
        
        {/* Performance Trends Chart */}
        <div style={styles.chartContainer}>
          <h3 style={styles.chartTitle}>Accuracy & Loss Convergence</h3>
          <div style={{ height: 280, width: '100%' }}>
            <ResponsiveContainer>
              <LineChart data={trendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="round" stroke="#94a3b8" style={{fontSize: '12px'}} />
                <YAxis yAxisId="left" stroke="#4ade80" style={{fontSize: '12px'}} />
                <YAxis yAxisId="right" orientation="right" stroke="#f87171" style={{fontSize: '12px'}} />
                <RechartsTooltip content={<CustomHoverTooltip />} />
                <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }}/>
                <Line yAxisId="left" type="monotone" dataKey="accuracy" stroke="#4ade80" name="Accuracy" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                <Line yAxisId="right" type="monotone" dataKey="loss" stroke="#f87171" name="Loss" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Weights Progression Chart (Now perfectly matching the left chart) */}
        <div style={styles.chartContainer}>
          <h3 style={styles.chartTitle}>Weight Progression Across Rounds</h3>
          <div style={{ height: 280, width: '100%' }}>
            <ResponsiveContainer>
              <LineChart data={trendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="round" stroke="#94a3b8" style={{fontSize: '12px'}} />
                <YAxis stroke="#94a3b8" style={{fontSize: '12px'}} />
                <RechartsTooltip content={<CustomHoverTooltip />} />
                <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }}/>
                {weightKeys.map((key, index) => (
                  <Line 
                    key={key} 
                    type="monotone" 
                    dataKey={key} 
                    stroke={lineColors[index % lineColors.length]} 
                    strokeWidth={3}  /* Updated to match chart 1 */
                    dot={{ r: 4 }}   /* Updated to match chart 1 */
                    activeDot={{ r: 6 }} /* Updated to match chart 1 */
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>
    </section>
  );
}

function ModelVersionsPanel({ metrics, submissions, jobId, jobName }) {
  const [downloading, setDownloading] = useState(null);

  const downloadRound = async (roundNumber, format) => {
    const key = `${roundNumber}-${format}`;
    setDownloading(key);
    const ext = format === "pt" ? "pt" : "json";
    try {
      const res = await client.get(`/jobs/${jobId}/model/${roundNumber}?format=${format}`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `job_${jobId}_round_${roundNumber}_model.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || "Unknown error";
      alert(`Download failed: ${detail}`);
    } finally {
      setDownloading(null);
    }
  };

  const latestRound = metrics[metrics.length - 1].round_number;
  const emailsByRound = (submissions || []).reduce((acc, submission) => {
    const round = submission.round_number;
    if (!acc[round]) {
      acc[round] = [];
    }
    const label = submission.client_email || submission.client_label;
    if (label && !acc[round].includes(label)) {
      acc[round].push(label);
    }
    return acc;
  }, {});

  return (
    <section style={styles.panel}>
      <h2 style={styles.panelTitle}>Model Versions</h2>
      <p style={styles.muted}>
        Each aggregation round produces a versioned global model checkpoint. Download as JSON or PyTorch .pt.
      </p>
      <div style={styles.tableWrap}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Round</th>
              <th style={styles.th}>Accuracy</th>
              <th style={styles.th}>Loss</th>
              <th style={styles.th}>Total Samples</th>
              <th style={styles.th}>Clients</th>
              <th style={styles.th}>Client Emails</th>
              <th style={styles.th}>Aggregated At</th>
              <th style={styles.th} colSpan={2}>Download</th>
            </tr>
          </thead>
          <tbody>
            {[...metrics].reverse().map((m) => (
              <tr key={m.round_number}>
                <td style={styles.td}>
                  <span style={m.round_number === latestRound ? styles.latestBadge : styles.roundBadge}>
                    Round {m.round_number}
                    {m.round_number === latestRound && " ★"}
                  </span>
                </td>
                <td style={styles.td}>{formatMetric(m.accuracy)}</td>
                <td style={styles.td}>{formatMetric(m.loss)}</td>
                <td style={styles.td}>{m.total_samples ?? "—"}</td>
                <td style={styles.td}>{m.num_clients ?? "—"}</td>
                <td style={styles.td}>
                  {(emailsByRound[m.round_number] || []).length > 0
                    ? emailsByRound[m.round_number].join(", ")
                    : "—"}
                </td>
                <td style={styles.td}>
                  {m.completed_at ? new Date(m.completed_at).toLocaleString() : "—"}
                </td>
                <td style={styles.td}>
                  <button
                    style={downloading === `${m.round_number}-json` ? styles.downloadingBtn : styles.versionDownloadBtn}
                    disabled={downloading !== null}
                    onClick={() => downloadRound(m.round_number, "json")}
                    title="Download raw weights as JSON"
                  >
                    {downloading === `${m.round_number}-json` ? "…" : "↓ JSON"}
                  </button>
                </td>
                <td style={styles.td}>
                  <button
                    style={downloading === `${m.round_number}-pt` ? styles.downloadingBtn : styles.ptDownloadBtn}
                    disabled={downloading !== null}
                    onClick={() => downloadRound(m.round_number, "pt")}
                    title="Download PyTorch checkpoint (.pt)"
                  >
                    {downloading === `${m.round_number}-pt` ? "…" : "↓ .pt"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SummaryCard({ label, value }) {
  return (
    <article style={styles.summaryCard}>
      <span style={styles.summaryLabel}>{label}</span>
      <strong style={styles.summaryValue}>{value}</strong>
    </article>
  );
}

function formatMetric(value) {
  if (value === null || value === undefined) {
    return "N/A";
  }
  return Number(value).toFixed(4);
}

const styles = {
  page: { minHeight: "100vh", background: "#0f172a", fontFamily: "Arial, sans-serif" },
  content: { maxWidth: "1180px", margin: "0 auto", padding: "32px 24px" },
  backBtn: { background: "transparent", border: "1px solid #334155", color: "#cbd5e1", borderRadius: "8px", padding: "8px 12px", cursor: "pointer", marginBottom: "20px" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "16px", marginBottom: "20px" },
  eyebrowBadge: { background: '#38bdf8', color: '#0f172a', padding: '4px 8px', borderRadius: '4px', fontSize: "12px", margin: 0, fontWeight: "bold" },
  title: { color: "#f8fafc", fontSize: "32px", margin: "8px 0 4px" },
  muted: { color: "#94a3b8" },
  error: { color: "#f87171" },
  notice: { color: "#cbd5e1", background: "#164e63", padding: "10px 12px", borderRadius: "8px" },
  status: { background: "#4ade80", color: "#052e16", borderRadius: "999px", padding: "6px 14px", fontWeight: "bold", textTransform: "capitalize" },
  actions: { display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap", marginBottom: "20px" },
  downloadBtn: { padding: "10px 14px", borderRadius: "8px", background: "#38bdf8", color: "#082f49", border: "none", fontWeight: "bold", cursor: "pointer" },
  publishBtn: { padding: "10px 14px", borderRadius: "8px", background: "#4ade80", color: "#052e16", border: "none", fontWeight: "bold", cursor: "pointer" },
  published: { color: "#bbf7d0", fontWeight: "bold" },
  summaryGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "12px", marginBottom: "20px" },
  summaryCard: { background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", padding: "14px" },
  summaryLabel: { display: "block", color: "#94a3b8", fontSize: "12px", marginBottom: "6px" },
  summaryValue: { display: "block", color: "#f8fafc", fontSize: "20px" },
  panel: { background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", padding: "24px", marginBottom: "20px" },
  panelTitle: { color: "#f8fafc", margin: "0 0 8px", fontSize: "20px" },
  chartContainer: { background: "#0f172a", border: "1px solid #334155", borderRadius: "8px", padding: "16px" },
  chartTitle: { color: "#e2e8f0", fontSize: "14px", margin: "0 0 16px 0", textAlign: "center" },
  tableWrap: { overflowX: "auto", marginTop: "16px" },
  table: { width: "100%", borderCollapse: "collapse", color: "#cbd5e1", fontSize: "14px" },
  th: { textAlign: "left", color: "#94a3b8", borderBottom: "1px solid #334155", padding: "10px 8px" },
  td: { borderBottom: "1px solid #334155", padding: "10px 8px", verticalAlign: "top" },
  tdMono: { borderBottom: "1px solid #334155", padding: "10px 8px", verticalAlign: "top", fontFamily: "monospace", fontSize: "12px", minWidth: "150px" },
  versionDownloadBtn: { padding: "5px 10px", borderRadius: "6px", background: "#38bdf8", color: "#082f49", border: "none", fontWeight: "bold", cursor: "pointer", fontSize: "13px" },
  ptDownloadBtn: { padding: "5px 10px", borderRadius: "6px", background: "#a78bfa", color: "#1e1b4b", border: "none", fontWeight: "bold", cursor: "pointer", fontSize: "13px" },
  downloadingBtn: { padding: "5px 10px", borderRadius: "6px", background: "#334155", color: "#94a3b8", border: "none", fontWeight: "bold", cursor: "not-allowed", fontSize: "13px" },
  latestBadge: { background: "#4ade80", color: "#052e16", borderRadius: "4px", padding: "2px 8px", fontWeight: "bold", fontSize: "13px" },
  roundBadge: { background: "#1e293b", color: "#94a3b8", borderRadius: "4px", padding: "2px 8px", fontSize: "13px", border: "1px solid #334155" },
};
