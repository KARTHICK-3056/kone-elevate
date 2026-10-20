/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Industrial enterprise palette.
        navy: {
          50: '#f2f5fa',
          100: '#e2e9f4',
          200: '#c5d3e8',
          300: '#9bb2d5',
          400: '#6a89bd',
          500: '#4869a3',
          600: '#365188',
          700: '#2b406e',
          800: '#1d2d4e',
          900: '#0f1c33',
          950: '#0a1526',
        },
        steel: {
          50: '#f6f7f9',
          100: '#eceef2',
          200: '#d5dae3',
          300: '#b0bac9',
          400: '#8593aa',
          500: '#66758f',
          600: '#515e76',
          700: '#434d60',
          800: '#3a4252',
          900: '#333a46',
        },
        accent: {
          DEFAULT: '#0aa2c0',
          light: '#3fc4de',
          dark: '#077f97',
        },
        reuse: '#0f9d58',
        refurbish: '#1a73e8',
        recycle: '#f4a300',
        dispose: '#d93025',
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'Menlo', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(15, 28, 51, 0.06), 0 4px 16px rgba(15, 28, 51, 0.06)',
        elevated: '0 8px 30px rgba(15, 28, 51, 0.12)',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.25s ease-out',
        shimmer: 'shimmer 1.6s infinite',
      },
    },
  },
  plugins: [],
};
