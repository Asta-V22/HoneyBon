export function Placeholder({ title, note }: { title: string; note: string }) {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-[26px] font-semibold tracking-tight">{title}</h1>
      <p className="text-text-muted">{note}</p>
    </div>
  );
}
