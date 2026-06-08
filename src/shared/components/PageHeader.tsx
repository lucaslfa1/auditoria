import type { ElementType, ReactNode } from 'react';

interface PageHeaderProps {
  eyebrow: string;
  titleFirstWord: string;
  titleRest?: string;
  subtitle: string;
  headingTag?: 'h1' | 'h2';
  className?: string;
  aside?: ReactNode;
}

export function PageHeader({
  eyebrow,
  titleFirstWord,
  titleRest,
  subtitle,
  headingTag = 'h1',
  className = '',
  aside,
}: PageHeaderProps) {
  const HeadingTag = headingTag as ElementType;
  const classes = ['page-hero', className].filter(Boolean).join(' ');

  return (
    <section className={classes}>
      <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="page-eyebrow">{eyebrow}</p>
          <HeadingTag className="page-title">
            <span className="page-title-accent">{titleFirstWord}</span>
            {titleRest && <> {titleRest}</>}
          </HeadingTag>
          <p className="page-subtitle">{subtitle}</p>
        </div>
        {aside ? <div className="flex flex-wrap gap-2.5 lg:justify-end">{aside}</div> : null}
      </div>
    </section>
  );
}
