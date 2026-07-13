/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'bg-deep': '#121212',
        'bg-elevated': '#1e1e1e',
        'border': '#2a2a2a',
        'text-secondary': '#888888',
        'text-muted': '#555555',
      },
    },
  },
  plugins: [],
}