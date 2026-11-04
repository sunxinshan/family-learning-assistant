import { useEffect, useState } from 'react'

export interface KeyboardViewport {
  /** 输入法（软键盘）是否占住了屏幕下方 */
  keyboardOpen: boolean
  /** 视觉视口高度，CSS 像素 */
  height: number
  /** 视觉视口相对布局视口的顶部偏移（iOS 键盘弹起时页面会被往上推） */
  offsetTop: number
}

/** 视觉视口比正常高度矮这么多，就认为输入法弹起了。 */
const KEYBOARD_MIN_INSET = 120

/**
 * 监听手机软键盘：把「键盘占掉多少」变成可用的布局信息。
 *
 * 键盘弹起时 iOS Safari 的 `window.innerHeight` 不变、只有 `visualViewport` 变小，
 * Android Chrome 则是布局视口跟着缩。用「见过的最高的视觉视口」当基准，
 * 两种行为都能判断出来，且地址栏收起、横竖屏切换都不会误判成键盘。
 */
export function useKeyboardViewport(): KeyboardViewport {
  const [viewport, setViewport] = useState<KeyboardViewport>(() => ({
    keyboardOpen: false,
    height: typeof window === 'undefined' ? 0 : window.innerHeight,
    offsetTop: 0,
  }))

  useEffect(() => {
    const visual = window.visualViewport
    if (!visual) return

    let baseline = visual.height
    let lastWidth = visual.width
    let frame = 0

    const sync = () => {
      const height = visual.height
      const width = visual.width
      if (Math.abs(width - lastWidth) > 5) {
        // 横竖屏切换 / 窗口尺寸变了：重新取基准，别把新尺寸误判成键盘
        lastWidth = width
        baseline = height
      }
      if (height > baseline + 1) baseline = height
      const offsetTop = visual.offsetTop
      const keyboardOpen = baseline - height > KEYBOARD_MIN_INSET
      setViewport((current) =>
        current.keyboardOpen === keyboardOpen &&
        Math.abs(current.height - height) < 0.5 &&
        Math.abs(current.offsetTop - offsetTop) < 0.5
          ? current
          : { keyboardOpen, height, offsetTop },
      )
    }

    // 键盘弹出/收起是连续动画，合并到一帧里算，避免一路重渲染。
    const schedule = () => {
      if (frame) return
      frame = window.requestAnimationFrame(() => {
        frame = 0
        sync()
      })
    }

    sync()
    visual.addEventListener('resize', schedule)
    visual.addEventListener('scroll', schedule)
    return () => {
      if (frame) window.cancelAnimationFrame(frame)
      visual.removeEventListener('resize', schedule)
      visual.removeEventListener('scroll', schedule)
    }
  }, [])

  const { keyboardOpen } = viewport
  useEffect(() => {
    document.documentElement.classList.toggle('keyboard-open', keyboardOpen)
    return () => document.documentElement.classList.remove('keyboard-open')
  }, [keyboardOpen])

  return viewport
}
