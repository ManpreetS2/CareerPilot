import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { X } from "lucide-react";
import { cn } from "../lib/cn";
import type { TaxonomyOption } from "../lib/profile-taxonomy";

type GuidedComboboxProps = {
  id?: string;
  label: string;
  values: string[];
  onChange: (next: string[]) => void;
  options: TaxonomyOption[];
  multiple?: boolean;
  allowCustom?: boolean;
  placeholder?: string;
  description?: string;
};

function normalize(value: string) {
  return value.trim().toLowerCase();
}

export function GuidedCombobox({
  id,
  label,
  values,
  onChange,
  options,
  multiple = true,
  allowCustom = true,
  placeholder = "Search or add your own",
  description,
}: GuidedComboboxProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const listboxId = `${inputId}-listbox`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  const selected = values.map((item) => item.trim()).filter(Boolean);
  const selectedKeys = new Set(selected.map(normalize));

  const filtered = useMemo(() => {
    const needle = normalize(query);
    return options.filter((option) => {
      if (selectedKeys.has(normalize(option.value))) return false;
      if (!needle) return true;
      return (
        normalize(option.label).includes(needle) || normalize(option.value).includes(needle)
      );
    });
  }, [options, query, selectedKeys]);

  const customValue = query.trim();
  const customAlreadySelected = customValue ? selectedKeys.has(normalize(customValue)) : false;
  const matchesOption = options.some(
    (option) => normalize(option.value) === normalize(customValue) || normalize(option.label) === normalize(customValue),
  );
  const canAddCustom =
    allowCustom && Boolean(customValue) && !customAlreadySelected && !matchesOption;

  const items: Array<{ value: string; label: string; custom?: boolean }> = [
    ...filtered.map((option) => ({ value: option.value, label: option.label })),
    ...(canAddCustom ? [{ value: customValue, label: `Add custom “${customValue}”`, custom: true }] : []),
    ...(allowCustom && !customValue
      ? [{ value: "__other__", label: "Other / add custom", custom: true }]
      : []),
  ];

  useEffect(() => {
    setActiveIndex(0);
  }, [query, open]);

  function commit(value: string) {
    if (value === "__other__") {
      setQuery("");
      setOpen(true);
      inputRef.current?.focus();
      return;
    }
    const nextValue = value.trim();
    if (!nextValue) return;
    if (multiple) {
      if (selectedKeys.has(normalize(nextValue))) return;
      onChange([...selected, nextValue]);
    } else {
      onChange([nextValue]);
    }
    setQuery("");
    setOpen(false);
  }

  function remove(value: string) {
    onChange(selected.filter((item) => normalize(item) !== normalize(value)));
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((index) => (items.length ? (index + 1) % items.length : 0));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((index) => (items.length ? (index - 1 + items.length) % items.length : 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const active = items[activeIndex];
      if (open && active) {
        commit(active.value);
        return;
      }
      if (customValue) commit(customValue);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === "Backspace" && !query && selected.length) {
      remove(selected[selected.length - 1]!);
    }
  }

  return (
    <div className="space-y-2">
      <label className="block" htmlFor={inputId}>
        <span className="label">{label}</span>
        {description ? <span className="mt-1 block text-xs text-muted-foreground">{description}</span> : null}
      </label>
      <div
        className={cn(
          "flex min-h-11 flex-wrap items-center gap-2 rounded-[var(--radius-md)] border border-border bg-background px-2 py-1.5",
          "focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/30",
        )}
      >
        {selected.map((value) => (
          <span
            key={value}
            className="inline-flex max-w-full items-center gap-1 rounded-full border border-border bg-muted px-2.5 py-1 text-xs"
          >
            <span className="truncate">{value}</span>
            <button
              type="button"
              className="rounded-full p-0.5 hover:bg-foreground/10"
              aria-label={`Remove ${value}`}
              onClick={() => remove(value)}
            >
              <X className="h-3 w-3" aria-hidden />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          id={inputId}
          className="min-h-8 min-w-[8rem] flex-1 bg-transparent text-sm outline-none"
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={open && items[activeIndex] ? `${inputId}-option-${activeIndex}` : undefined}
          placeholder={selected.length ? "" : placeholder}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            window.setTimeout(() => setOpen(false), 120);
          }}
          onKeyDown={onKeyDown}
          autoComplete="off"
        />
      </div>
      {open && items.length > 0 ? (
        <ul
          id={listboxId}
          role="listbox"
          className="max-h-56 overflow-auto rounded-[var(--radius-md)] border border-border bg-surface-elevated p-1 shadow-lg"
        >
          {items.map((item, index) => (
            <li key={`${item.value}-${item.label}`} role="presentation">
              <button
                type="button"
                id={`${inputId}-option-${index}`}
                role="option"
                aria-selected={index === activeIndex}
                className={cn(
                  "flex min-h-11 w-full items-center rounded-lg px-3 text-left text-sm",
                  index === activeIndex ? "bg-primary/15 text-foreground" : "text-foreground hover:bg-muted",
                )}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => commit(item.value)}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
