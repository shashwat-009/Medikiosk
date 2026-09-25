import "./KioskShell.css";

export default function KioskShell({ children }) {
  return (
    <main className="kiosk-shell">
      <header className="kiosk-header">
        <div className="kiosk-header__brand">
          <img
            src="/medisetu-logo.png"
            alt="MediSetu"
            className="kiosk-header__logo"
          />

          <div className="kiosk-header__text">
            <span className="kiosk-header__name">
              MediSetu
            </span>

            <span className="kiosk-header__subtitle">
              Smart Patient Care
            </span>
          </div>
        </div>
      </header>

      <div className="kiosk-shell__content">
        {children}
      </div>
    </main>
  );
}