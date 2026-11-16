import type { ReactNode } from 'react';

type Props = { title: string; body: string; children?: ReactNode };

export default function EmptyState({ title, body, children }: Props) {
  return (
    <section className="w-full max-w-3xl rounded-3xl border border-white bg-surface px-5 py-7 shadow-sm sm:px-7">
      <h2 className="text-19 font-semibold tracking-heading">{title}</h2>
      <p className="mt-2 max-w-[65ch] text-14 text-text-secondary">{body}</p>
      {children ? <div className="mt-5">{children}</div> : null}
    </section>
  );
}