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
        'bg-card': 'rgba(255,255,255,0.04)',
        'bg-glass': 'rgba(30,30,30,0.72)',
        'border-default': '#2a2a2a',
        'border-light': '#333333',
        'text-secondary': '#888888',
        'text-muted': '#555555',
      },
      borderRadius: {
        card: '12px',
        btn: '8px',
      },
      boxShadow: {
        card: '0 2px 12px rgba(0,0,0,0.3)',
        'card-hover': '0 4px 20px rgba(0,0,0,0.45)',
        glass: '0 8px 32px rgba(0,0,0,0.4)',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}