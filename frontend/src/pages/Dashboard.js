import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import Navbar from "../components/Navbar";

const STATUS_COLORS = {
  draft: "#94a3b8",
  scheduled: "#fbbf24",
  running: "#38bdf8",
  completed: "#4ade80",
  failed: "#f87171",
};

const ROLE_LABELS = {
  platform_admin: "Platform Admin",
  ml_engineer: "ML Engineer",
  client_operator: "Client Operator",
};

export default function Dashboard() {
  const navigate = useNavigate();
  const storedUser = useMemo(
    () => JSON.parse(localStorage.getItem("user") || "{}"),
    []
  );
  const [user, setUser] = useState(storedUser);
  const [jobs, setJobs] = useState([]);
  const [users, setUsers] = useState([]);
  const [clientOperators, setClientOperators] = useState([]);
  const [metricsByJob, setMetricsByJob] = useState({});
  const [submissionsByJob, setSubmissionsByJob] = useState({});
  const [submissionForms, setSubmissionForms] = useState({});
  const [assigningJobId, setAssigningJobId] = useState(null);
  const [pendingAssignments, setPendingAssignments] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");

  const canManageJobs = user.role === "platform_admin" || user.role === "ml_engineer";
  const isAdmin = user.role === "platform_admin";
  const isClient = user.role === "client_operator";

  const loadDashboard = async () => {
    setError("");
    setLoading(true);

    try {
      const profileRes = await client.get("/auth/me");
      const profile = profileRes.data;
      const nextUser = {
        id: profile.id,
        email: profile.email,
        role: profile.role,
        status: profile.status,
      };
      setUser(nextUser);
      localStorage.setItem("user", JSON.stringify(nextUser));

      const jobsRes = await client.get("/jobs/");
      setJobs(jobsRes.data);

      // Initialise pending assignment selections from each job's current assignments
      setPendingAssignments((prev) => {
        const next = { ...prev };
        for (const job of jobsRes.data) {
          if (next[job.id] === undefined) {
            next[job.id] = job.assigned_user_ids || [];
          }
        }
        return next;
      });

      const metricPairs = await Promise.all(
        jobsRes.data.map(async (job) => {
          try {
            const metricsRes = await client.get(`/jobs/${job.id}/metrics`);
            return [job.id, metricsRes.data];
          } catch {
            return [job.id, []];
          }
        })
      );
      setMetricsByJob(Object.fromEntries(metricPairs));

      const submissionPairs = await Promise.all(
        jobsRes.data.map(async (job) => {
          try {
            const submissionsRes = await client.get(`/jobs/${job.id}/submissions`);
            return [job.id, submissionsRes.data];
          } catch {
            return [job.id, []];
          }
        })
      );
      setSubmissionsByJob(Object.fromEntries(submissionPairs));
      setSubmissionForms((current) => {
        const next = { ...current };
        for (const job of jobsRes.data) {
          if (!next[job.id]) {
            next[job.id] = buildDefaultSubmissionForm(profile.email, job);
          }
        }
        return next;
      });

      if (profile.role === "platform_admin") {
        const usersRes = await client.get("/auth/users");
        setUsers(usersRes.data);
      }

      if (profile.role === "platform_admin" || profile.role === "ml_engineer") {
        try {
          const clientOpsRes = await client.get("/auth/client-operators");
          setClientOperators(clientOpsRes.data);
        } catch {}
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startJob = async (jobId) => {
    setActionMessage("");
    try {
      const res = await client.post(`/jobs/${jobId}/start`);
      setActionMessage(res.data.message);
      setJobs((current) =>
        current.map((job) =>
          job.id === jobId ? { ...job, status: res.data.status } : job
        )
      );
    } catch (err) {
      setActionMessage(err.response?.data?.detail || "Failed to start job.");
    }
  };

  const publishJob = async (jobId) => {
    setActionMessage("");
    try {
      const res = await client.post(`/jobs/${jobId}/publish`);
      setActionMessage(res.data.message);
      setJobs((current) =>
        current.map((job) =>
          job.id === jobId ? { ...job, results_published: true } : job
        )
      );
    } catch (err) {
      setActionMessage(err.response?.data?.detail || "Failed to publish results.");
    }
  };

  const deleteJob = async (jobId, jobName) => {
    const ok = window.confirm(`Delete job "${jobName}"? This also removes its round metrics.`);
    if (!ok) return;

    setActionMessage("");
    try {
      await client.delete(`/jobs/${jobId}`);
      setJobs((current) => current.filter((job) => job.id !== jobId));
      setMetricsByJob((current) => {
        const next = { ...current };
        delete next[jobId];
        return next;
      });
      setActionMessage(`Deleted job "${jobName}".`);
    } catch (err) {
      setActionMessage(err.response?.data?.detail || "Failed to delete job.");
    }
  };

  const updateSubmissionForm = (jobId, field, value) => {
    setSubmissionForms((current) => ({
      ...current,
      [jobId]: {
        ...(current[jobId] || {}),
        [field]: value,
      },
    }));
  };

  const submitClientUpdate = async (job) => {
    const form = submissionForms[job.id] || buildDefaultSubmissionForm(user.email, job);
    const weights = parseWeights(form.weights);
    if (weights.length === 0) {
      setActionMessage("Enter at least one numeric model weight.");
      return;
    }


    setActionMessage("");
    try {
      const res = await client.post(`/jobs/${job.id}/submissions`, {
        client_label: form.client_label || user.email,
        sample_count: Number(form.sample_count),
        accuracy: form.accuracy === "" ? null : Number(form.accuracy),
        loss: form.loss === "" ? null : Number(form.loss),
        weights,
      });
      setActionMessage(res.data.message);
      await loadDashboard();
    } catch (err) {
      setActionMessage(err.response?.data?.detail || "Failed to submit client update.");
    }
  };

  const toggleAssignment = (jobId, userId) => {
    setPendingAssignments((prev) => {
      const current = prev[jobId] || [];
      return {
        ...prev,
        [jobId]: current.includes(userId)
          ? current.filter((id) => id !== userId)
          : [...current, userId],
      };
    });
  };

  const saveAssignments = async (jobId) => {
    setActionMessage("");
    try {
      const userIds = pendingAssignments[jobId] || [];
      await client.post(`/jobs/${jobId}/assign`, { user_ids: userIds });
      setJobs((current) =>
        current.map((job) =>
          job.id === jobId ? { ...job, assigned_user_ids: userIds } : job
        )
      );
      setAssigningJobId(null);
      setActionMessage(`Client assignments updated for job #${jobId}.`);
    } catch (err) {
      setActionMessage(err.response?.data?.detail || "Failed to save assignments.");
    }
  };

  const updateUserStatus = async (userId, status) => {
    setActionMessage("");
    try {
      const res = await client.patch(`/auth/users/${userId}/status`, { status });
      setUsers((current) =>
        current.map((item) => (item.id === userId ? res.data : item))
      );
      setActionMessage(`Updated ${res.data.email} to ${res.data.status}.`);
    } catch (err) {
      setActionMessage(err.response?.data?.detail || "Failed to update user status.");
    }
  };

  return (
    <div style={styles.page}>
      <Navbar />
      <div style={styles.content}>
        <section style={styles.topBand}>
          <div>
            <h2 style={styles.heading}>{ROLE_LABELS[user.role] || "Dashboard"}</h2>
            <p style={styles.subtext}>{user.email}</p>
          </div>
          {canManageJobs && (
            <button style={styles.createBtn} onClick={() => navigate("/jobs/new")}>
              + Create Job
            </button>
          )}
        </section>

        {isClient && <ClientOperatorPanel />}
        {isAdmin && (
          <AdminUsersPanel users={users} onStatusChange={updateUserStatus} />
        )}

        <section style={styles.sectionHeader}>
          <h3 style={styles.sectionTitle}>
            {isClient ? "Available Federated Jobs" : "Training Jobs"}
          </h3>
          <button style={styles.refreshBtn} onClick={loadDashboard}>
            Refresh
          </button>
        </section>

        {loading && <p style={styles.muted}>Loading dashboard...</p>}
        {error && <p style={styles.error}>{error}</p>}
        {actionMessage && <p style={styles.notice}>{actionMessage}</p>}

        {!loading && jobs.length === 0 && (
          <div style={styles.emptyState}>
            <p style={styles.muted}>No jobs have been created yet.</p>
            {canManageJobs && (
              <button style={styles.createBtn} onClick={() => navigate("/jobs/new")}>
                Create your first job
              </button>
            )}
          </div>
        )}

        <div style={styles.grid}>
          {jobs.map((job) => {
            const metrics = metricsByJob[job.id] || [];
            const submissions = submissionsByJob[job.id] || [];
            const latestMetric = metrics[metrics.length - 1];
            const isStarted = job.status === "running" || job.status === "scheduled";
            const isCompleted = job.status === "completed";
            const activeRound = job.current_round || 0;
            const activeRoundSubmissions = submissions.filter(
              (item) => item.round_number === activeRound && item.status === "accepted"
            );

            return (
              <article key={job.id} style={styles.card}>
                <div style={styles.cardTop}>
                  <div>
                    <span style={styles.jobName}>{job.job_name}</span>
                    <p style={styles.jobId}>Job ID: {job.id}</p>
                  </div>
                  <span
                    style={{
                      ...styles.badge,
                      background: STATUS_COLORS[job.status] || "#94a3b8",
                    }}
                  >
                    {job.status}
                  </span>
                </div>

                <div style={styles.metaStack}>
                  <span>Created by: <strong>{job.creator_email || "Unknown"}</strong></span>
                  <span>Active round: <strong>{job.status === "completed" ? "Complete" : activeRound || "Not started"}</strong></span>
                  <span>Expected clients: <strong>{job.expected_clients}</strong></span>
                  <span>Pending updates: <strong>{isCompleted ? "Complete" : `${activeRoundSubmissions.length}/${job.expected_clients}`}</strong></span>
                  <span>Rounds: <strong>{job.round_count}</strong></span>
                  <span>Local epochs: <strong>{job.local_epochs}</strong></span>
                  <span>Completed rounds: <strong>{metrics.length}</strong></span>
                  <span>Participating clients: <strong>{latestMetric?.num_clients ?? "N/A"}</strong></span>
                  <span>Total samples: <strong>{latestMetric?.total_samples ?? "N/A"}</strong></span>
                </div>

                {job.description && (
                  <p style={styles.descriptionText}>{job.description}</p>
                )}

                {canManageJobs || job.results_published ? (
                  <button
                    style={styles.detailBtnFull}
                    onClick={() => navigate(`/jobs/${job.id}`)}
                  >
                    View Live Dashboard & Details
                  </button>
                ) : (
                  <p style={styles.clientNote}>
                    Live dashboard and model details will be available after the ML Engineer publishes final results.
                  </p>
                )}

                {isCompleted && (canManageJobs || job.results_published) && (
                  <CompletedResults
                    job={job}
                    metrics={metrics}
                    submissions={submissions}
                  />
                )}

                <p style={styles.cardDate}>
                  Created: {new Date(job.created_at).toLocaleString()}
                </p>

                {canManageJobs ? (
                  <>
                    <div style={styles.cardActions}>
                      {!isCompleted && (
                        <button
                          style={styles.startBtn}
                          onClick={() => startJob(job.id)}
                          disabled={isStarted}
                        >
                          {isStarted ? "Started" : "Start Orchestration"}
                        </button>
                      )}
                      {isCompleted && !job.results_published && (
                        <button
                          style={styles.publishBtn}
                          onClick={() => publishJob(job.id)}
                        >
                          Publish Results
                        </button>
                      )}
                      {isCompleted && job.results_published && (
                        <span style={styles.publishedBadge}>Published</span>
                      )}
                      <button
                        style={styles.assignBtn}
                        onClick={() =>
                          setAssigningJobId(
                            assigningJobId === job.id ? null : job.id
                          )
                        }
                      >
                        {assigningJobId === job.id ? "Close" : "Assign Clients"}
                      </button>
                      <button
                        style={styles.deleteBtn}
                        onClick={() => deleteJob(job.id, job.job_name)}
                      >
                        Delete
                      </button>
                    </div>
                    {assigningJobId === job.id && (
                      <AssignClientsPanel
                        job={job}
                        clientOperators={clientOperators}
                        selected={pendingAssignments[job.id] || []}
                        onToggle={(userId) => toggleAssignment(job.id, userId)}
                        onSave={() => saveAssignments(job.id)}
                      />
                    )}
                  </>
                ) : (
                  <>
                    <ClientSubmissionPanel
                      job={job}
                      form={submissionForms[job.id] || buildDefaultSubmissionForm(user.email, job)}
                      submissions={submissions}
                      onChange={(field, value) => updateSubmissionForm(job.id, field, value)}
                      onSubmit={() => submitClientUpdate(job)}
                    />
                  </>
                )}
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function buildDefaultSubmissionForm(email, job) {
  return {
    client_label: email || "Client Node",
    sample_count: "",
    accuracy: "",
    loss: "",
    weights: "",
  };
}

function parseWeights(text) {
  return String(text || "")
    .split(/[,\s]+/)
    .map((value) => value.trim())
    .filter(Boolean)
    .map(Number)
    .filter((value) => Number.isFinite(value));
}

function parseSnapshot(metric) {
  if (!metric?.global_weights_snapshot) {
    return null;
  }
  try {
    return JSON.parse(metric.global_weights_snapshot);
  } catch {
    return null;
  }
}

function downloadJobReport(job, metrics, submissions) {
  const report = {
    job,
    final_metric: metrics[metrics.length - 1] || null,
    rounds: metrics,
    submissions,
    exported_at: new Date().toISOString(),
  };
  const blob = new Blob([JSON.stringify(report, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `federhub-job-${job.id}-report.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function ClientOperatorPanel() {
  const handleDownloadApp = (osType) => {
    const apiBase = process.env.REACT_APP_API_BASE_URL || "http://127.0.0.1:8000";
    window.open(`${apiBase}/download/client/${osType}`, "_blank");
  };

  return (
    <section style={{...styles.infoPanel, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '20px'}}>
      <div>
        <h3 style={styles.panelTitle}>Client Operator Workspace</h3>
        <div style={styles.operatorGrid}>
          <div>
            <span style={styles.operatorLabel}>Workflow</span>
            <strong style={styles.operatorValue}>Choose a running job and submit a local model update.</strong>
          </div>
          <div>
            <span style={styles.operatorLabel}>Privacy</span>
            <strong style={styles.operatorValue}>Only weights, metrics, and sample count are submitted.</strong>
          </div>
          <div>
            <span style={styles.operatorLabel}>Aggregation</span>
            <strong style={styles.operatorValue}>FedAvg runs automatically when enough clients submit.</strong>
          </div>
        </div>
      </div>
      <div style={{ background: '#0f172a', padding: '16px', borderRadius: '8px', border: '1px solid #334155', maxWidth: '300px' }}>
        <h4 style={{ margin: '0 0 8px 0', color: '#f8fafc', fontSize: '15px' }}>Desktop Environment</h4>
        <p style={{ margin: '0 0 16px 0', color: '#94a3b8', fontSize: '13px', lineHeight: '1.4' }}>
          For local PyTorch training with secure data isolation, download the Edge Node app.
        </p>
        <div style={{display: 'flex', gap: '10px'}}>
          <button style={{...styles.downloadAppBtn, background: '#e2e8f0', color: '#0f172a'}} onClick={() => handleDownloadApp('mac')}>
             Mac (.dmg)
          </button>
          <button style={{...styles.downloadAppBtn, background: '#38bdf8', color: '#0f172a'}} onClick={() => handleDownloadApp('windows')}>
            ⊞ Win (.exe)
          </button>
        </div>
      </div>
    </section>
  );
}

function CompletedResults({ job, metrics, submissions }) {
  const finalMetric = metrics[metrics.length - 1];
  const snapshot = parseSnapshot(finalMetric);
  const weightsPreview = snapshot?.weights_preview || [];

  return (
    <section style={styles.resultsBox}>
      <div style={styles.resultsHeader}>
        <strong>Final Global Model Ready</strong>
        <button
          style={styles.reportBtn}
          onClick={() => downloadJobReport(job, metrics, submissions)}
        >
          Download Report
        </button>
      </div>
      <div style={styles.resultsGrid}>
        <span>FedAvg rounds: <strong>{metrics.length}</strong></span>
        <span>Final accuracy: <strong>{formatMetric(finalMetric?.accuracy)}</strong></span>
        <span>Final loss: <strong>{formatMetric(finalMetric?.loss)}</strong></span>
        <span>Samples used: <strong>{finalMetric?.total_samples ?? "N/A"}</strong></span>
      </div>
      {weightsPreview.length > 0 && (
        <p style={styles.weightsPreview}>
          Weight preview: {weightsPreview.join(", ")}
        </p>
      )}
    </section>
  );
}

function formatMetric(value) {
  if (value === null || value === undefined) {
    return "N/A";
  }
  return Number(value).toFixed(4);
}

function ClientSubmissionPanel({ job, form, submissions, onChange, onSubmit }) {
  // State strictly for the manual override toggle
  const [showManualForm, setShowManualForm] = useState(false);

  const alreadySubmitted = submissions.some(
    (item) => item.round_number === job.current_round
  );

  if (job.status === "draft") {
    return (
      <p style={styles.clientNote}>
        This job is waiting for an ML Engineer or Admin to start orchestration.
      </p>
    );
  }

  if (job.status === "completed") {
    return <p style={styles.clientNote}>This job is complete. No more updates are needed.</p>;
  }

  if (alreadySubmitted) {
    return (
      <p style={styles.clientNote}>
        Your update for round {job.current_round} has been submitted. Refresh after aggregation to continue.
      </p>
    );
  }

  return (
    <div style={styles.submitBox}>
      
      {/* BUTTON 1: The Primary Edge Node / gRPC Trigger */}
      <div style={{ marginBottom: "16px", paddingBottom: "16px", borderBottom: "1px solid #334155" }}>
        <p style={{ color: "#e2e8f0", margin: "0 0 8px 0", fontSize: "14px", fontWeight: "bold" }}>
          Round {job.current_round} is active.
        </p>
        <p style={{ color: "#94a3b8", margin: "0 0 12px 0", fontSize: "13px", lineHeight: "1.4" }}>
          Run local training in your Edge Node App. Once the gRPC server receives your weights, click below to generate graphs.
        </p>
        <button 
          style={{ ...styles.submitUpdateBtn, width: "100%", background: "#4ade80", color: "#052e16" }} 
          onClick={() => window.location.reload()}
        >
          Sync gRPC Results & Generate Graph
        </button>
      </div>

      {/* BUTTON 2: The Manual Override Toggle */}
      <button 
        style={{ ...styles.refreshBtn, width: "100%", fontSize: "13px", padding: "8px", marginBottom: showManualForm ? "14px" : "0" }}
        onClick={() => setShowManualForm(!showManualForm)}
      >
        {showManualForm ? "Cancel Manual Override" : "Manual Override (Fallback)"}
      </button>

      {/* The Hidden Manual Form & Its Submit Button */}
      {showManualForm && (
        <div style={{ display: "grid", gap: "10px" }}>
          <label style={styles.formLabel}>
            Client label
            <input
              style={styles.formInput}
              value={form.client_label}
              onChange={(event) => onChange("client_label", event.target.value)}
            />
          </label>
          <div style={styles.twoCols}>
            <label style={styles.formLabel}>
              Sample count
              <input
                style={styles.formInput}
                type="number"
                min="1"
                value={form.sample_count}
                onChange={(event) => onChange("sample_count", event.target.value)}
              />
            </label>
            <label style={styles.formLabel}>
              Accuracy
              <input
                style={styles.formInput}
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={form.accuracy}
                onChange={(event) => onChange("accuracy", event.target.value)}
              />
            </label>
          </div>
          <label style={styles.formLabel}>
            Loss
            <input
              style={styles.formInput}
              type="number"
              min="0"
              step="0.01"
              value={form.loss}
              onChange={(event) => onChange("loss", event.target.value)}
            />
          </label>
          <label style={styles.formLabel}>
            Model weights
            <textarea
              style={styles.textarea}
              value={form.weights}
              onChange={(event) => onChange("weights", event.target.value)}
            />
          </label>
          
          <button style={styles.submitUpdateBtn} onClick={onSubmit}>
            Submit Manual Weights
          </button>
        </div>
      )}
      
    </div>
  );
}


function AssignClientsPanel({ job, clientOperators, selected, onToggle, onSave }) {
  return (
    <div style={styles.assignPanel}>
      <p style={styles.assignTitle}>Assign Client Operators to this job</p>
      <p style={styles.assignHint}>
        Only assigned clients can submit updates. Currently{" "}
        <strong>{selected.length}</strong> assigned.
      </p>
      {clientOperators.length === 0 ? (
        <p style={{ color: "#64748b", fontSize: "13px" }}>
          No client operators registered yet.
        </p>
      ) : (
        <div style={styles.assignList}>
          {clientOperators.map((op) => (
            <label key={op.id} style={styles.checkRow}>
              <input
                type="checkbox"
                checked={selected.includes(op.id)}
                onChange={() => onToggle(op.id)}
                style={styles.checkbox}
              />
              <span style={styles.checkEmail}>{op.email}</span>
              <span
                style={{
                  ...styles.checkStatus,
                  color: op.status === "active" ? "#4ade80" : "#f87171",
                }}
              >
                {op.status}
              </span>
            </label>
          ))}
        </div>
      )}
      <button style={{ ...styles.submitUpdateBtn, marginTop: "10px" }} onClick={onSave}>
        Save Assignments
      </button>
    </div>
  );
}

function AdminUsersPanel({ users, onStatusChange }) {
  return (
    <section style={styles.infoPanel}>
      <h3 style={styles.panelTitle}>User Management</h3>
      <div style={styles.tableWrap}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Email</th>
              <th style={styles.th}>Role</th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((item) => (
              <tr key={item.id}>
                <td style={styles.td}>{item.email}</td>
                <td style={styles.td}>{item.role.replace("_", " ")}</td>
                <td style={styles.td}>{item.status}</td>
                <td style={styles.tdActions}>
                  <button style={styles.smallBtn} onClick={() => onStatusChange(item.id, "active")}>Activate</button>
                  <button style={styles.smallDangerBtn} onClick={() => onStatusChange(item.id, "deactivated")}>Deactivate</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const styles = {
  page: { minHeight: "100vh", background: "#0f172a", fontFamily: "Arial, sans-serif" },
  content: { maxWidth: "1120px", margin: "0 auto", padding: "32px 24px" },
  topBand: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: "16px", marginBottom: "24px" },
  heading: { color: "#f1f5f9", fontSize: "24px", margin: 0 },
  subtext: { color: "#94a3b8", fontSize: "14px", margin: "6px 0 0" },
  createBtn: { padding: "10px 20px", borderRadius: "8px", background: "#38bdf8", color: "#0f172a", fontWeight: "bold", border: "none", cursor: "pointer", fontSize: "14px" },
  sectionHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", margin: "24px 0 16px" },
  sectionTitle: { color: "#e2e8f0", fontSize: "18px", margin: 0 },
  refreshBtn: { padding: "8px 14px", borderRadius: "8px", background: "transparent", color: "#cbd5e1", border: "1px solid #334155", cursor: "pointer" },
  muted: { color: "#94a3b8" },
  error: { color: "#f87171" },
  notice: { color: "#cbd5e1", background: "#164e63", padding: "10px 12px", borderRadius: "8px" },
  emptyState: { textAlign: "center", padding: "60px 0" },
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "16px" },
  card: { background: "#1e293b", borderRadius: "8px", padding: "20px", border: "1px solid #334155" },
  cardTop: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px", marginBottom: "14px" },
  jobName: { color: "#f1f5f9", fontWeight: "bold", fontSize: "16px" },
  jobId: { color: "#64748b", fontSize: "12px", margin: "4px 0 0" },
  badge: { padding: "4px 10px", borderRadius: "999px", fontSize: "12px", color: "#0f172a", fontWeight: "bold", whiteSpace: "nowrap" },
  metaStack: { display: "grid", gap: "7px", color: "#94a3b8", fontSize: "14px", marginBottom: "12px" },
  descriptionText: { color: "#cbd5e1", fontSize: "13px", lineHeight: 1.45, background: "#0f172a", border: "1px solid #334155", borderRadius: "8px", padding: "10px", margin: "10px 0", whiteSpace: "pre-wrap" },
  cardDate: { color: "#64748b", fontSize: "12px", margin: 0 },
  cardActions: { display: "flex", gap: "10px", marginTop: "14px", flexWrap: "wrap" },
  startBtn: { padding: "9px 14px", borderRadius: "8px", background: "#4ade80", color: "#052e16", fontWeight: "bold", border: "none", cursor: "pointer", fontSize: "13px" },
  publishBtn: { padding: "9px 14px", borderRadius: "8px", background: "#7c3aed", color: "#ede9fe", fontWeight: "bold", border: "none", cursor: "pointer", fontSize: "13px" },
  publishedBadge: { padding: "9px 14px", borderRadius: "8px", background: "#1e1b4b", color: "#a5b4fc", fontWeight: "bold", fontSize: "13px", border: "1px solid #3730a3" },
  deleteBtn: { padding: "9px 14px", borderRadius: "8px", background: "#7f1d1d", color: "#fecaca", fontWeight: "bold", border: "1px solid #991b1b", cursor: "pointer", fontSize: "13px" },
  detailBtnFull: { width: "100%", padding: "10px", borderRadius: "8px", background: "#38bdf8", color: "#082f49", fontWeight: "bold", border: "none", cursor: "pointer", fontSize: "14px", margin: "10px 0" },
  resultsBox: { background: "#0f172a", border: "1px solid #14532d", borderRadius: "8px", padding: "12px", margin: "12px 0" },
  resultsHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px", color: "#bbf7d0", fontSize: "14px", marginBottom: "10px" },
  resultsGrid: { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "8px", color: "#cbd5e1", fontSize: "13px" },
  reportBtn: { padding: "6px 10px", borderRadius: "6px", border: "1px solid #166534", background: "#14532d", color: "#dcfce7", cursor: "pointer", fontSize: "12px", fontWeight: "bold" },
  weightsPreview: { color: "#94a3b8", fontSize: "12px", margin: "10px 0 0", overflowWrap: "anywhere" },
  clientNote: { color: "#cbd5e1", fontSize: "13px", margin: "14px 0 0" },
  infoPanel: { background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", padding: "18px", marginBottom: "18px" },
  panelTitle: { color: "#f1f5f9", fontSize: "16px", margin: "0 0 14px" },
  operatorGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "12px" },
  operatorLabel: { display: "block", color: "#94a3b8", fontSize: "12px", marginBottom: "4px" },
  operatorValue: { display: "block", color: "#e2e8f0", fontSize: "14px", overflowWrap: "anywhere" },
  tableWrap: { overflowX: "auto" },
  table: { width: "100%", borderCollapse: "collapse", color: "#cbd5e1", fontSize: "14px" },
  th: { textAlign: "left", color: "#94a3b8", borderBottom: "1px solid #334155", padding: "8px" },
  td: { borderBottom: "1px solid #334155", padding: "8px" },
  tdActions: { borderBottom: "1px solid #334155", padding: "8px", display: "flex", gap: "8px", flexWrap: "wrap" },
  smallBtn: { padding: "6px 10px", borderRadius: "6px", border: "none", background: "#38bdf8", color: "#082f49", cursor: "pointer" },
  smallDangerBtn: { padding: "6px 10px", borderRadius: "6px", border: "none", background: "#991b1b", color: "#fee2e2", cursor: "pointer" },
  submitBox: { display: "grid", gap: "10px", marginTop: "14px", paddingTop: "14px", borderTop: "1px solid #334155" },
  twoCols: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" },
  formLabel: { display: "grid", gap: "5px", color: "#94a3b8", fontSize: "12px", fontWeight: "bold" },
  formInput: { padding: "8px 10px", borderRadius: "6px", border: "1px solid #334155", background: "#0f172a", color: "#e2e8f0", fontSize: "13px" },
  textarea: { minHeight: "68px", padding: "8px 10px", borderRadius: "6px", border: "1px solid #334155", background: "#0f172a", color: "#e2e8f0", fontSize: "13px", resize: "vertical" },
  submitUpdateBtn: { padding: "9px 14px", borderRadius: "8px", background: "#38bdf8", color: "#082f49", fontWeight: "bold", border: "none", cursor: "pointer", fontSize: "13px" },
  downloadAppBtn: { padding: "6px 12px", borderRadius: "6px", border: "none", fontSize: "12px", fontWeight: "bold", cursor: "pointer", transition: "opacity 0.2s" },
  assignBtn: { padding: "9px 14px", borderRadius: "8px", background: "#1e3a5f", color: "#93c5fd", fontWeight: "bold", border: "1px solid #1d4ed8", cursor: "pointer", fontSize: "13px" },
  assignPanel: { marginTop: "12px", padding: "14px", background: "#0f172a", border: "1px solid #1d4ed8", borderRadius: "8px" },
  assignTitle: { color: "#93c5fd", fontSize: "14px", fontWeight: "bold", margin: "0 0 4px" },
  assignHint: { color: "#64748b", fontSize: "12px", margin: "0 0 10px" },
  assignList: { display: "flex", flexDirection: "column", gap: "6px", maxHeight: "180px", overflowY: "auto", marginBottom: "4px" },
  checkRow: { display: "flex", alignItems: "center", gap: "10px", padding: "7px 10px", borderRadius: "6px", cursor: "pointer", background: "#1e293b", border: "1px solid #334155" },
  checkbox: { width: "15px", height: "15px", accentColor: "#38bdf8", cursor: "pointer" },
  checkEmail: { flex: 1, color: "#e2e8f0", fontSize: "13px" },
  checkStatus: { fontSize: "11px", fontWeight: "bold" },
};
