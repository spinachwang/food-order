/**
 * F050 ChatShell — 顶层单页布局 (M1)
 *
 * 当前为脚手架占位: 验证 token + 字体 + global.css 生效,
 * 并给 vite / vitest 一个 stable 入口. 真正的组件拆分在 Phase C / D.
 */
export default function ChatShell(): JSX.Element {
  return (
    <main className="shell" data-od-id="shell">
      <div style={{ padding: 48, fontFamily: 'var(--f-display)', color: 'var(--fg)' }}>
        <h1 style={{ fontSize: 'clamp(40px, 5.5vw, 72px)' }}>
          今天中午,<em style={{ color: 'var(--accent-deep)' }}>吃点好的</em>
        </h1>
        <p style={{ color: 'var(--muted)', fontFamily: 'var(--f-mono)' }}>
          ChatShell 骨架就绪 — Phase C / D 接入组件.
        </p>
      </div>
    </main>
  )
}