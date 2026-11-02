import {
  X,
  LoaderCircle,
  AlertTriangle,
  Inbox,
  type LucideIcon,
} from 'lucide-react'
import {
  useEffect,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  icon?: LucideIcon
  loading?: boolean
}

export const Button = ({
  variant = 'secondary',
  size = 'md',
  icon: Icon,
  loading,
  className = '',
  children,
  disabled,
  ...props
}: ButtonProps) => (
  <button
    className={`button button-${variant} button-${size} ${className}`.trim()}
    disabled={disabled || loading}
    {...props}
  >
    {loading ? <LoaderCircle className="spin" size={16} /> : Icon ? <Icon size={16} /> : null}
    {children}
  </button>
)

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string
  icon: LucideIcon
  size?: 'sm' | 'md'
}

export const IconButton = ({
  label,
  icon: Icon,
  size = 'md',
  className = '',
  ...props
}: IconButtonProps) => (
  <button
    className={`icon-button icon-button-${size} ${className}`.trim()}
    aria-label={label}
    title={label}
    {...props}
  >
    <Icon size={size === 'sm' ? 15 : 17} />
  </button>
)

export const Badge = ({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'success' | 'danger' | 'warning' | 'info'
}) => <span className={`badge badge-${tone}`}>{children}</span>

export const ProgressBar = ({
  value,
  label,
  compact = false,
}: {
  value: number
  label?: string
  compact?: boolean
}) => (
  <div className={`progress-wrap ${compact ? 'progress-compact' : ''}`}>
    {label ? (
      <div className="progress-meta">
        <span>{label}</span>
        <span>{value}%</span>
      </div>
    ) : null}
    <div
      className="progress-track"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
    >
      <div className="progress-fill" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  </div>
)

export const PageHeader = ({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
}) => (
  <header className="page-header">
    <div>
      {eyebrow ? <div className="page-eyebrow">{eyebrow}</div> : null}
      <h1 className="page-title">{title}</h1>
      {description ? <p className="page-description">{description}</p> : null}
    </div>
    {actions ? <div className="page-actions">{actions}</div> : null}
  </header>
)

export const Modal = ({
  open,
  title,
  description,
  children,
  footer,
  onClose,
  width = 'md',
  danger = false,
}: {
  open: boolean
  title: string
  description?: string
  children?: ReactNode
  footer?: ReactNode
  onClose: () => void
  width?: 'sm' | 'md' | 'lg' | 'xl'
  danger?: boolean
}) => {
  useEffect(() => {
    if (!open) return
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    document.body.classList.add('modal-open')
    return () => {
      window.removeEventListener('keydown', handleKey)
      document.body.classList.remove('modal-open')
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className={`modal modal-${width} ${danger ? 'modal-danger' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <div>
            <h2 id="modal-title">{title}</h2>
            {description ? <p>{description}</p> : null}
          </div>
          <IconButton label="关闭" icon={X} onClick={onClose} />
        </header>
        {children ? <div className="modal-body">{children}</div> : null}
        {footer ? <footer className="modal-footer">{footer}</footer> : null}
      </section>
    </div>
  )
}

export const EmptyState = ({
  icon: Icon = Inbox,
  title,
  description,
  action,
}: {
  icon?: LucideIcon
  title: string
  description: string
  action?: ReactNode
}) => (
  <div className="empty-state">
    <div className="empty-icon">
      <Icon size={22} />
    </div>
    <h3>{title}</h3>
    <p>{description}</p>
    {action ? <div className="empty-action">{action}</div> : null}
  </div>
)

export const InlineError = ({ children }: { children: ReactNode }) => (
  <div className="inline-error" role="alert">
    <AlertTriangle size={16} />
    <span>{children}</span>
  </div>
)

export const Field = ({
  label,
  hint,
  error,
  children,
  className = '',
}: {
  label: string
  hint?: string
  error?: string
  children: ReactNode
  className?: string
}) => (
  <label className={`field ${className}`.trim()}>
    <span className="field-label">{label}</span>
    {children}
    {hint ? <span className="field-hint">{hint}</span> : null}
    {error ? <span className="field-error">{error}</span> : null}
  </label>
)

export const TextInput = ({
  className = '',
  ...props
}: InputHTMLAttributes<HTMLInputElement>) => (
  <input className={`text-input ${className}`.trim()} {...props} />
)

export const SelectInput = ({
  className = '',
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={`text-input select-input ${className}`.trim()} {...props}>
    {children}
  </select>
)

export const Checkbox = ({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  disabled?: boolean
}) => (
  <label className={`checkbox ${disabled ? 'is-disabled' : ''}`}>
    <input
      type="checkbox"
      checked={checked}
      onChange={(event) => onChange(event.target.checked)}
      disabled={disabled}
    />
    <span>{label}</span>
  </label>
)

export const LoadingBlock = ({ label = '加载中' }: { label?: string }) => (
  <div className="loading-block">
    <LoaderCircle className="spin" size={18} />
    <span>{label}</span>
  </div>
)

export const Divider = () => <div className="divider" />
