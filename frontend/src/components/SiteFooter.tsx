/**
 * 全站页脚：展示 ICP 备案号，按工信部要求链接到备案管理系统首页。
 * 备案号必须原样展示，不能拆分或加空格，否则备案核查不通过。
 */
export const ICP_NUMBER = '苏ICP备2026067314号-1'
export const ICP_LINK = 'https://beian.miit.gov.cn/'

type SiteFooterProps = {
  className?: string
}

export const SiteFooter = ({ className }: SiteFooterProps) => (
  <footer className={className ? `site-footer ${className}` : 'site-footer'}>
    <a href={ICP_LINK} target="_blank" rel="noopener noreferrer">
      {ICP_NUMBER}
    </a>
  </footer>
)
