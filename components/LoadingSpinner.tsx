
import React from 'react';

interface LoadingSpinnerProps {
  message?: string;
  size?: 'small' | 'medium' | 'large';
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ message = "Loading articles...", size = 'large' }) => {
  const sizeClasses = {
    small: 'h-4 w-4',
    medium: 'h-8 w-8', 
    large: 'h-16 w-16'
  };
  
  const containerClasses = size === 'small' ? 'flex items-center space-x-2' : 'flex flex-col items-center justify-center space-y-4 my-10';
  
  return (
    <div className={containerClasses}>
      <div className={`animate-spin rounded-full border-t-4 border-b-4 border-blue-500 ${sizeClasses[size]}`}></div>
      {message && (
        <p className={`text-gray-600 ${size === 'small' ? 'text-sm' : 'text-lg'}`}>{message}</p>
      )}
    </div>
  );
};

export default LoadingSpinner;
