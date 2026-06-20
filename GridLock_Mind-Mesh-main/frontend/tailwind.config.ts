import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        muted: "hsl(var(--muted))",
        panel: "hsl(var(--panel))",
        primary: "hsl(var(--primary))",
        accent: "hsl(var(--accent))",
        risk: "hsl(var(--risk))",
        blind: "hsl(var(--blind))"
      }
    }
  },
  plugins: []
};

export default config;
