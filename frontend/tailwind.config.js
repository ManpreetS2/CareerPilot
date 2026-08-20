/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#E5E7EB",
          100: "#D1D5DB",
          200: "#CBD5E1",
          300: "#94A3B8",
          400: "#64748B",
          500: "#64748B",
          600: "#475569",
          700: "#334155",
          800: "#1E293B",
          900: "#121821",
          950: "#0B0F14",
        },
        accent: {
          50: "#F0F9FF",
          100: "#E0F2FE",
          200: "#BAE6FD",
          300: "#7DD3FC",
          400: "#7DD3FC",
          500: "#38BDF8",
          600: "#0EA5E9",
          700: "#0284C7",
          800: "#0369A1",
          900: "#0C4A6E",
          950: "#082F49",
        },
        sand: {
          50: "#F8FAFC",
          100: "#F1F5F9",
          200: "#E2E8F0",
        },
        danger: {
          500: "#b42318",
          600: "#912018",
        },
        warn: {
          500: "#b54708",
          600: "#93370d",
        },
      },
      fontFamily: {
        display: ['"Source Serif 4"', "Georgia", "serif"],
        sans: ['"DM Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        soft: "0 12px 40px -24px rgba(11, 15, 20, 0.65)",
      },
    },
  },
  plugins: [],
};
