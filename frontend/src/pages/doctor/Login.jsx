import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, setDoctorAccessToken } from "../../services/api";

import "./doctor.css";

export default function Login() {
  const navigate = useNavigate();

  const [doctorId, setDoctorId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();

    const id = doctorId.trim();

    if (!id) {
      setError("Please enter your doctor ID.");
      return;
    }

    if (!password) {
      setError("Please enter your password.");
      return;
    }

    setError("");
    setIsLoading(true);

    try {
      const response = await api("/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({
          username: id,
          password,
        }),
      });

      if (!response?.access_token) {
        throw new Error("Login failed. No access token was returned.");
      }

      setDoctorAccessToken(response.access_token);

      sessionStorage.setItem(
        "doctorId",
        id
      );

      navigate("/doctor");
    } catch (err) {
      console.error("Doctor login failed:", err);

      setError(
        err?.message ||
          "Unable to sign in. Please check your doctor ID and password."
      );
    } finally {
      setIsLoading(false);
    }
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
                autoComplete="username"
                disabled={isLoading}
              />

            </div>


            <div className="doctor-field">

              <label htmlFor="doctor-password">
                Password
              </label>

              <input
                id="doctor-password"
                type="password"
                value={password}
                onChange={(event) =>
                  setPassword(event.target.value)
                }
                placeholder="Enter password"
                autoComplete="current-password"
                disabled={isLoading}
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
              disabled={isLoading}
            >
              {isLoading ? "Signing in..." : "Continue"}

              {!isLoading && (
                <span>→</span>
              )}
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