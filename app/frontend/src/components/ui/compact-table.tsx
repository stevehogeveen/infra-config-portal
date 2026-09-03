import {
  Children,
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode
} from "react";

import { cn } from "../../lib/utils";

type CompactTableProps = {
  children: ReactNode;
  className?: string;
};

type CompactTableRowProps = {
  children: ReactNode;
  className?: string;
  hover?: boolean;
};

type CompactTableCellProps = {
  children: ReactNode;
  align?: "left" | "center" | "right";
  className?: string;
  header?: boolean;
};

export function CompactTable({ children, className }: CompactTableProps) {
  return (
    <div className="ui-compact-table-wrap">
      <table className={cn("ui-compact-table", className)}>{children}</table>
    </div>
  );
}

export function CompactTableHeader({ children, className }: CompactTableProps) {
  return (
    <thead className={cn("ui-compact-table-head", className)}>
      <tr>{markCellsAsHeader(children)}</tr>
    </thead>
  );
}

export function CompactTableRow({ children, className, hover = true }: CompactTableRowProps) {
  return <tr className={cn("ui-compact-table-row", hover && "ui-compact-table-row-hover", className)}>{children}</tr>;
}

export function CompactTableCell({ children, align = "left", className, header = false }: CompactTableCellProps) {
  const Tag = header ? "th" : "td";
  return <Tag className={cn("ui-compact-table-cell", `ui-compact-table-cell-${align}`, className)}>{children}</Tag>;
}

function markCellsAsHeader(children: ReactNode): ReactNode {
  return Children.map(children, (child) => {
    if (!isValidElement(child)) {
      return child;
    }
    return cloneElement(child as ReactElement<CompactTableCellProps>, { header: true });
  });
}
