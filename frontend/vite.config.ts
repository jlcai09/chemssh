import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

const frontendRoot = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  root: frontendRoot,
  plugins: [
    vue()
  ],

  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8888',
        changeOrigin: true,
        ws: true
      }
    }
  },

  build: {
    outDir: 'dist',
    emptyOutDir: true,

    // Chunk splitting for better caching and lazy loading
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor': ['vue'],
          'element-plus': ['element-plus', '@element-plus/icons-vue'],
          'three': ['three'],
          'monaco': ['monaco-editor'],
          'xterm': ['@xterm/xterm', '@xterm/addon-fit']
        }
      }
    },

    // Minification optimization
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
        pure_funcs: ['console.log']
      }
    },

    // Chunk size and CSS splitting
    chunkSizeWarningLimit: 1000,
    cssCodeSplit: true,

    // CommonJS optimization
    commonjsOptions: {
      include: [/node_modules/],
      transformMixedEsModules: true
    }
  },

  // Dependency optimization
  optimizeDeps: {
    include: ['vue', 'element-plus'],
    exclude: []
  }
})
