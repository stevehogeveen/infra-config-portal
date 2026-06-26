import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

import { cn } from "../../lib/utils";

type ActionLinkProps = {
  children: ReactNode;
  className?: string;
  href?: string;
  to?: string;
  onClick?: () => void;
};

export function ActionLink({ children, className, href, to, onClick }: ActionLinkProps) {
  const content = (
    <>
      <span>{children}</span>
      <ChevronRight aria-hidden="true" size={14} />
    </>
  );
  const classes = cn("ui-action-link", className);

  if (to) {
    return (
      <Link className={classes} to={to}>
        {content}
      </Link>
    );
  }

  if (href) {
    return (
      <a className={classes} href={href}>
        {content}
      </a>
    );
  }

  return (
    <button className={classes} onClick={onClick} type="button">
      {content}
    </button>
  );
}
