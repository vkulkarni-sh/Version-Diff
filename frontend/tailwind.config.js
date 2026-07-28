/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // OASYS violet palette (shared across the tools suite). Tailwind drops
        // any class whose shade isn't defined, so every amelia-N used in JSX
        // must be listed here.
        amelia: {
          200: '#ddd6fe',
          300: '#c4b5fd',
          400: '#a78bfa',
          500: '#8b5cf6',
          600: '#6d3eff',
          700: '#5b2fd9',
          800: '#4c1d95',
          900: '#2e1065',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
