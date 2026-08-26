import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export const Sheet = DialogPrimitive.Root;
export const SheetTrigger = DialogPrimitive.Trigger;
export const SheetClose = DialogPrimitive.Close;

export function SheetContent({
  children,
  side = "left",
  title,
  className,
}: {
  children: ReactNode;
  side?: "left" | "right";
  title: string;
  className?: string;
  open?: boolean;
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="command-tunnel fixed inset-0 z-[70]" />
      <DialogPrimitive.Content
        className={cn(
          "glass-floating glass-refract fixed inset-y-0 z-[80] flex max-h-[100dvh] w-[min(20rem,100%)] flex-col overflow-y-auto border-border p-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-[max(1rem,env(safe-area-inset-top))] shadow-floating",
          side === "left" ? "left-0 border-r" : "right-0 border-l",
          className,
        )}
      >
        <div className="mb-4 flex items-center justify-between gap-2">
          <DialogPrimitive.Title className="font-display text-base font-semibold">
            {title}
          </DialogPrimitive.Title>
          <DialogPrimitive.Close className="btn-ghost h-11 w-11 min-h-11 px-0" aria-label="Close menu">
            <X className="h-4 w-4" />
          </DialogPrimitive.Close>
        </div>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
