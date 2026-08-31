/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  future: {
    hoverOnlyWhenSupported: true,
  },
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        surface: {
          DEFAULT: "var(--surface)",
          secondary: "var(--surface-secondary)",
          elevated: "var(--surface-elevated)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        border: {
          DEFAULT: "var(--border)",
          strong: "var(--border-strong)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          hover: "var(--primary-hover)",
          foreground: "var(--primary-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
          50: "#f5efe6",
          100: "#ebe1d2",
          200: "#dccbb3",
          300: "#c4ae93",
          400: "#b59a78",
          500: "#9a8062",
          600: "#806a50",
          700: "#67553f",
          800: "#4f4233",
          900: "#3a3228",
          950: "#29231e",
        },
        ink: {
          50: "#faf7f2",
          100: "#f5efe6",
          200: "#e8decf",
          300: "#c4b5a3",
          400: "#9a8d7e",
          500: "#746b61",
          600: "#5c534b",
          700: "#46392e",
          800: "#342b24",
          900: "#29231e",
          950: "#1c1814",
        },
        success: "var(--success)",
        warning: "var(--warning)",
        danger: {
          DEFAULT: "var(--danger)",
          500: "#e11d48",
          600: "#be123c",
        },
        warn: {
          500: "#d97706",
          600: "#b45309",
        },
      },
      fontFamily: {
        sans: ['"Geist Variable"', "ui-sans-serif", "system-ui", "sans-serif"],
        display: ['"Geist Variable"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"Geist Mono Variable"', "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
      },
      boxShadow: {
        soft: "var(--shadow-floating)",
        floating: "var(--shadow-floating)",
      },
    },
  },
  plugins: [],
};
