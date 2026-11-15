type Props = { title: string; body: string };

export default function EmptyState({ title, body }: Props) {
  return (
    <div className="rounded-md border border-border bg-surface p-6">
      <p className="text-16 font-medium">{title}</p>
      <p className="mt-1 max-w-[65ch] text-14 text-text-secondary">{body}</p>
    </div>
  );
}