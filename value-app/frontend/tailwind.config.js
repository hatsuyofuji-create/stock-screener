/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 4象限の色（仕様書 4.7）
        honmei: '#16a34a',      // 本命ゾーン（緑）
        trap: '#dc2626',        // バリュートラップ警告（赤）
        expensive: '#2563eb',   // 健全だが割高（青）
        out: '#9ca3af',         // 対象外（灰）
      },
    },
  },
  plugins: [],
}
