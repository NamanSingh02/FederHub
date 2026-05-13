import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import Navbar from "../components/Navbar";

export default function CreateJobPage() {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const [form, setForm] = useState({
    job_name: "",
    description: "",
    round_count: 5,
    local_epochs: 3,
    expected_clients: 1,
  });
  const [clientOperators, setClientOperators] = useState([]);
  const [selectedClientIds, setSelectedClientIds] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user.role === "client_operator") {
      navigate("/dashboard", { replace: true });
      return;
    }
    client
      .get("/auth/client-operators")
      .then((res) => setClientOperators(res.data))
      .catch(() => {});
  }, [navigate, user.role]);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const stopNumberWheel = (event) => {
    event.currentTarget.blur();
  };

  const toggleClient = (id) => {
    setSelectedClientIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!form.job_name.trim()) {
      setError("Job name is required.");
      return;
    }
    if (!form.description.trim()) {
      setError("Job description is required.");
      return;
    }
    const roundCount = parseInt(form.round_count, 10);
    const localEpochs = parseInt(form.local_epochs, 10);
    const expectedClients = parseInt(form.expected_clients, 10);

    if (!Number.isInteger(roundCount) || !Number.isInteger(localEpochs)) {
      setError("Round count and local epochs must be whole numbers.");
      return;
    }
    if (!Number.isInteger(expectedClients)) {
      setError("Expected clients must be a whole number.");
      return;
    }
    if (roundCount < 1 || localEpochs < 1) {
      setError("Round count and local epochs must be at least 1.");
      return;
    }
    if (expectedClients < 1) {
      setError("Expected clients must be at least 1.");
      return;
    }
    setLoading(true);
    try {
      await client.post("/jobs/", {
        ...form,
        round_count: roundCount,
        local_epochs: localEpochs,
        expected_clients: expectedClients,
        assigned_user_ids: selectedClientIds,
      });
      navigate("/dashboard");
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create job.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.page}>
      <Navbar />
      <div style={styles.content}>
        <div style={styles.card}>
          <h2 style={styles.heading}>Create Training Job</h2>
          <p style={styles.subtext}>
            Configure a new federated learning training job. Parameters will be
            saved to the database and passed to the orchestration engine.
          </p>

          <form onSubmit={handleSubmit} style={styles.form}>
            <div style={styles.field}>
              <label style={styles.label}>Job Name</label>
              <input
                style={styles.input}
                type="text"
                name="job_name"
                value={form.job_name}
                onChange={handleChange}
                placeholder="e.g. mnist-federated-run-1"
                required
              />
              <p style={styles.hint}>A unique name to identify this training run.</p>
            </div>

            <div style={styles.field}>
              <label style={styles.label}>Description and Feature Notes</label>
              <textarea
                style={styles.textarea}
                name="description"
                value={form.description}
                onChange={handleChange}
                placeholder="Describe the task, feature order, expected labels, and any dataset requirements clients need to know."
                required
              />
              <p style={styles.hint}>
                Include the feature order clients should use when creating their local update vector.
              </p>
            </div>

            <div style={styles.field}>
              <label style={styles.label}>Round Count</label>
              <input
                style={styles.input}
                type="number"
                name="round_count"
                value={form.round_count}
                onChange={handleChange}
                onWheel={stopNumberWheel}
                min={1}
                max={500}
              />
              <p style={styles.hint}>
                Number of global aggregation rounds. Each round collects updates
                from all clients and runs FedAvg.
              </p>
            </div>

            <div style={styles.field}>
              <label style={styles.label}>Local Epochs</label>
              <input
                style={styles.input}
                type="number"
                name="local_epochs"
                value={form.local_epochs}
                onChange={handleChange}
                onWheel={stopNumberWheel}
                min={1}
                max={200}
              />
              <p style={styles.hint}>
                How many epochs each client trains locally before sending weight
                updates to the server.
              </p>
            </div>

            <div style={styles.field}>
              <label style={styles.label}>Expected Clients Per Round</label>
              <input
                style={styles.input}
                type="number"
                name="expected_clients"
                value={form.expected_clients}
                onChange={handleChange}
                onWheel={stopNumberWheel}
                min={1}
                max={1000}
              />
              <p style={styles.hint}>
                Aggregation runs automatically after this many Client Operators
                submit local updates for the active round.
              </p>
            </div>

            {/* Client Assignment */}
            <div style={styles.field}>
              <label style={styles.label}>Assign Client Operators</label>
              <p style={styles.hint}>
                Only assigned clients can submit updates to this job. You can change assignments later from the dashboard.
              </p>
              {clientOperators.length === 0 ? (
                <p style={styles.emptyClients}>
                  No client operators registered yet. You can assign them after the job is created.
                </p>
              ) : (
                <div style={styles.clientList}>
                  {clientOperators.map((op) => (
                    <label key={op.id} style={styles.checkRow}>
                      <input
                        type="checkbox"
                        checked={selectedClientIds.includes(op.id)}
                        onChange={() => toggleClient(op.id)}
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
              {selectedClientIds.length > 0 && (
                <p style={styles.selectionCount}>
                  {selectedClientIds.length} client{selectedClientIds.length !== 1 ? "s" : ""} selected
                </p>
              )}
            </div>

            {/* Summary preview */}
            <div style={styles.summary}>
              <span style={styles.summaryLabel}>Summary:</span>
              <span style={styles.summaryText}>
                <strong style={styles.highlight}>{form.round_count}</strong> rounds ×{" "}
                <strong style={styles.highlight}>{form.local_epochs}</strong> local epochs ×{" "}
                <strong style={styles.highlight}>{form.expected_clients}</strong> clients
              </span>
            </div>

            {error && <p style={styles.error}>{error}</p>}

            <div style={styles.actions}>
              <button
                type="button"
                style={styles.cancelBtn}
                onClick={() => navigate("/dashboard")}
              >
                Cancel
              </button>
              <button type="submit" style={styles.submitBtn} disabled={loading}>
                {loading ? "Creating…" : "Create Job"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: { minHeight: "100vh", background: "#0f172a", fontFamily: "Arial, sans-serif" },
  content: { maxWidth: "600px", margin: "0 auto", padding: "40px 24px" },
  card: {
    background: "#1e293b",
    borderRadius: "12px",
    padding: "36px",
    border: "1px solid #334155",
  },
  heading: { color: "#f1f5f9", margin: "0 0 8px 0", fontSize: "22px" },
  subtext: { color: "#94a3b8", fontSize: "14px", marginBottom: "28px" },
  form: { display: "flex", flexDirection: "column", gap: "20px" },
  field: { display: "flex", flexDirection: "column", gap: "4px" },
  label: { color: "#cbd5e1", fontSize: "14px", fontWeight: "bold" },
  input: {
    padding: "10px 14px",
    borderRadius: "8px",
    border: "1px solid #334155",
    background: "#0f172a",
    color: "#f1f5f9",
    fontSize: "15px",
  },
  textarea: {
    minHeight: "110px",
    padding: "10px 14px",
    borderRadius: "8px",
    border: "1px solid #334155",
    background: "#0f172a",
    color: "#f1f5f9",
    fontSize: "15px",
    resize: "vertical",
  },
  hint: { color: "#475569", fontSize: "12px", margin: "4px 0 0 0" },
  clientList: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
    marginTop: "8px",
    padding: "12px",
    background: "#0f172a",
    borderRadius: "8px",
    border: "1px solid #334155",
    maxHeight: "220px",
    overflowY: "auto",
  },
  checkRow: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "8px 10px",
    borderRadius: "6px",
    cursor: "pointer",
    background: "#1e293b",
    border: "1px solid #334155",
  },
  checkbox: { width: "16px", height: "16px", accentColor: "#38bdf8", cursor: "pointer" },
  checkEmail: { flex: 1, color: "#e2e8f0", fontSize: "14px" },
  checkStatus: { fontSize: "11px", fontWeight: "bold" },
  emptyClients: {
    color: "#64748b",
    fontSize: "13px",
    padding: "12px",
    background: "#0f172a",
    borderRadius: "8px",
    border: "1px solid #334155",
    margin: "4px 0 0",
  },
  selectionCount: { color: "#38bdf8", fontSize: "12px", margin: "6px 0 0" },
  summary: {
    background: "#0f172a",
    borderRadius: "8px",
    padding: "14px 16px",
    display: "flex",
    gap: "10px",
    alignItems: "center",
    border: "1px solid #334155",
  },
  summaryLabel: { color: "#94a3b8", fontSize: "13px" },
  summaryText: { color: "#cbd5e1", fontSize: "14px" },
  highlight: { color: "#38bdf8" },
  error: { color: "#f87171", fontSize: "13px", margin: 0 },
  actions: { display: "flex", gap: "12px", justifyContent: "flex-end" },
  cancelBtn: {
    padding: "10px 20px",
    borderRadius: "8px",
    background: "transparent",
    color: "#94a3b8",
    border: "1px solid #334155",
    cursor: "pointer",
    fontSize: "14px",
  },
  submitBtn: {
    padding: "10px 24px",
    borderRadius: "8px",
    background: "#38bdf8",
    color: "#0f172a",
    fontWeight: "bold",
    border: "none",
    cursor: "pointer",
    fontSize: "14px",
  },
};
