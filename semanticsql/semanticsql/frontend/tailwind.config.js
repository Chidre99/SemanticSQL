/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        // Calm dark palette; pick distinct accent for status changes
        bg:      { DEFAULT: "#0b0d10", panel: "#13161b", soft: "#1a1e25" },
        ink:     { DEFAULT: "#e8eaed", muted: "#8a93a6", faint: "#5a6478" },
        accent:  { DEFAULT: "#7ab7ff", weak: "#2b4a73" },
        ok:      { DEFAULT: "#7adf8a" },
        warn:    { DEFAULT: "#f3c969" },
        err:     { DEFAULT: "#ff7a7a" },
      },
    },
  },
  plugins: [],
};
