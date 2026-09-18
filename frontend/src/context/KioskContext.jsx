import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

const KioskContext = createContext(null);

const STORAGE_KEY = "medikiosk_kiosk_state_v1";

const initialState = {
  language: null,
  mode: "allopathy",

  patient: null,
  session: null,
  consent: null,

  transcript: [],
  documents: [],
  summary: null,
  redFlag: null,
};

function loadPersistedState() {
  if (typeof window === "undefined") {
    return initialState;
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);

    if (!stored) {
      return initialState;
    }

    const parsed = JSON.parse(stored);

    if (!parsed || typeof parsed !== "object") {
      return initialState;
    }

    return {
      ...initialState,

      language:
        typeof parsed.language === "string"
          ? parsed.language
          : null,

      mode:
        parsed.mode === "allopathy" || parsed.mode === "ayush"
          ? parsed.mode
          : "allopathy",

      patient:
        parsed.patient &&
        typeof parsed.patient === "object"
          ? parsed.patient
          : null,

      session:
        parsed.session &&
        typeof parsed.session === "object"
          ? parsed.session
          : null,

      consent:
        parsed.consent &&
        typeof parsed.consent === "object"
          ? parsed.consent
          : null,
    };
  } catch (error) {
    console.error("Failed to restore kiosk state:", error);

    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore storage errors.
    }

    return initialState;
  }
}

function sanitizePatient(patient) {
  if (!patient || typeof patient !== "object") {
    return null;
  }

  if (!patient.id) {
    return null;
  }

  return {
    id: patient.id,
    name: patient.name ?? null,
    age: patient.age ?? null,
    gender: patient.gender ?? null,
  };
}

function sanitizeSession(session) {
  if (!session || typeof session !== "object") {
    return null;
  }

  if (!session.id) {
    return null;
  }

  return {
    id: session.id,
    patient_id: session.patient_id ?? null,
    doctor_id: session.doctor_id ?? null,
    status: session.status ?? null,
    language: session.language ?? null,
    mode: session.mode ?? null,
    complaint: session.complaint ?? null,
    created_at: session.created_at ?? null,
    last_activity_at: session.last_activity_at ?? null,
    expires_at: session.expires_at ?? null,
    completed_at: session.completed_at ?? null,
  };
}

function persistState(state) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    const data = {
      language: state.language,
      mode: state.mode,
      patient: sanitizePatient(state.patient),
      session: sanitizeSession(state.session),
      consent:
        state.consent &&
        typeof state.consent === "object"
          ? state.consent
          : null,
    };

    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(data)
    );
  } catch (error) {
    console.error("Failed to persist kiosk state:", error);
  }
}

function clearPersistedState() {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore storage errors.
  }
}

export function KioskProvider({ children }) {
  const [state, setState] = useState(() => {
    return loadPersistedState();
  });

  useEffect(() => {
    persistState(state);
  }, [
    state.language,
    state.mode,
    state.patient,
    state.session,
    state.consent,
  ]);

  const actions = useMemo(
    () => ({
      state,

      setLanguage: (language) => {
        setState((current) => ({
          ...current,
          language,
        }));
      },

      setMode: (mode) => {
        setState((current) => ({
          ...current,
          mode,
        }));
      },

      setPatient: (patient) => {
        setState((current) => ({
          ...current,
          patient,
        }));
      },

      setSession: (session) => {
        setState((current) => ({
          ...current,
          session,
        }));
      },

      setConsent: (consent) => {
        setState((current) => ({
          ...current,
          consent,
        }));
      },

      pushTranscript: (entry) => {
        setState((current) => ({
          ...current,
          transcript: [
            ...current.transcript,
            entry,
          ],
        }));
      },

      clearTranscript: () => {
        setState((current) => ({
          ...current,
          transcript: [],
        }));
      },

      addDocument: (document) => {
        setState((current) => ({
          ...current,
          documents: [
            ...current.documents,
            document,
          ],
        }));
      },

      updateDocument: (id, updates) => {
        setState((current) => ({
          ...current,
          documents: current.documents.map(
            (document) =>
              document.id === id
                ? {
                    ...document,
                    ...updates,
                  }
                : document
          ),
        }));
      },

      removeDocument: (id) => {
        setState((current) => ({
          ...current,
          documents: current.documents.filter(
            (document) => document.id !== id
          ),
        }));
      },

      setSummary: (summary) => {
        setState((current) => ({
          ...current,
          summary,
        }));
      },

      triggerRedFlag: (symptom) => {
        setState((current) => ({
          ...current,
          redFlag: {
            symptom,
            time: new Date().toISOString(),
          },
        }));
      },

      clearRedFlag: () => {
        setState((current) => ({
          ...current,
          redFlag: null,
        }));
      },

      reset: () => {
        clearPersistedState();
        setState({
          ...initialState,
        });
      },
    }),
    [state]
  );

  return (
    <KioskContext.Provider value={actions}>
      {children}
    </KioskContext.Provider>
  );
}

export function useKiosk() {
  const context = useContext(KioskContext);

  if (!context) {
    throw new Error(
      "useKiosk must be used within KioskProvider"
    );
  }

  return context;
}