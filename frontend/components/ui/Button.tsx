import React from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  icon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      children,
      variant = "primary",
      size = "md",
      isLoading = false,
      leftIcon,
      rightIcon,
      icon,
      className = "",
      disabled,
      ...props
    },
    ref
  ) => {
    // Base styles: 8px radius, min 44px touch target on md/lg, visible focus ring
    const base =
      "inline-flex items-center justify-center font-medium transition-colors duration-150 rounded-btn cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed select-none focus:outline-none focus:ring-2 focus:ring-[#0F766E] focus:ring-offset-2";

    const sizes = {
      sm: "h-9 px-3 text-xs gap-1.5",
      md: "h-11 px-4 text-sm gap-2", // 44px min height
      lg: "h-12 px-6 text-base gap-2.5",
    };

    const variants = {
      primary:
        "bg-[#0F766E] hover:bg-[#115E59] active:bg-[#0D4E49] text-white shadow-soft",
      secondary:
        "bg-white hover:bg-slate-50 text-[#0F172A] border border-[#E2E8F0] shadow-soft",
      ghost:
        "bg-transparent hover:bg-slate-100 text-[#475569] hover:text-[#0F172A]",
      danger:
        "bg-[#B91C1C] hover:bg-[#991B1B] text-white shadow-soft",
    };

    const leadingIcon = leftIcon || icon;

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}
        {...props}
      >
        {isLoading ? (
          <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
        ) : (
          leadingIcon
        )}
        {children && <span>{children}</span>}
        {!isLoading && rightIcon}
      </button>
    );
  }
);

Button.displayName = "Button";
