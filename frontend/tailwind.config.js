/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans:  ['"Pretendard Variable"', 'Pretendard', '"Apple SD Gothic Neo"', '"Noto Sans KR"', '"Malgun Gothic"', '"Segoe UI"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        serif: ['"Pretendard Variable"', 'Pretendard', '"Apple SD Gothic Neo"', '"Noto Sans KR"', '"Malgun Gothic"', '"Segoe UI"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono:  ['"JetBrains Mono"', 'Consolas', '"Courier New"', 'monospace'],
      },
      colors: {
        navy: {
          DEFAULT: '#192340',
          dark: '#0d1628',
          mid: '#243358',
          subtle: '#e6eaf4',
        },
        amber: {
          brand: '#c07010',
          light: '#fef4e3',
        },
      },
      maxWidth: {
        '8xl': '90rem',
      },
    },
  },
  plugins: [],
};
