import { api } from "./api";

export const documentService = {
  upload: (data) =>
    api("/documents/", {
      method: "POST",
      body: data,
      auth: "patient",
    }),

  process: (documentId) =>
    api(`/documents/${documentId}/process`, {
      method: "POST",
      auth: "patient",
    }),
};