/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#182338",
        mist: "#f4f7fb",
        teal: "#0d9488",
      },
    },
  },
  plugins: [],
};
