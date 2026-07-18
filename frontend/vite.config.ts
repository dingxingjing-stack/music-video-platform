import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { compression } from 'vite-plugin-compression2';
import { visualizer } from 'rollup-plugin-visualizer';

const isProd = process.env.NODE_ENV === 'production';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'zyvexo-mark.svg'],
      manifest: {
        name: 'Zyvexo',
        short_name: 'Zyvexo',
        description: 'Zyvexo — Global Digital Platform',
        theme_color: '#121212',
        background_color: '#121212',
        display: 'standalone',
        orientation: 'portrait',
        scope: '/',
        start_url: '/',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      workbox: { globPatterns: [], runtimeCaching: [] },
    }),
    // Brotli 压缩（CF Pages 自动 gzip，brotli 需插件预生成 .br 文件）
    isProd && compression({ algorithm: 'brotliCompress', exclude: [/\.br$/, /\.gz$/, /\.html$/] }),
    // 打包体积分析（仅 build --mode analyze 时生成）
    process.env.ANALYZE && visualizer({
      filename: 'dist/stats.html',
      template: 'treemap',
      gzipSize: true,
      brotliSize: true,
    }),
  ].filter(Boolean),

  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': { target: 'http://localhost:8001', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8001', ws: true },
    },
  },

  build: {
    rollupOptions: {
      output: {
        // 分包：react / ui / audio 三大 vendor chunk
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-ui': ['framer-motion', 'clsx', 'tailwind-merge'],
          'vendor-audio': ['wavesurfer.js', 'tone'],
        },
        // 分类输出带 hash 文件名
        chunkFileNames: 'assets/js/[name]-[hash].js',
        entryFileNames: 'assets/js/[name]-[hash].js',
        assetFileNames: (info) => {
          if (info.name?.endsWith('.css')) return 'assets/css/[name]-[hash][extname]';
          if (/\.(png|jpe?g|gif|webp|svg)$/.test(info.name || '')) return 'assets/img/[name]-[hash][extname]';
          if (/\.(mp3|wav|ogg|flac|m4a)$/.test(info.name || '')) return 'assets/audio/[name]-[hash][extname]';
          if (/\.(woff2?|ttf|eot)$/.test(info.name || '')) return 'assets/fonts/[name]-[hash][extname]';
          return 'assets/misc/[name]-[hash][extname]';
        },
      },
    },
    target: 'esnext',
    minify: 'terser',
    terserOptions: {
      compress: { drop_console: isProd, drop_debugger: isProd },
    },
    // 小于 4KB 的图片转 base64，减少 HTTP 请求
    assetsInlineLimit: 4096,
    // 开启 CSS 代码分割
    cssCodeSplit: true,
    // sourcemap 仅开发
    sourcemap: !isProd,
  },
});
