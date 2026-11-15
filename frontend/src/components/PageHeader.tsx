type Props = { title: string; description?: string };

export default function PageHeader({ title, description }: Props) {
  return (
    <div className="mb-6">
      <h1 className="text-23 font-semibold tracking-heading">{title}</h1>
      {description ? (
        <p className="mt-1 max-w-[65ch] text-14 text-text-secondary">{description}</p>
      ) : null}
    </div>
  );
}