import { Routes, Route, Outlet } from "react-router-dom";

import { KioskProvider } from "./context/KioskContext";

import KioskShell from "./components/kiosk/KioskShell";

import KioskTTS from "./components/kiosk/KioskTTS";

// Patient pages
import Welcome from "./pages/patient/Welcome";
import Identify from "./pages/patient/Identify";
import Consent from "./pages/patient/Consent";
import Interview from "./pages/patient/Interview";
import Documents from "./pages/patient/Documents";
import Processing from "./pages/patient/Processing";
import Confirmation from "./pages/patient/Confirmation";
import ModeSelection from "./pages/patient/ModeSelection";

// Doctor pages
import DoctorLogin from "./pages/doctor/Login";
import DoctorDashboard from "./pages/doctor/Dashboard";
import SessionReview from "./pages/doctor/SessionReview";
import EditSummary from "./pages/doctor/EditSummary";


/* ============================================================
   PATIENT / KIOSK LAYOUT
   ============================================================ */

function KioskLayout() {
  return (
    <KioskShell>
      <KioskTTS />
      <Outlet />
    </KioskShell>
  );
}


/* ============================================================
   APP
   ============================================================ */

export default function App() {
  return (
    <KioskProvider>

      <Routes>

        {/* ==================================================
            PATIENT / KIOSK FLOW
            ================================================== */}

        <Route element={<KioskLayout />}>

          <Route
            path="/"
            element={<Welcome />}
          />

          <Route
            path="/identify"
            element={<Identify />}
          />

          <Route
            path="/consent"
            element={<Consent />}
          />

          <Route
            path="/mode"
            element={<ModeSelection />}
          />

          <Route
            path="/interview"
            element={<Interview />}
          />

          <Route
            path="/documents"
            element={<Documents />}
          />

          <Route
            path="/processing"
            element={<Processing />}
          />

          <Route
            path="/confirmation"
            element={<Confirmation />}
          />

        </Route>


        {/* ==================================================
            DOCTOR FLOW
            No kiosk header here
            ================================================== */}

        <Route
          path="/doctor/login"
          element={<DoctorLogin />}
        />

        <Route
          path="/doctor"
          element={<DoctorDashboard />}
        />

        <Route
          path="/doctor/session/:sessionId"
          element={<SessionReview />}
        />

        <Route
          path="/doctor/sessions/:sessionId"
          element={<SessionReview />}
        />

        <Route
          path="/doctor/session/:sessionId/edit-summary"
          element={<EditSummary />}
        />

        <Route
          path="/doctor/sessions/:sessionId/edit-summary"
          element={<EditSummary />}
        />

      </Routes>

    </KioskProvider>
  );
}