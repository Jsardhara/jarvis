import { ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

type Variant = "default" | "primary" | "danger" | "icon";

interface OpsButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const variantClass: Record<Variant, string> = {
  default: "",
  primary: "ops-btn-primary",
  danger: "ops-btn-danger",
  icon: "ops-btn-icon",
};

export const OpsButton = forwardRef<HTMLButtonElement, OpsButtonProps>(
  function OpsButton({ variant = "default", className, children, ...rest }, ref) {
    return (
      <button
        ref={ref}
        className={cn("ops-btn", variantClass[variant], className)}
        {...rest}
      >
        {children}
      </button>
    );
  }
);
