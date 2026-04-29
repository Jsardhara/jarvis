import {
  InputHTMLAttributes,
  ReactNode,
  TextareaHTMLAttributes,
  forwardRef,
} from "react";
import { cn } from "@/lib/utils";

interface FieldProps {
  label?: string;
  hint?: ReactNode;
  className?: string;
  children: ReactNode;
}

/** Field wrapper — uppercase label + monospace input slot. */
export function OpsField({ label, hint, className, children }: FieldProps) {
  return (
    <label className={cn("ops-field", className)}>
      {label && <span>{label}</span>}
      {children}
      {hint && (
        <span className="text-[10px] text-ops-fg-dim font-mono mt-1">{hint}</span>
      )}
    </label>
  );
}

type OpsInputProps = InputHTMLAttributes<HTMLInputElement>;
export const OpsInput = forwardRef<HTMLInputElement, OpsInputProps>(
  function OpsInput({ className, ...rest }, ref) {
    return (
      <input
        ref={ref}
        className={cn(
          "bg-ops-input-bg border border-ops-line text-ops-fg font-mono text-[12px] px-2 py-1.5 rounded-[2px] outline-none focus:border-ops-amber focus:bg-ops-deep w-full",
          className
        )}
        {...rest}
      />
    );
  }
);

type OpsTextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;
export const OpsTextarea = forwardRef<HTMLTextAreaElement, OpsTextareaProps>(
  function OpsTextarea({ className, ...rest }, ref) {
    return (
      <textarea
        ref={ref}
        className={cn(
          "bg-ops-input-bg border border-ops-line text-ops-fg font-mono text-[12px] px-3 py-2 rounded-[2px] outline-none focus:border-ops-amber focus:bg-ops-deep w-full resize-y min-h-[80px] leading-[1.55]",
          className
        )}
        {...rest}
      />
    );
  }
);
