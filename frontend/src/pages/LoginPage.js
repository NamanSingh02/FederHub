import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import client from "../api/client";

export default function LoginPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleChange = (e) =>
    setForm({ ...form, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await client.post("/auth/login", form);
      localStorage.setItem("token", res.data.access_token);
      localStorage.setItem(
        "user",
        JSON.stringify({
          role: res.data.role,
          id: res.data.user_id,
          email: res.data.email,
          status: res.data.status,
        })
      );
      sessionStorage.removeItem("token");
      sessionStorage.removeItem("user");
      navigate("/dashboard");
    } catch (err) {
      setError(err.response?.data?.detail || "Incorrect email or password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1 style={styles.title}>FederHub</h1>
        <p style={styles.subtitle}>Federated Learning Platform</p>
        <form onSubmit={handleSubmit} style={styles.form}>
          <label style={styles.label}>Email</label>
          <input
            style={styles.input}
            type="email"
            name="email"
            value={form.email}
            onChange={handleChange}
            placeholder="you@example.com"
            required
          />
          <label style={styles.label}>Password</label>
          <input
            style={styles.input}
            type="password"
            name="password"
            value={form.password}
            onChange={handleChange}
            placeholder="••••••••"
            required
          />
          {error && <p style={styles.error}>{error}</p>}
          <button style={styles.button} type="submit" disabled={loading}>
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>
        <p style={styles.registerText}>
          No account?{" "}
          <Link to="/register" style={styles.link}>
            Register here
          </Link>
        </p>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#0f172a",
    fontFamily: "Arial, sans-serif",
  },
  card: {
    background: "#1e293b",
    padding: "48px 40px",
    borderRadius: "12px",
    width: "100%",
    maxWidth: "400px",
    boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
  },
  title: { color: "#38bdf8", margin: 0, fontSize: "28px" },
  subtitle: { color: "#94a3b8", marginTop: "6px", marginBottom: "32px" },
  form: { display: "flex", flexDirection: "column", gap: "12px" },
  label: { color: "#cbd5e1", fontSize: "14px" },
  input: {
    padding: "10px 14px",
    borderRadius: "8px",
    border: "1px solid #334155",
    background: "#0f172a",
    color: "#f1f5f9",
    fontSize: "15px",
  },
  error: { color: "#f87171", fontSize: "13px", margin: 0 },
  button: {
    marginTop: "8px",
    padding: "12px",
    borderRadius: "8px",
    background: "#38bdf8",
    color: "#0f172a",
    fontWeight: "bold",
    fontSize: "15px",
    border: "none",
    cursor: "pointer",
  },
  registerText: { color: "#94a3b8", textAlign: "center", marginTop: "24px", fontSize: "14px" },
  link: { color: "#38bdf8" },
};
