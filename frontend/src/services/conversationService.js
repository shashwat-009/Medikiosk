import { api } from "./api";

export async function startConversation({
  sessionId,
  complaint,
  language = "en",
  mode = "allopathy",
}) {
  return api("/conversation/start", {
    method: "POST",

    headers: {
      "Content-Type": "application/json",
    },

    body: JSON.stringify({
      session_id: sessionId,
      complaint,
      language,
      mode,
    }),

    auth: "patient",
  });
}

export async function submitConversationAnswer({
  sessionId,
  fieldId,
  answer,
  questionId,
  inputType = "touch",
}) {
  return api("/conversation/answer", {
    method: "POST",

    headers: {
      "Content-Type": "application/json",
    },

    body: JSON.stringify({
      session_id: sessionId,
      field_id: fieldId,
      answer,
      question_id: questionId,
      input_type: inputType,
    }),

    auth: "patient",
  });
}

export async function getNextConversationQuestion(sessionId) {
  return api(
    `/conversation/${encodeURIComponent(sessionId)}/next`,
    {
      method: "GET",
      auth: "patient",
    }
  );
}