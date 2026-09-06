// User roles
export const UserRole = {
  PASSENGER: 'passenger',
  DRIVER: 'driver',
  ADMIN: 'admin',
} as const;
export type UserRole = typeof UserRole[keyof typeof UserRole];

// Journey status
export const JourneyStatus = {
  ACTIVE: 'active',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
} as const;
export type JourneyStatus = typeof JourneyStatus[keyof typeof JourneyStatus];

// Booking status
export const BookingStatus = {
  PENDING: 'pending',
  CONFIRMED: 'confirmed',
  CANCELLED: 'cancelled',
  COMPLETED: 'completed',
} as const;
export type BookingStatus = typeof BookingStatus[keyof typeof BookingStatus];

// User profile
export interface User {
  id: string;
  name: string;
  email: string;
  phone: string;
  role: UserRole;
  avatar?: string;
  rating?: number;
  reviews?: number;
  createdAt: Date;
}

// Journey / Ride
export interface Journey {
  id: string;
  driverId: string;
  driver: User;
  from: string;
  to: string;
  date: string;
  departureTime: string;
  arrivalTime: string;
  availableSeats: number;
  totalSeats: number;
  pricePerSeat: number;
  vehicle: Vehicle;
  status: JourneyStatus;
  description?: string;
  stops?: string[];
  createdAt: Date;
}

// Booking / Reservation
export interface Booking {
  id: string;
  journeyId: string;
  passengerId: string;
  passenger: User;
  journey: Journey;
  seatsBooked: number;
  totalPrice: number;
  status: BookingStatus;
  bookingReference: string;
  createdAt: Date;
  pickupLocation?: string;
  dropoffLocation?: string;
}

// Vehicle
export interface Vehicle {
  id: string;
  driverId: string;
  registrationNumber: string;
  vehicleType: VehicleType;
  model: string;
  colour: string;
  seatingCapacity: number;
  image?: string;
  createdAt: Date;
}

export const VehicleType = {
  SEDAN: 'sedan',
  SUV: 'suv',
  HATCHBACK: 'hatchback',
  MINIVAN: 'minivan',
  VAN: 'van',
} as const;
export type VehicleType = typeof VehicleType[keyof typeof VehicleType];

// Search/Filter parameters
export interface SearchParams {
  from: string;
  to: string;
  date: string;
  seats: number;
}

export interface JourneyFilterOptions {
  price?: {
    min: number;
    max: number;
  };
  departureTime?: {
    min: string;
    max: string;
  };
  availableSeats?: number;
  vehicleType?: VehicleType;
  rating?: number;
}

export interface JourneySortOption {
  field: 'price' | 'departureTime' | 'rating';
  order: 'asc' | 'desc';
}

// API Response
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

// Authentication
export interface AuthContext {
  user: User | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  register: (userData: RegisterData) => Promise<void>;
  setUser: (user: User | null) => void;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  name: string;
  email: string;
  phone: string;
  password: string;
  confirmPassword: string;
  role?: UserRole;
}

export interface PasswordResetRequest {
  email: string;
}

export interface ResetPasswordData {
  token: string;
  password: string;
  confirmPassword: string;
}

// Notification
export interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  duration?: number;
}
