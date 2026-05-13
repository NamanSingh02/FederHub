import { useNavigate } from "react-router-dom";

export default function Navbar() {
  const navigate = useNavigate();
  let user = {};
  try {
    user = JSON.parse(localStorage.getItem("user") || "{}");
  } catch {
    localStorage.removeItem("user");
  }

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    navigate("/login");
  };

  return (
    <nav style={styles.nav}>
      <span style={styles.brand} onClick={() => navigate("/dashboard")}>
        FederHub
      </span>
      <div style={styles.right}>
        {user.email && <span style={styles.email}>{user.email}</span>}
        {user.role && (
          <span style={styles.role}>{user.role.replace("_", " ")}</span>
        )}
        <button style={styles.logoutBtn} onClick={handleLogout}>
          Sign out
        </button>
      </div>
    </nav>
  );
}

const styles = {
  nav: {
    background: "#1e293b",
    borderBottom: "1px solid #334155",
    padding: "0 24px",
    height: "56px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    fontFamily: "Arial, sans-serif",
  },
  brand: {
    color: "#38bdf8",
    fontWeight: "bold",
    fontSize: "18px",
    cursor: "pointer",
    userSelect: "none",
  },
  right: { display: "flex", alignItems: "center", gap: "16px" },
  email: {
    color: "#e2e8f0",
    fontSize: "13px",
    maxWidth: "260px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  role: {
    color: "#94a3b8",
    fontSize: "13px",
    background: "#0f172a",
    padding: "4px 10px",
    borderRadius: "6px",
    textTransform: "capitalize",
  },
  logoutBtn: {
    background: "transparent",
    border: "1px solid #334155",
    color: "#94a3b8",
    padding: "6px 14px",
    borderRadius: "6px",
    cursor: "pointer",
    fontSize: "13px",
  },
};
