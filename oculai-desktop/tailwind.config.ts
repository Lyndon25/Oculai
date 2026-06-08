import type { Config } from "tailwindcss";

export default {
  content: ["./src/renderer/**/*.{ts,tsx,html}"],
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: "#E85D3F",
          soft: "rgba(232, 93, 63, 0.07)",
          hover: "#D44C2F",
          press: "#BF3D22",
          glow: "rgba(232, 93, 63, 0.15)",
        },
        surface: {
          DEFAULT: "#FFFFFF",
          raised: "#FFFFFF",
          hover: "#F4F1ED",
          press: "#EDE9E4",
          glass: "rgba(255, 255, 255, 0.72)",
        },
        canvas: {
          DEFAULT: "#FAF8F5",
        },
        ink: {
          DEFAULT: "#1B1918",
          secondary: "#6B6560",
          muted: "#9E9892",
          inverse: "#FFFFFF",
          accent: "#D44C2F",
        },
        rule: {
          DEFAULT: "#EBE6E0",
          strong: "#DBD4CC",
          hover: "#B8AFA5",
        },
        warm: {
          50: "#FDF8F3",
          100: "#F8EFE6",
          200: "#EDE0D2",
          300: "#D6C5B3",
          500: "#A08972",
          700: "#6B5744",
          900: "#3D2E20",
        },
        semantic: {
          success: "#4A9670",
          "success-soft": "rgba(74, 150, 112, 0.08)",
          "success-muted": "#D9EDE2",
          warning: "#C2853A",
          "warning-soft": "rgba(194, 133, 58, 0.08)",
          "warning-muted": "#F8EDDC",
          error: "#C5554A",
          "error-soft": "rgba(197, 85, 74, 0.08)",
          "error-muted": "#F5DDDA",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "PingFang SC",
          "Microsoft YaHei",
          "system-ui",
          "-apple-system",
          "sans-serif",
        ],
        display: [
          "DM Serif Display",
          "PingFang SC",
          "Noto Serif SC",
          "SimSun",
          "serif",
        ],
        mono: [
          "JetBrains Mono",
          "Fira Code",
          "Consolas",
          "Courier New",
          "monospace",
        ],
      },
      borderRadius: {
        sm: "8px",
        DEFAULT: "12px",
        lg: "16px",
        xl: "24px",
        "2xl": "32px",
      },
      boxShadow: {
        xs: "0 1px 2px rgba(27, 25, 24, 0.04)",
        sm: "0 1px 3px rgba(27, 25, 24, 0.05), 0 1px 2px rgba(27, 25, 24, 0.03)",
        md: "0 4px 12px rgba(27, 25, 24, 0.05), 0 1px 3px rgba(27, 25, 24, 0.04)",
        lg: "0 8px 24px rgba(27, 25, 24, 0.06), 0 2px 6px rgba(27, 25, 24, 0.03)",
        xl: "0 16px 40px rgba(27, 25, 24, 0.07), 0 4px 12px rgba(27, 25, 24, 0.04)",
        glow: "0 0 0 4px rgba(232, 93, 63, 0.15)",
        "card-hover":
          "0 12px 32px rgba(27, 25, 24, 0.07), 0 2px 8px rgba(27, 25, 24, 0.04)",
      },
      animation: {
        "fade-up": "fade-up 400ms var(--oc-spring-smooth) both",
        "scale-in": "scale-in 300ms var(--oc-spring-smooth) both",
        "slide-in-right":
          "slide-in-right 300ms var(--oc-spring-smooth) both",
        breathe: "breathe 2s ease-in-out infinite",
        shimmer: "shimmer 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
