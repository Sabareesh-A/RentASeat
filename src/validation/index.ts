// Validation utilities
export const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const PHONE_REGEX = /^[+]?[(]?[0-9]{1,3}[)]?[-\s.]?[0-9]{1,4}[-\s.]?[0-9]{1,4}$/;

export interface ValidationError {
  field: string;
  message: string;
}

export interface PasswordStrength {
  score: number; // 0-5
  strength: 'very-weak' | 'weak' | 'fair' | 'good' | 'strong';
  feedback: string[];
}

export const validateEmail = (email: string): boolean => {
  return EMAIL_REGEX.test(email);
};

export const validatePhone = (phone: string): boolean => {
  return PHONE_REGEX.test(phone.replace(/\s/g, ''));
};

export const validatePassword = (password: string): PasswordStrength => {
  const feedback: string[] = [];
  let score = 0;

  if (password.length === 0) {
    return {
      score: 0,
      strength: 'very-weak',
      feedback: ['Password is required'],
    };
  }

  if (password.length >= 8) score++;
  else feedback.push('At least 8 characters');

  if (password.length >= 12) score++;

  if (/[a-z]/.test(password)) score++;
  else feedback.push('At least one lowercase letter');

  if (/[A-Z]/.test(password)) score++;
  else feedback.push('At least one uppercase letter');

  if (/[0-9]/.test(password)) score++;
  else feedback.push('At least one number');

  if (/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password)) score++;
  else feedback.push('At least one special character');

  const strengthMap: Record<number, PasswordStrength['strength']> = {
    0: 'very-weak',
    1: 'weak',
    2: 'fair',
    3: 'good',
    4: 'good',
    5: 'strong',
  };

  return {
    score: Math.min(score, 5),
    strength: strengthMap[score],
    feedback,
  };
};

export const validatePasswordMatch = (
  password: string,
  confirmPassword: string
): boolean => {
  return password === confirmPassword && password.length > 0;
};

export const validateName = (name: string): boolean => {
  return name.trim().length >= 2 && name.trim().length <= 100;
};

export const validateForm = (
  formData: Record<string, any>,
  rules: Record<string, (value: any) => boolean | ValidationError>
): ValidationError[] => {
  const errors: ValidationError[] = [];

  Object.entries(rules).forEach(([field, rule]) => {
    const result = rule(formData[field]);
    if (result instanceof Object && 'message' in result) {
      errors.push(result);
    } else if (result === false) {
      errors.push({
        field,
        message: `${field} is invalid`,
      });
    }
  });

  return errors;
};
