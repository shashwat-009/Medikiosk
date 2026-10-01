import { api } from "./api";

/**
 * Create or retrieve a patient using Aadhaar identity.
 *
 * This is the bootstrap endpoint, so it intentionally does
 * not require a patient session token.
 */
export async function createPatient(patientData) {
  if (!patientData) {
    throw new Error("Patient information is required.");
  }

  const name = String(patientData.name ?? "").trim();
  const age = Number(patientData.age);
  const gender = String(patientData.gender ?? "").trim();
  const aadhaar = String(patientData.aadhaar ?? "")
    .replace(/\D/g, "")
    .slice(0, 12);

  if (!name) {
    throw new Error("Patient name is required.");
  }

  if (!Number.isInteger(age) || age < 1 || age > 120) {
    throw new Error("Patient age must be between 1 and 120.");
  }

  if (!gender) {
    throw new Error("Patient gender is required.");
  }

  if (aadhaar.length !== 12) {
    throw new Error("Aadhaar must contain exactly 12 digits.");
  }

  const patient = await api("/patients/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name,
      age,
      gender,
      aadhaar,
    }),
  });

  if (!patient?.id) {
    throw new Error(
      "Patient was created or found, but no patient ID was returned."
    );
  }

  return patient;
}
