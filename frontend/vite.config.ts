import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import fs from 'node:fs'
import path from 'node:path'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

const frontendRoot = fileURLToPath(new URL('.', import.meta.url))

// `public/_dev/` 只放开发用的原型页面，不能进入发行包。
// 注意：Vite 在写 bundle 之前就整体复制 public 目录到 outDir，这些文件不在 rollup
// bundle 里，因此不能用 generateBundle 过滤（那样写永远不会命中），必须在产物落盘后
// 从输出目录删除。
function excludePublicDev(): Plugin {
  let outDir = ''
  return {
    name: 'exclude-public-dev',
    apply: 'build',
    configResolved(config) {
      outDir = path.resolve(config.root, config.build.outDir)
    },
    closeBundle() {
      fs.rmSync(path.join(outDir, '_dev'), { recursive: true, force: true })
    },
  }
}

export default defineConfig(({ command }) => ({
  root: frontendRoot,
  plugins: [
    vue(),
    Components({
      resolvers: [ElementPlusResolver({ importStyle: false })]
    }),
    excludePublicDev(),
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
    target: 'es2020',

    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor': ['vue'],
          'three': ['three'],
          'xterm': ['@xterm/xterm', '@xterm/addon-fit']
        }
      }
    },

    modulePreload: {
      polyfill: true,
      resolveDependencies(_filename, deps) {
        return deps.filter(dep => !/monaco|three|xterm|\.worker/i.test(dep))
      }
    },

    minify: 'esbuild',

    chunkSizeWarningLimit: 800,
    cssCodeSplit: true,

    commonjsOptions: {
      include: [/node_modules/],
      transformMixedEsModules: true
    }
  },

  optimizeDeps: {
    include: [
      'vue',
      'element-plus',
      '@element-plus/icons-vue',
      '@vueuse/core'
    ],
    exclude: ['monaco-editor']
  },

  // 构建期用 esbuild 压缩（比 terser 快一个数量级），并在产物中移除 console/debugger。
  // esbuild 的 drop 选项只在构建时生效，开发模式保留调试输出。
  esbuild: {
    drop: command === 'build' ? ['console', 'debugger'] : []
  }
}))
