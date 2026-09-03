const ENV_KEYS = [
  "NEXT_PUBLIC_FIREBASE_API_KEY",
  "NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN",
  "NEXT_PUBLIC_FIREBASE_PROJECT_ID",
  "NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET",
  "NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID",
  "NEXT_PUBLIC_FIREBASE_APP_ID",
];

export function SetupNotice() {
  return (
    <section className="mt-12 border border-rule-strong">
      <div className="border-b border-rule px-8 py-8 md:px-10">
        <p className="kicker">Setup</p>
        <h2 className="mt-2 font-display text-2xl tracking-tight md:text-3xl">
          Set up Firebase first
        </h2>
        <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-ink-soft">
          The dashboard reads its live counter from Firestore. Copy your
          Firebase web config into{" "}
          <span className="font-mono text-[13px] text-ink">.env.local</span>,
          then restart the dev server. Values come from the Firebase console,
          under Project settings, Your apps.
        </p>
      </div>
      <ul className="grid gap-x-8 gap-y-2 px-8 py-6 font-mono text-[13px] md:grid-cols-2 md:px-10">
        {ENV_KEYS.map((key) => (
          <li key={key} className="flex gap-2">
            <span className="text-signal" aria-hidden="true">
              →
            </span>
            {key}
          </li>
        ))}
      </ul>
    </section>
  );
}
