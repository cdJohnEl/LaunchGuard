type GroupLineProps = {
  name: string | null;
  active: boolean;
  subscription: string | null;
};

export function GroupLine({ name, active, subscription }: GroupLineProps) {
  const unregistered = name === null && !active;

  if (unregistered) {
    return (
      <p className="mt-4 flex items-center gap-2 text-sm text-ink-soft">
        <span
          className="inline-block h-1.5 w-1.5 rounded-full bg-signal"
          aria-hidden="true"
        />
        Bot has not registered this group yet
      </p>
    );
  }

  return (
    <p className="mt-4 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm text-ink-soft">
      <span>
        Protecting{" "}
        <strong className="font-semibold text-ink">{name ?? "this group"}</strong>
      </span>
      <span
        className={`inline-block h-1.5 w-1.5 self-center rounded-full ${
          active ? "bg-ink" : "bg-signal"
        }`}
        aria-hidden="true"
      />
      <span>
        {active
          ? "Bot active in the group"
          : "Bot not active — it left the group or was removed"}
      </span>
      {subscription !== null && (
        <>
          <span aria-hidden="true">·</span>
          <span className="font-mono text-[11px] uppercase tracking-[0.14em]">
            {subscription}
          </span>
        </>
      )}
    </p>
  );
}
