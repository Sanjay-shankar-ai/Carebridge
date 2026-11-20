import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./context/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#F8FAFC",
        surface: "#FFFFFF",
        border: "#E2E8F0",
        primary: {
          DEFAULT: "#0F766E",
          hover: "#115E59",
          tint: "#E6F4F1",
        },
        text: {
          primary: "#0F172A",
          secondary: "#475569",
          muted: "#64748B",
        },
        success: {
          DEFAULT: "#15803D",
          tint: "#DCFCE7",
          text: "#14532D",
        },
        warning: {
          DEFAULT: "#B45309",
          tint: "#FEF3C7",
          text: "#78350F",
        },
        error: {
          DEFAULT: "#B91C1C",
          tint: "#FEE2E2",
          text: "#7F1D1D",
        },
        blue: {
          DEFAULT: "#2563EB",
          tint: "#EFF6FF",
          text: "#1E40AF",
        },
        purple: {
          DEFAULT: "#7E22CE",
          tint: "#F3E8FF",
          text: "#581C87",
        },
        grey: {
          DEFAULT: "#64748B",
          tint: "#F1F5F9",
          text: "#334155",
        },
      },
      borderRadius: {
        card: "12px",
        btn: "8px",
        input: "8px",
      },
      boxShadow: {
        soft: "0 1px 3px 0 rgba(15, 23, 42, 0.08)",
        modal: "0 10px 25px -5px rgba(15, 23, 42, 0.1), 0 8px 10px -6px rgba(15, 23, 42, 0.04)",
      },
      maxWidth: {
        container: "1280px",
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
