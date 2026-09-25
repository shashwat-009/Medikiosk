import { apiJson } from "./api";

export async function createPatient(patientData) {
  return apiJson("/patients/", "POST", {
    name: patientData.name,
    age: patientData.age,
    gender: patientData.gender,
    aadhaar: patientData.aadhaar,
  });
}