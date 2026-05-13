import { Navigate } from "react-router-dom";

/**
 * Wraps a route and redirects to /login if no JWT token is present.
 * Usage: <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
 */
export default function PrivateRoute({ children }) {
  const token = localStorage.getItem("token");
  return token ? children : <Navigate to="/login" replace />;
}
