import { ButtonHTMLAttributes, ReactNode } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary'
  size?: 'sm' | 'md'
  block?: boolean
  loading?: boolean
  children: ReactNode
}

/**
 * Thin wrapper around the existing .btn / .btn-primary / .btn-secondary
 * classes from global.css, so markup stays consistent without changing
 * any visual behavior already relied upon elsewhere in the app.
 */
export default function Button({
  variant = 'primary',
  size = 'md',
  block = false,
  loading = false,
  disabled,
  className = '',
  children,
  ...rest
}: ButtonProps) {
  const classes = [
    'btn',
    variant === 'primary' ? 'btn-primary' : 'btn-secondary',
    size === 'sm' ? 'btn-sm' : '',
    block ? 'btn-block' : '',
    className,
  ].filter(Boolean).join(' ')

  return (
    <button className={classes} disabled={disabled || loading} {...rest}>
      {loading && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  )
}
