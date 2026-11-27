module.exports = {
  content: ["./main.tsx", "./components/*.tsx"],
  theme: {
    extend: {
      colors: {
        background: "var(--background)", foreground: "var(--foreground)",
        input: "var(--line)", ring: "var(--ring)",
        primary: { DEFAULT: "#eaeaea", foreground: "#141414" },
        secondary: { DEFAULT: "#262626", foreground: "#f2f2f2" },
        accent: { DEFAULT: "#2f2f2f", foreground: "#f2f2f2" },
        destructive: { DEFAULT: "#ef4444", foreground: "#141414" },
      },
    },
  },
}
