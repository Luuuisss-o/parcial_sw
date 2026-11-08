import { Route, Routes, Navigate } from "react-router-dom";
import LoginPage from "./pages/Login.jsx";
import HomePage from "./pages/Home.jsx";
import useAuth from "./store/auth.js";
import { shallow } from "zustand/shallow";
import Diagram from "./pages/Diagram.jsx";

function Protected({ children }) {
  const token = useAuth(s => s.token);  // selector estable
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <Protected>
            <HomePage />
          </Protected>
        }
      /><Route
        path="/diagram/:id"
        element={
          <Protected>
            <Diagram />
          </Protected>
        }
      />


      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
