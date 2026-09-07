import '@testing-library/jest-dom'

// jsdom 没有实现 `document.execCommand` (已被废弃)。
// F050 clip.ts 的降级路径依赖此方法; 测试中我们提供 mock, 让 vi.spyOn 可用。
if (typeof document !== 'undefined' && typeof document.execCommand !== 'function') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(document as any).execCommand = () => true
}