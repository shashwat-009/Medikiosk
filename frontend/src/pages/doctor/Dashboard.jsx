import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  api,
  clearDoctorAccessToken,
} from "../../services/api";
import "./doctor.css";

export default function Dashboard() {
  const navigate = useNavigate();

  const doctorId = sessionStorage.getItem("doctorId");

  const [doctor, setDoctor] = useState(null);
  const [sessions, setSessions] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  /* ============================================================
     LOAD DOCTOR + SESSIONS
     ============================================================ */

  useEffect(() => {
    if (!doctorId) {
      navigate("/doctor/login");
      return;
    }

    loadDashboard();
  }, [doctorId, navigate]);

  async function loadDashboard() {
    try {
      setLoading(true);
      setError("");

      const [doctorData, sessionsData] = await Promise.all([
        api(`/doctors/${doctorId}`, {
          auth: "doctor",
        }),
        api(`/doctors/${doctorId}/sessions`, {
          auth: "doctor",
        }),
      ]);

      setDoctor(doctorData);

      const sessionList = Array.isArray(sessionsData)
        ? sessionsData
        : [];

      const enrichedSessions = await Promise.all(
        sessionList.map(async (session) => {
          try {
            const review = await api(
              `/doctors/${doctorId}/sessions/${session.id}/review`,
              {
                auth: "doctor",
              }
            );

            return {
              ...session,
              ...review,
            };
          } catch (err) {
            console.error(
              `Unable to load review for session ${session.id}`,
              err
            );

            return {
              ...session,
              summary: null,
            };
          }
        })
      );

      setSessions(enrichedSessions);
    } catch (err) {
      console.error("Dashboard loading error:", err);

      setError(
        err?.message ||
          "Unable to load the doctor dashboard."
      );
    } finally {
      setLoading(false);
    }
  }

  /* ============================================================
     LOGOUT
     ============================================================ */

  function handleLogout() {
    clearDoctorAccessToken();
    sessionStorage.removeItem("doctorId");
    navigate("/doctor/login");
  }

  /* ============================================================
     HELPERS
     ============================================================ */

  function getStatus(session) {
    const summaryStatus = (
      session?.summary?.status ||
      session?.summary_status ||
      "draft"
    ).toLowerCase();

    if (summaryStatus === "accepted") {
      return "accepted";
    }

    if (summaryStatus === "rejected") {
      return "rejected";
    }

    return "draft";
  }

  function getStatusLabel(status) {
    switch (status) {
      case "accepted":
        return "Approved";

      case "rejected":
        return "Rejected";

      case "draft":
      default:
        return "Pending Review";
    }
  }

  function getMode(session) {
    const mode = (
      session?.mode ||
      session?.consultation_mode ||
      "allopathy"
    ).toLowerCase();

    if (
      mode === "ayush" ||
      mode === "ayurveda"
    ) {
      return "AYUSH";
    }

    return "Allopathy";
  }

  function formatDate(value) {
    if (!value) {
      return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return "—";
    }

    return date.toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  /* ============================================================
     FILTER
     ============================================================ */

  const filteredSessions = useMemo(() => {
    const query = search.trim().toLowerCase();

    return sessions.filter((session) => {
      const status = getStatus(session);

      const matchesSearch =
        !query ||
        String(session.id || "")
          .toLowerCase()
          .includes(query) ||
        String(session.patient_id || "")
          .toLowerCase()
          .includes(query);

      const matchesStatus =
        statusFilter === "all" ||
        status === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [
    sessions,
    search,
    statusFilter,
  ]);

  /* ============================================================
     STATS
     ============================================================ */

  const pendingCount = sessions.filter(
    (session) => {
      const status = getStatus(session);

      return (
        status === "draft" ||
        status === "pending"
      );
    }
  ).length;

  const acceptedCount = sessions.filter(
    (session) =>
      getStatus(session) === "accepted"
  ).length;

  const rejectedCount = sessions.filter(
    (session) =>
      getStatus(session) === "rejected"
  ).length;

  /* ============================================================
     RENDER
     ============================================================ */

  return (
    <main className="doctor-page">

      {/* ======================================================
          TOP BAR
          ====================================================== */}

      <header className="doctor-topbar">

        <div className="doctor-topbar__brand">

          <div className="doctor-brand-mini">
            <img
              src="/medikiosk-logo.png"
              alt="MediKiosk"
            />
          </div>

          <div>
            <div className="doctor-topbar__title">
              MediKiosk
            </div>

            <div className="doctor-topbar__subtitle">
              Doctor Portal
            </div>
          </div>

        </div>


        <div className="doctor-topbar__right">

          <div className="doctor-doctor-identity">

            <div className="doctor-small-avatar">
              {doctor?.name
                ? doctor.name
                    .charAt(0)
                    .toUpperCase()
                : "D"}
            </div>

            <div>

              <strong>
                {doctor?.name || "Doctor"}
              </strong>

              <span>
                {doctor?.specialization ||
                  doctor?.department ||
                  "Clinical Review"}
              </span>

            </div>

          </div>


          <button
            type="button"
            className="doctor-topbar__logout"
            onClick={handleLogout}
          >
            Logout
          </button>

        </div>

      </header>


      {/* ======================================================
          DASHBOARD
          ====================================================== */}

      <section className="doctor-dashboard">

        {/* HEADING */}

        <div className="doctor-dashboard-heading">

          <div>

            <h1>
              Patient Cases
            </h1>

            <p>
              Review AI-generated clinical histories
              before consultation.
            </p>

          </div>


          <button
            type="button"
            className="doctor-refresh-button"
            onClick={loadDashboard}
            disabled={loading}
          >
            {loading ? "Refreshing..." : "↻ Refresh"}
          </button>

        </div>


        {/* ERROR */}

        {error && (
          <div className="doctor-error-card">

            <div className="doctor-error-card__icon">
              !
            </div>

            <h1>
              Unable to load cases
            </h1>

            <p>
              {error}
            </p>

            <button
              type="button"
              className="doctor-button doctor-button--primary"
              onClick={loadDashboard}
            >
              Try Again
            </button>

          </div>
        )}


        {/* ==================================================
            STATS
            ================================================== */}

        {!error && (
          <div className="doctor-stat-grid">

            <div className="doctor-stat-card doctor-stat-card--pending">

              <span className="doctor-stat-card__label">
                Pending Review
              </span>

              <strong>
                {pendingCount}
              </strong>

              <span className="doctor-stat-card__hint">
                Awaiting physician review
              </span>

            </div>


            <div className="doctor-stat-card doctor-stat-card--accepted">

              <span className="doctor-stat-card__label">
                Approved
              </span>

              <strong>
                {acceptedCount}
              </strong>

              <span className="doctor-stat-card__hint">
                Doctor-confirmed summaries
              </span>

            </div>


            <div className="doctor-stat-card doctor-stat-card--rejected">

              <span className="doctor-stat-card__label">
                Rejected
              </span>

              <strong>
                {rejectedCount}
              </strong>

              <span className="doctor-stat-card__hint">
                Require further review
              </span>

            </div>


            <div className="doctor-stat-card">

              <span className="doctor-stat-card__label">
                Total Cases
              </span>

              <strong>
                {sessions.length}
              </strong>

              <span className="doctor-stat-card__hint">
                Assigned patient sessions
              </span>

            </div>

          </div>
        )}


        {/* ==================================================
            CASE PANEL
            ================================================== */}

        {!error && (
          <section className="doctor-cases-panel">

            {/* HEADER */}

            <div className="doctor-cases-header">

              <div>

                <h2>
                  Assigned Cases
                </h2>

                <p>
                  Patient sessions routed to you
                  for clinical review.
                </p>

              </div>


              <div className="doctor-case-tools">

                <div className="doctor-search">

                  <span>
                    ⌕
                  </span>

                  <input
                    type="text"
                    placeholder="Search patient or session..."
                    value={search}
                    onChange={(event) =>
                      setSearch(event.target.value)
                    }
                  />

                </div>


                <select
                  className="doctor-filter"
                  value={statusFilter}
                  onChange={(event) =>
                    setStatusFilter(
                      event.target.value
                    )
                  }
                >

                  <option value="all">
                    All Status
                  </option>

                  <option value="draft">
                    Pending Review
                  </option>

                  <option value="accepted">
                    Approved
                  </option>

                  <option value="rejected">
                    Rejected
                  </option>

                </select>

              </div>

            </div>


            {/* ==================================================
                LOADING
                ================================================== */}

            {loading ? (

              <div className="doctor-loading">

                <div className="doctor-loading__spinner" />

                <span>
                  Loading patient cases...
                </span>

              </div>

            ) : filteredSessions.length === 0 ? (

              /* ==================================================
                 EMPTY
                 ================================================== */

              <div className="doctor-no-cases">

                <div className="doctor-no-cases__icon">
                  ✓
                </div>

                <h3>
                  No patient cases found
                </h3>

                <p>
                  There are currently no sessions
                  matching your search or filter.
                </p>

              </div>

            ) : (

              /* ==================================================
                 TABLE
                 ================================================== */

              <div className="doctor-case-table-wrapper">

                <table className="doctor-case-table">

                  <thead>
                    <tr>

                      <th>
                        Patient
                      </th>

                      <th>
                        Session
                      </th>

                      <th>
                        Mode
                      </th>

                      <th>
                        Created
                      </th>

                      <th>
                        Status
                      </th>

                      <th>
                        Action
                      </th>

                    </tr>
                  </thead>


                  <tbody>

                    {filteredSessions.map(
                      (session) => {

                        const status =
                          getStatus(session);

                        return (
                          <tr key={session.id}>

                            {/* PATIENT */}

                            <td>

                              <div className="doctor-table-patient">

                                <div className="doctor-table-avatar">
                                  P
                                </div>

                                <div>

                                  <strong>
                                    Patient #
                                    {session.patient_id}
                                  </strong>

                                  <span>
                                    Patient ID:{" "}
                                    {session.patient_id}
                                  </span>

                                </div>

                              </div>

                            </td>


                            {/* SESSION */}

                            <td>

                              <span className="doctor-session-chip">
                                #{session.id}
                              </span>

                            </td>


                            {/* MODE */}

                            <td>

                              <span className="doctor-table-muted">
                                {getMode(session)}
                              </span>

                            </td>


                            {/* DATE */}

                            <td>

                              <span className="doctor-table-muted">
                                {formatDate(
                                  session.created_at
                                )}
                              </span>

                            </td>


                            {/* STATUS */}

                            <td>

                              <span
                                className={`doctor-case-status ${
                                  status === "accepted"
                                    ? "doctor-case-status--accepted"
                                    : status === "rejected"
                                    ? "doctor-case-status--rejected"
                                    : "doctor-case-status--pending"
                                }`}
                              >

                                <span className="doctor-case-status__dot" />

                                {getStatusLabel(
                                  status
                                )}

                              </span>

                            </td>


                            {/* ACTION */}

                            <td>

                              <button
                                type="button"
                                className="doctor-review-button"
                                onClick={() =>
                                  navigate(
                                    `/doctor/session/${session.id}`
                                  )
                                }
                              >
                                Review
                                <span>
                                  →
                                </span>
                              </button>

                            </td>

                          </tr>
                        );
                      }
                    )}

                  </tbody>

                </table>

              </div>

            )}

          </section>
        )}

      </section>

    </main>
  );
}