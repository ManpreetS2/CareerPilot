import * as TabsPrimitive from "@radix-ui/react-tabs";
import type { ComponentPropsWithoutRef } from "react";
import { cn } from "../../lib/cn";

export const Tabs = TabsPrimitive.Root;
export const TabsList = ({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof TabsPrimitive.List>) => (
  <TabsPrimitive.List
    className={cn("flex flex-wrap gap-1 rounded-[var(--radius-md)] bg-surface-secondary p-1", className)}
    {...props}
  />
);
export const TabsTrigger = ({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>) => (
  <TabsPrimitive.Trigger
    className={cn(
      "min-h-11 rounded-[var(--radius-sm)] px-3 text-sm font-medium text-muted-foreground data-[state=active]:bg-surface data-[state=active]:text-foreground data-[state=active]:shadow-sm",
      className,
    )}
    {...props}
  />
);
export const TabsContent = TabsPrimitive.Content;
