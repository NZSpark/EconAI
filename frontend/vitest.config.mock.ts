import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test-setup.ts',
    css: true,
    include: ['src/__tests__/mock_test/**/*.test.tsx'],
  },
});
