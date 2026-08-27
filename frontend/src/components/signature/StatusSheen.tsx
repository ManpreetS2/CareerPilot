import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "../../lib/cn";

export function StatusSheen({
  status,
  children,
  className,
}: {
  status: string;
  children: ReactNode;
  className?: string;
}) {
  const previous = useRef(status);
  const [sheen, setSheen] = useState(false);

  useEffect(() => {
    if (previous.current === status) return;
    previous.current = status;
    setSheen(true);
    const timer = window.setTimeout(() => setSheen(false), 420);
    return () => window.clearTimeout(timer);
  }, [status]);

  return <span className={cn(sheen && "status-sheen inline-flex", className)}>{children}</span>;
}
