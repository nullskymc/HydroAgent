import { ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'icon'

const variantClasses: Record<ButtonVariant, string> = {
  primary: 'ui-button ui-button-primary',
  secondary: 'ui-button ui-button-secondary',
  ghost: 'ui-button ui-button-ghost',
  danger: 'ui-button ui-button-danger',
}

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'ui-button-sm',
  md: 'ui-button-md',
  icon: 'ui-button-icon',
}

export function Button({
  className,
  variant = 'primary',
  size = 'md',
  type = 'button',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: ButtonSize
}) {
  return <button type={type} className={cn(variantClasses[variant], sizeClasses[size], className)} {...props} />
}
