import React from "react";

interface TableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  children: React.ReactNode;
  className?: string;
  striped?: boolean;
}

export function Table({ children, className = "", striped = false, ...props }: TableProps) {
  return (
    <div className="w-full overflow-x-auto border border-[#E2E8F0] rounded-card bg-white">
      <table
        className={`w-full text-left text-xs border-collapse ${striped ? "[&_tbody_tr:nth-child(even)]:bg-[#F8FAFC]" : ""} ${className}`}
        {...props}
      >
        {children}
      </table>
    </div>
  );
}

export function TableHead({ children, className = "", ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead className={`bg-[#F8FAFC] text-[#64748B] border-b border-[#E2E8F0] ${className}`} {...props}>
      {children}
    </thead>
  );
}

export function TableBody({ children, className = "", ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tbody className={`divide-y divide-[#E2E8F0] ${className}`} {...props}>
      {children}
    </tbody>
  );
}

export function TableRow({ children, className = "", ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr className={`hover:bg-[#F8FAFC] transition-colors ${className}`} {...props}>
      {children}
    </tr>
  );
}

export function TableHeader({ children, className = "", ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th className={`py-3 px-4 font-semibold text-[#64748B] text-start ${className}`} {...props}>
      {children}
    </th>
  );
}

export function TableCell({ children, className = "", ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={`py-3 px-4 text-[#0F172A] ${className}`} {...props}>
      {children}
    </td>
  );
}
