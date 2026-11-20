import React from "react";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  leftIcon?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, leftIcon, className = "", id, required, ...props }, ref) => {
    const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);

    return (
      <div className="w-full space-y-1.5 text-left">
        {label && (
          <label htmlFor={inputId} className="block text-sm font-medium text-[#0F172A]">
            {label}
            {required && <span className="text-[#B91C1C] ml-1">*</span>}
          </label>
        )}

        <div className="relative">
          {leftIcon && (
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-[#64748B]">
              {leftIcon}
            </div>
          )}

          <input
            ref={ref}
            id={inputId}
            required={required}
            className={`w-full min-h-[44px] h-11 px-3.5 ${
              leftIcon ? "pl-10" : ""
            } bg-white border rounded-btn text-sm text-[#0F172A] placeholder-[#94A3B8] transition-colors focus:outline-none focus:ring-2 focus:ring-[#0F766E] focus:ring-offset-2 ${
              error
                ? "border-[#B91C1C] focus:ring-[#B91C1C]"
                : "border-[#E2E8F0] hover:border-[#CBD5E1]"
            } ${className}`}
            {...props}
          />
        </div>

        {error ? (
          <p className="text-xs text-[#B91C1C] font-medium">{error}</p>
        ) : helperText ? (
          <p className="text-xs text-[#64748B]">{helperText}</p>
        ) : null}
      </div>
    );
  }
);

Input.displayName = "Input";
