import { api } from "./api";

export const summaryService = {
  generate: (sessionId) =>
    api(`/summaries/session/${sessionId}/generate`, {
      method: "POST",
    }),

  get: (summaryId) =>
    api(`/summaries/${summaryId}`),

  update: (summaryId, data) =>
    api(`/summaries/${summaryId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    }),
};