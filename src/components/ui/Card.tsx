import React from 'react';
import './Card.css';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  elevated?: boolean;
  clickable?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
}

export const Card: React.FC<CardProps> = ({
  children,
  className,
  elevated = false,
  clickable = false,
  onClick,
  style,
}) => {
  return (
    <div
      className={`card ${elevated ? 'card--elevated' : ''} ${clickable ? 'card--clickable' : ''} ${
        className || ''
      }`}
      onClick={onClick}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      style={style}
    >
      {children}
    </div>
  );
};

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'primary' | 'success' | 'warning' | 'error' | 'info' | 'gray';
  size?: 'sm' | 'md';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  className,
}) => {
  return (
    <span className={`badge badge--${variant} badge--${size} ${className || ''}`}>
      {children}
    </span>
  );
};

interface StatusBadgeProps {
  status: string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className }) => {
  const statusMap: Record<string, 'success' | 'warning' | 'error' | 'info'> = {
    active: 'success',
    pending: 'warning',
    completed: 'success',
    cancelled: 'error',
    confirmed: 'success',
  };

  const variant = statusMap[status] || 'info';
  const label = status.charAt(0).toUpperCase() + status.slice(1);

  return (
    <Badge variant={variant} className={className}>
      {label}
    </Badge>
  );
};

interface AlertProps {
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  onClose?: () => void;
  className?: string;
}

export const Alert: React.FC<AlertProps> = ({
  type,
  message,
  onClose,
  className,
}) => {
  return (
    <div className={`alert alert--${type} ${className || ''}`}>
      <div className="alert-content">{message}</div>
      {onClose && (
        <button
          className="alert-close"
          onClick={onClose}
          aria-label="Close alert"
        >
          ×
        </button>
      )}
    </div>
  );
};

interface DividerProps {
  className?: string;
  vertical?: boolean;
  text?: string;
}

export const Divider: React.FC<DividerProps> = ({
  className,
  vertical = false,
  text,
}) => {
  if (vertical) {
    return <div className={`divider divider--vertical ${className || ''}`} />;
  }

  if (text) {
    return (
      <div className={`divider divider--with-text ${className || ''}`}>
        <span>{text}</span>
      </div>
    );
  }

  return <div className={`divider ${className || ''}`} />;
};

interface LoadingSkeletonProps {
  count?: number;
  height?: number;
  circle?: boolean;
  className?: string;
}

export const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({
  count = 1,
  height = 20,
  circle = false,
  className,
}) => {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={`skeleton ${className || ''}`}
          style={{
            height: circle ? height : `${height}px`,
            borderRadius: circle ? '50%' : 'var(--radius-lg)',
            marginBottom: i < count - 1 ? 'var(--spacing-md)' : 0,
          }}
        />
      ))}
    </>
  );
};
