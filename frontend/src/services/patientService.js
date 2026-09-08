const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  "http://localhost:8000";


export async function createPatient(patientData) {
  const response = await fetch(
    `${API_BASE_URL}/patients/`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: patientData.name,
        age: patientData.age,
        gender: patientData.gender,
        aadhaar: patientData.aadhaar,
      }),
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);

    console.error("Patient API validation error:", errorData);

    let message = "Failed to create patient.";

    if (Array.isArray(errorData?.detail)) {
      message = errorData.detail
        .map((error) => {
          const field = Array.isArray(error.loc)
            ? error.loc.join(".")
            : "field";

          return `${field}: ${error.msg}`;
        })
        .join("\n");
    } else if (typeof errorData?.detail === "string") {
      message = errorData.detail;
    }

    throw new Error(message);
  }

  return response.json();
}