import React from 'react';
import './StateComponents.css';
import { LoadingSkeleton } from './Card';

export const LoadingState: React.FC<{ message?: string }> = ({
  message = 'Loading...',
}) => {
  return (
    <div className="state-container loading-state">
      <div className="spinner-large"></div>
      <p>{message}</p>
    </div>
  );
};

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  message: string;
  action?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  message,
  action,
}) => {
  return (
    <div className="state-container empty-state">
      {icon && <div className="empty-state-icon">{icon}</div>}
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-message">{message}</p>
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
};

interface ErrorStateProps {
  title?: string;
  message: string;
  action?: React.ReactNode;
  retry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Oops! Something went wrong',
  message,
  action,
  retry,
}) => {
  return (
    <div className="state-container error-state">
      <div className="error-state-icon">⚠️</div>
      <h3 className="error-state-title">{title}</h3>
      <p className="error-state-message">{message}</p>
      {action ? (
        <div className="error-state-action">{action}</div>
      ) : retry ? (
        <button className="btn btn--primary" onClick={retry}>
          Try Again
        </button>
      ) : null}
    </div>
  );
};

interface PageLoadingProps {
  skeletonsCount?: number;
}

export const PageLoading: React.FC<PageLoadingProps> = ({
  skeletonsCount = 3,
}) => {
  return (
    <div className="page-loading">
      {Array.from({ length: skeletonsCount }).map((_, i) => (
        <div key={i} style={{ marginBottom: '1.5rem' }}>
          <LoadingSkeleton height={200} />
        </div>
      ))}
    </div>
  );
};
