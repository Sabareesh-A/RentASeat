import type {
  Journey,
  Booking,
  Vehicle,
  User,
  SearchParams,
  JourneyFilterOptions,
  JourneySortOption,
  ApiResponse,
  RegisterData,
} from '../types';
import { BookingStatus, JourneyStatus } from '../types';
import { request, ApiError } from '../api/client';
import {
  getAllJourneys,
  searchJourneys as mockSearchJourneys,
  getJourneyById,
  getJourneysByDriverId,
  getBookingsByPassengerId,
  getUserById,
  getVehicleById,
  mockUsers,
} from '../data/mock';

// Journey Service
export const journeyService = {
  // Get all journeys
  async getAllJourneys(): Promise<ApiResponse<Journey[]>> {
    try {
      // Simulate API call delay
      await new Promise((resolve) => setTimeout(resolve, 500));
      return {
        success: true,
        data: getAllJourneys(),
      };
    } catch {
      return {
        success: false,
        error: 'Failed to fetch journeys',
      };
    }
  },

  // Search journeys
  async searchJourneys(params: SearchParams): Promise<ApiResponse<Journey[]>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 300));
      const results = mockSearchJourneys(params.from, params.to, params.date);
      return {
        success: true,
        data: results.filter((j) => j.availableSeats >= params.seats),
      };
    } catch {
      return {
        success: false,
        error: 'Failed to search journeys',
      };
    }
  },

  // Get journey by ID
  async getJourneyById(id: string): Promise<ApiResponse<Journey>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 200));
      const journey = getJourneyById(id);
      if (!journey) {
        return {
          success: false,
          error: 'Journey not found',
        };
      }
      return {
        success: true,
        data: journey,
      };
    } catch {
      return {
        success: false,
        error: 'Failed to fetch journey',
      };
    }
  },

  // Get journeys by driver
  async getJourneysByDriver(driverId: string): Promise<ApiResponse<Journey[]>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 300));
      return {
        success: true,
        data: getJourneysByDriverId(driverId),
      };
    } catch {
      return {
        success: false,
        error: 'Failed to fetch driver journeys',
      };
    }
  },

  // Filter journeys
  filterJourneys(
    journeys: Journey[],
    filters: JourneyFilterOptions
  ): Journey[] {
    return journeys.filter((journey) => {
      if (filters.price) {
        if (
          journey.pricePerSeat < filters.price.min ||
          journey.pricePerSeat > filters.price.max
        ) {
          return false;
        }
      }

      if (filters.departureTime) {
        if (
          journey.departureTime < filters.departureTime.min ||
          journey.departureTime > filters.departureTime.max
        ) {
          return false;
        }
      }

      if (
        filters.availableSeats &&
        journey.availableSeats < filters.availableSeats
      ) {
        return false;
      }

      if (filters.vehicleType && journey.vehicle.vehicleType !== filters.vehicleType) {
        return false;
      }

      if (filters.rating && journey.driver.rating) {
        if (journey.driver.rating < filters.rating) {
          return false;
        }
      }

      return true;
    });
  },

  // Sort journeys
  async sortJourneys(
    journeys: Journey[],
    sortOption: JourneySortOption
  ): Promise<Journey[]> {
    const sorted = [...journeys];
    sorted.sort((a, b) => {
      let aValue: any;
      let bValue: any;

      if (sortOption.field === 'price') {
        aValue = a.pricePerSeat;
        bValue = b.pricePerSeat;
      } else if (sortOption.field === 'departureTime') {
        aValue = a.departureTime;
        bValue = b.departureTime;
      } else if (sortOption.field === 'rating') {
        aValue = a.driver.rating || 0;
        bValue = b.driver.rating || 0;
      }

      if (aValue < bValue) return sortOption.order === 'asc' ? -1 : 1;
      if (aValue > bValue) return sortOption.order === 'asc' ? 1 : -1;
      return 0;
    });

    return sorted;
  },

  // Create journey
  async createJourney(journeyData: any): Promise<ApiResponse<Journey>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 500));
      const driverId = 'user1'; // In real app, get from auth context
      const driver = mockUsers[driverId] as User;
      const newJourney: Journey = {
        id: `journey_${Date.now()}`,
        driverId: driverId,
        driver: driver,
        from: journeyData.from,
        to: journeyData.to,
        date: journeyData.date,
        departureTime: journeyData.departureTime,
        arrivalTime: journeyData.arrivalTime,
        availableSeats: parseInt(journeyData.availableSeats),
        totalSeats: parseInt(journeyData.availableSeats),
        pricePerSeat: parseFloat(journeyData.pricePerSeat),
        vehicle: null as any, // Mock vehicle
        status: JourneyStatus.ACTIVE,
        description: journeyData.description || '',
        stops: [],
        createdAt: new Date(),
      };
      return {
        success: true,
        data: newJourney,
        message: 'Journey created successfully',
      };
    } catch {
      return {
        success: false,
        error: 'Failed to create journey',
      };
    }
  },
};

// Booking Service
export const bookingService = {
  // Get bookings by passenger
  async getBookingsByPassenger(passengerId: string): Promise<ApiResponse<Booking[]>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 300));
      return {
        success: true,
        data: getBookingsByPassengerId(passengerId),
      };
    } catch {
      return {
        success: false,
        error: 'Failed to fetch bookings',
      };
    }
  },

  // Create booking
  async createBooking(journeyId: string, passengerId: string, seatsBooked: number): Promise<ApiResponse<Booking>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 500));

      const journey = getJourneyById(journeyId);
      if (!journey || journey.availableSeats < seatsBooked) {
        return {
          success: false,
          error: 'Not enough seats available',
        };
      }

      const passenger = getUserById(passengerId);
      if (!passenger) {
        return {
          success: false,
          error: 'Passenger not found',
        };
      }

      const totalPrice = journey.pricePerSeat * seatsBooked;

      const newBooking: Booking = {
        id: `booking_${Date.now()}`,
        journeyId,
        passengerId,
        passenger,
        journey,
        seatsBooked,
        totalPrice,
        status: BookingStatus.PENDING,
        bookingReference: `REN${Math.random().toString(36).substr(2, 9).toUpperCase()}`,
        createdAt: new Date(),
      };

      return {
        success: true,
        data: newBooking,
        message: 'Booking created successfully',
      };
    } catch {
      return {
        success: false,
        error: 'Failed to create booking',
      };
    }
  },

  // Cancel booking
  async cancelBooking(_bookingId: string): Promise<ApiResponse<void>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 300));
      return {
        success: true,
        message: 'Booking cancelled successfully',
      };
    } catch {
      return {
        success: false,
        error: 'Failed to cancel booking',
      };
    }
  },
};

// Vehicle Service
export const vehicleService = {
  // Get vehicle by ID
  async getVehicleById(id: string): Promise<ApiResponse<Vehicle>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 200));
      const vehicle = getVehicleById(id);
      if (!vehicle) {
        return {
          success: false,
          error: 'Vehicle not found',
        };
      }
      return {
        success: true,
        data: vehicle,
      };
    } catch {
      return {
        success: false,
        error: 'Failed to fetch vehicle',
      };
    }
  },

  // Create vehicle
  async createVehicle(vehicle: Omit<Vehicle, 'id' | 'createdAt'>): Promise<ApiResponse<Vehicle>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 500));
      const newVehicle: Vehicle = {
        ...vehicle,
        id: `vehicle_${Date.now()}`,
        createdAt: new Date(),
      };
      return {
        success: true,
        data: newVehicle,
        message: 'Vehicle created successfully',
      };
    } catch {
      return {
        success: false,
        error: 'Failed to create vehicle',
      };
    }
  },
};

// User Service
export const userService = {
  // Get user by ID
  async getUserById(id: string): Promise<ApiResponse<User>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 200));
      const user = getUserById(id);
      if (!user) {
        return {
          success: false,
          error: 'User not found',
        };
      }
      return {
        success: true,
        data: user,
      };
    } catch {
      return {
        success: false,
        error: 'Failed to fetch user',
      };
    }
  },

  // Get all drivers
  async getAllDrivers(): Promise<ApiResponse<User[]>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 300));
      const drivers = Object.values(mockUsers).filter((u) => u.role === 'driver');
      return {
        success: true,
        data: drivers,
      };
    } catch {
      return {
        success: false,
        error: 'Failed to fetch drivers',
      };
    }
  },

  // Update user profile
  async updateProfile(userId: string, updateData: Partial<User>): Promise<ApiResponse<User>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 500));
      const user = getUserById(userId);
      if (!user) {
        return {
          success: false,
          error: 'User not found',
        };
      }
      const updatedUser = { ...user, ...updateData };
      return {
        success: true,
        data: updatedUser,
        message: 'Profile updated successfully',
      };
    } catch {
      return {
        success: false,
        error: 'Failed to update profile',
      };
    }
  },
};

interface AuthApiResponse {
  success: boolean;
  token?: string;
  user?: User;
  message?: string;
  error?: string;
}

// Authentication Service
export const authService = {
  // Login with backend API
  async login(email: string, password: string): Promise<ApiResponse<User>> {
    try {
      if (!email || !password) {
        return {
          success: false,
          error: 'Email and password are required',
        };
      }

      const response = await request<AuthApiResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });

      if (response.success && response.user && response.token) {
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem('token', response.token);
          localStorage.setItem('user', JSON.stringify(response.user));
        }
        return {
          success: true,
          data: response.user,
          message: response.message || 'Login successful',
        };
      }

      return {
        success: false,
        error: response.error || 'Login failed',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Login failed. Network or server error.';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Register with backend API
  async register(userData: RegisterData): Promise<ApiResponse<User>> {
    try {
      const response = await request<AuthApiResponse>('/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          name: userData.name,
          email: userData.email,
          password: userData.password,
          phone: userData.phone,
          role: userData.role || 'passenger',
        }),
      });

      if (response.success && response.user && response.token) {
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem('token', response.token);
          localStorage.setItem('user', JSON.stringify(response.user));
        }
        return {
          success: true,
          data: response.user,
          message: response.message || 'Registration successful',
        };
      }

      return {
        success: false,
        error: response.error || 'Registration failed',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Registration failed. Network or server error.';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Logout
  async logout(): Promise<ApiResponse<void>> {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
      }
      return {
        success: true,
        message: 'Logout successful',
      };
    } catch {
      return {
        success: false,
        error: 'Logout failed',
      };
    }
  },

  // Get current user session
  async getCurrentUser(): Promise<ApiResponse<User>> {
    try {
      const token = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
      if (!token) {
        return {
          success: false,
          error: 'No active session token',
        };
      }

      const response = await request<{ success: boolean; user?: User; error?: string }>('/auth/me');
      if (response.success && response.user) {
        localStorage.setItem('user', JSON.stringify(response.user));
        return {
          success: true,
          data: response.user,
        };
      }

      return {
        success: false,
        error: response.error || 'Failed to retrieve session',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Session verification failed';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Reset password request (documented as pending - no email verification infrastructure yet)
  async resetPasswordRequest(_email: string): Promise<ApiResponse<void>> {
    return {
      success: false,
      error: 'Password reset is pending email verification infrastructure setup.',
    };
  },

  // Reset password (documented as pending)
  async resetPassword(_token: string, _newPassword: string): Promise<ApiResponse<void>> {
    return {
      success: false,
      error: 'Password reset is pending email verification infrastructure setup.',
    };
  },
};
