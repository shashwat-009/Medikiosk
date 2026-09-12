import { api } from "./api";

export async function createResponse(responseData) {
  return api("/responses/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(responseData),
    auth: "patient",
  });
}