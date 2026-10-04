export function Placeholder({ title }: { title: string }) {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-[26px] font-semibold tracking-tight">{title}</h1>
      <p className="text-text-muted">Not built yet.</p>
    </div>
  );
}
