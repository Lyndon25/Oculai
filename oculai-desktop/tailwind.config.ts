import type { Config } from "tailwindcss";

export default {
  content: ["./src/renderer/**/*.{ts,tsx,html}"],
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: "#FF5E3A",
          soft: "rgba(255, 94, 58, 0.08)",
          hover: "#FF7A5C",
          press: "#E0482A",
        },
        surface: {
          DEFAULT: "#FFFFFF",
          hover: "#F5F5F5",
          press: "#EBEBEB",
        },
        canvas: {
          DEFAULT: "#FAFAFA",
        },
        ink: {
          DEFAULT: "#171717",
          secondary: "#737373",
          muted: "#A3A3A3",
          inverse: "#FFFFFF",
        },
        rule: {
          DEFAULT: "#E5E5E5",
          strong: "#D4D4D4",
          hover: "#A3A3A3",
        },
        semantic: {
          success: "#16A34A",
          "success-soft": "rgba(22, 163, 74, 0.08)",
          warning: "#D97706",
          "warning-soft": "rgba(217, 119, 6, 0.08)",
          error: "#DC2626",
          "error-soft": "rgba(220, 38, 38, 0.08)",
        },
      },
      fontFamily: {
        sans: [
          "Space Grotesk",
          "PingFang SC",
          "Microsoft YaHei",
          "system-ui",
          "sans-serif",
        ],
        display: [
          "Archivo",
          "PingFang SC",
          "Microsoft YaHei",
          "system-ui",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
      },
      borderRadius: {
        sm: "6px",
        DEFAULT: "10px",
        lg: "14px",
        xl: "20px",
      },
    },
  },
  plugins: [],
} satisfies Config;
