/** Paleta agro: folha (verde), trigo (âmbar), terra (marrom), céu (azul de água). */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        marca: ['"Outfit"', "Inter", "sans-serif"],
        display: ["'Plus Jakarta Sans'", "Inter", "system-ui", "sans-serif"],
      },
      colors: {
        folha: {
          50: "#f1f8f1", 100: "#ddefdc", 200: "#bcdfba", 300: "#8fc78d", 400: "#5fa95d",
          500: "#3f8c3e", 600: "#2f7030", 700: "#275a29", 800: "#224824", 900: "#1c3b1f", 950: "#0d2011",
        },
        trigo: {
          50: "#fdf9ec", 100: "#f9eecb", 200: "#f3dc93", 300: "#ecc55a", 400: "#e6b034",
          500: "#d6921f", 600: "#b97018", 700: "#945118", 800: "#7a411a", 900: "#663719",
        },
        terra: { 50: "#f8f5f1", 100: "#ede6dc", 300: "#c9b49a", 500: "#9a7b58", 700: "#6b5139", 900: "#3d2e21" },
      },
      boxShadow: {
        cartao: "0 1px 2px rgba(16,40,20,.06), 0 4px 16px rgba(16,40,20,.06)",
      },
    },
  },
  plugins: [],
};
