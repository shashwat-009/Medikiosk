import { useState } from "react";
import { useNavigate } from "react-router-dom";

import "./doctor.css";


export default function Login() {
  const navigate = useNavigate();

  const [doctorId, setDoctorId] = useState("");
  const [error, setError] = useState("");


  function handleSubmit(event) {
    event.preventDefault();

    const id = doctorId.trim();

    if (!id) {
      setError("Please enter your doctor ID.");
      return;
    }

    setError("");

    sessionStorage.setItem(
      "doctorId",
      id
    );

    navigate("/doctor");
  }


  return (
    <main className="doctor-login-page">

      <div className="doctor-login-shell">

        {/* ==================================================
            BRAND PANEL
            ================================================== */}

        <section className="doctor-login-brand">

          <div className="doctor-login-logo">
            <img
              src="/medikiosk-logo.png"
              alt="MediKiosk logo"
            />
          </div>

          <div className="doctor-brand-name">
            MediKiosk
          </div>

          <div className="doctor-brand-line" />

          <h1>
            Clinical Review
            <br />
            Portal
          </h1>

          <p>
            Review AI-generated patient histories
            before consultation.
          </p>

          <div className="doctor-brand-note">
            Physician workspace
          </div>

        </section>


        {/* ==================================================
            LOGIN PANEL
            ================================================== */}

        <section className="doctor-login-card">

          <div className="doctor-login-heading">

            <span className="doctor-login-eyebrow">
              PHYSICIAN ACCESS
            </span>

            <h2>
              Welcome back
            </h2>

            <p>
              Sign in to access your assigned
              patient cases.
            </p>

          </div>


          <form
            className="doctor-login-form"
            onSubmit={handleSubmit}
          >

            <div className="doctor-field">

              <label htmlFor="doctor-id">
                Doctor ID
              </label>

              <input
                id="doctor-id"
                type="text"
                value={doctorId}
                onChange={(event) =>
                  setDoctorId(event.target.value)
                }
                placeholder="Enter doctor ID"
                autoComplete="off"
              />

            </div>


            {error && (
              <div className="doctor-form-error">
                {error}
              </div>
            )}


            <button
              type="submit"
              className="doctor-login-button"
            >
              Continue
              <span>→</span>
            </button>

          </form>


          <div className="doctor-login-footer">
            MediKiosk • Physician Portal
          </div>

        </section>

      </div>

    </main>
  );
}