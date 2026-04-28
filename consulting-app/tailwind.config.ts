import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f5f7ff",
          100: "#e4e9ff",
          500: "#4f5bd5",
          600: "#3f49b5",
          700: "#2f3795",
        },
      },
    },
  },
  plugins: [],
};

export default config;
