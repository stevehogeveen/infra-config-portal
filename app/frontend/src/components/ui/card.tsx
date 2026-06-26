import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "../../lib/utils";

type CardProps = HTMLAttributes<HTMLElement> & {
  children: ReactNode;
  hover?: boolean;
};

type CardSectionProps = {
  children: ReactNode;
  className?: string;
};

export function Card({ children, className, hover = true, ...props }: CardProps) {
  return (
    <section className={cn("ui-card", hover && "ui-card-hover", className)} {...props}>
      {children}
    </section>
  );
}

export function CardHeader({ children, className }: CardSectionProps) {
  return <div className={cn("ui-card-header", className)}>{children}</div>;
}

export function CardContent({ children, className }: CardSectionProps) {
  return <div className={cn("ui-card-content", className)}>{children}</div>;
}

export function CardFooter({ children, className }: CardSectionProps) {
  return <div className={cn("ui-card-footer", className)}>{children}</div>;
}
