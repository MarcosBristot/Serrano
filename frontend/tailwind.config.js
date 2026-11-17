/**
 * Paleta agro do painel, em variáveis (src/index.css): o tema é escuro, de campo à noite, com
 * vidro sobre a lavoura. As escalas "folha", "trigo" e "terra" são invertidas no tema (950 =
 * texto claro, 50 = superfície escura), então as classes das páginas continuam valendo.
 * "broto" é o verde vivo de destaque e "noite" o fundo, fixos.
 */
const escala = (nome, tons) =>
  Object.fromEntries(tons.map((t) => [t, `rgb(var(--${nome}-${t}) / <alpha-value>)`]));
const TONS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

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
        folha: escala("folha", TONS),
        trigo: escala("trigo", TONS.slice(0, 10)),
        terra: { 50: "rgb(var(--terra-50) / <alpha-value>)", 100: "rgb(var(--terra-100) / <alpha-value>)",
          300: "rgb(var(--terra-300) / <alpha-value>)", 500: "rgb(var(--terra-500) / <alpha-value>)",
          700: "rgb(var(--terra-700) / <alpha-value>)", 900: "rgb(var(--terra-900) / <alpha-value>)" },
        broto: { 300: "#c8ec8a", 400: "#a8dc5c", 500: "#8cc63f", 600: "#6fa82e", 700: "#558526" },
        noite: { 700: "#1d3a22", 800: "#132a18", 900: "#0c1f11", 950: "#07150b" },
        superficie: "rgb(var(--superficie) / <alpha-value>)",
      },
      boxShadow: {
        cartao: "0 1px 0 rgba(255,255,255,.06) inset, 0 10px 30px rgba(0,0,0,.28)",
      },
    },
  },
  plugins: [],
};
