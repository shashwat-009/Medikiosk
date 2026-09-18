import { useNavigate } from "react-router-dom";
import { useKiosk } from "../../context/KioskContext";
import { LANGUAGES } from "../../i18n/languages";
import { translate } from "../../i18n";
import "./Welcome.css";

export default function Welcome() {
  const navigate = useNavigate();
  const { reset, setLanguage } = useKiosk();

  function handleLanguageSelect(languageCode) {
    reset();
    setLanguage(languageCode);
    navigate("/identify");
  }

  // Welcome page itself is shown before a language
  // has been selected, so English is the fallback.
  const language = "en";

  return (
    <main className="welcome">
      <section className="welcome__hero">
        <div
          className="welcome__pulse"
          aria-hidden="true"
        >
          <svg
            viewBox="0 0 600 90"
            preserveAspectRatio="none"
          >
            <polyline
              points="
                0,45
                120,45
                145,45
                160,20
                175,70
                190,45
                280,45
                300,45
                315,10
                330,80
                345,45
                430,45
                455,45
                470,28
                485,62
                500,45
                600,45
              "
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>

        <p className="welcome__eyebrow">
          {translate(
            language,
            "welcome.eyebrow"
          )}
        </p>

        <h1>
          {translate(
            language,
            "welcome.title"
          )}
        </h1>

        <p className="welcome__description">
          {translate(
            language,
            "welcome.description"
          )}
        </p>
      </section>

      <section className="welcome__panel">
        <div className="welcome__panel-header">
          <h2>
            {translate(
              language,
              "welcome.chooseLanguage"
            )}
          </h2>

          <p className="welcome__hint">
            अपनी भाषा चुनें · আপনার ভাষা নির্বাচন করুন · तुमची भाषा निवडा
          </p>
        </div>

        <div className="welcome__grid">
          {LANGUAGES.map((item) => (
            <button
              key={item.code}
              type="button"
              className="welcome__lang"
              onClick={() => handleLanguageSelect(item.code)}
              data-tts={item.nativeName}
              data-tts-language={item.code}
              aria-label={`Continue in ${item.name}`}
            >
              <span className="welcome__lang-native">
                {item.nativeName}
              </span>
            </button>
          ))}
        </div>

        <button
          type="button"
          className="welcome__assist"
        >
          {translate(
            language,
            "welcome.needHelp"
          )}
        </button>
      </section>
    </main>
  );
}