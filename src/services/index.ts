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
import { request, ApiError } from '../api/client';
import {
  getUserById,
  mockUsers,
} from '../data/mock';

interface JourneyApiResponse {
  success: boolean;
  journey?: Journey;
  journeys?: Journey[];
  message?: string;
  error?: string;
}

// Journey Service
export const journeyService = {
  // Get all journeys
  async getAllJourneys(): Promise<ApiResponse<Journey[]>> {
    try {
      const response = await request<JourneyApiResponse>('/journeys');
      if (response.success && response.journeys) {
        return {
          success: true,
          data: response.journeys,
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to fetch journeys',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to fetch journeys';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Search journeys
  async searchJourneys(params: SearchParams): Promise<ApiResponse<Journey[]>> {
    try {
      const queryParts: string[] = [];
      if (params.from) queryParts.push(`from=${encodeURIComponent(params.from)}`);
      if (params.to) queryParts.push(`to=${encodeURIComponent(params.to)}`);
      if (params.date) queryParts.push(`date=${encodeURIComponent(params.date)}`);
      if (params.seats) queryParts.push(`seats=${encodeURIComponent(params.seats.toString())}`);

      const queryString = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
      const response = await request<JourneyApiResponse>(`/journeys${queryString}`);
      if (response.success && response.journeys) {
        return {
          success: true,
          data: response.journeys,
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to search journeys',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to search journeys';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Get journey by ID
  async getJourneyById(id: string): Promise<ApiResponse<Journey>> {
    try {
      const response = await request<JourneyApiResponse>(`/journeys/${id}`);
      if (response.success && response.journey) {
        return {
          success: true,
          data: response.journey,
        };
      }
      return {
        success: false,
        error: response.error || 'Journey not found',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to fetch journey';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Get journeys by driver
  async getJourneysByDriver(driverId: string): Promise<ApiResponse<Journey[]>> {
    try {
      const response = await request<JourneyApiResponse>(`/journeys?driverId=${encodeURIComponent(driverId)}&status=all`);
      if (response.success && response.journeys) {
        return {
          success: true,
          data: response.journeys,
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to fetch driver journeys',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to fetch driver journeys';
      return {
        success: false,
        error: message,
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

      if (filters.vehicleType && journey.vehicle && journey.vehicle.vehicleType !== filters.vehicleType) {
        return false;
      }

      if (filters.rating && journey.driver && journey.driver.rating) {
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
        aValue = a.driver?.rating || 0;
        bValue = b.driver?.rating || 0;
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
      const payload = {
        from: journeyData.from,
        to: journeyData.to,
        date: journeyData.date,
        departureTime: journeyData.departureTime,
        arrivalTime: journeyData.arrivalTime || undefined,
        totalSeats: parseInt(journeyData.availableSeats || journeyData.totalSeats || '1', 10),
        pricePerSeat: parseFloat(journeyData.pricePerSeat || '0'),
        vehicleId: journeyData.vehicleId,
        description: journeyData.description || '',
      };

      const response = await request<JourneyApiResponse>('/journeys', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      if (response.success && response.journey) {
        return {
          success: true,
          data: response.journey,
          message: response.message || 'Journey created successfully',
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to create journey',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to create journey';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Update journey
  async updateJourney(id: string, updates: Partial<Journey>): Promise<ApiResponse<Journey>> {
    try {
      const response = await request<JourneyApiResponse>(`/journeys/${id}`, {
        method: 'PUT',
        body: JSON.stringify(updates),
      });
      if (response.success && response.journey) {
        return {
          success: true,
          data: response.journey,
          message: response.message || 'Journey updated successfully',
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to update journey',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to update journey';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Delete journey
  async deleteJourney(id: string): Promise<ApiResponse<void>> {
    try {
      const response = await request<{ success: boolean; message?: string; error?: string }>(`/journeys/${id}`, {
        method: 'DELETE',
      });
      if (response.success) {
        return {
          success: true,
          message: response.message || 'Journey deleted successfully',
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to delete journey',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to delete journey';
      return {
        success: false,
        error: message,
      };
    }
  },
};

interface BookingApiResponse {
  success: boolean;
  booking?: Booking;
  bookings?: Booking[];
  count?: number;
  message?: string;
  error?: string;
}

// Booking Service
export const bookingService = {
  // Get bookings by passenger (or current authenticated user)
  async getBookingsByPassenger(passengerId?: string): Promise<ApiResponse<Booking[]>> {
    try {
      const endpoint = passengerId ? `/bookings?passengerId=${encodeURIComponent(passengerId)}` : '/bookings';
      const response = await request<BookingApiResponse>(endpoint, {
        method: 'GET',
      });
      if (response.success && response.bookings) {
        return {
          success: true,
          data: response.bookings,
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to fetch bookings',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to fetch bookings';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Get single booking by ID or reference
  async getBookingById(id: string): Promise<ApiResponse<Booking>> {
    try {
      const response = await request<BookingApiResponse>(`/bookings/${id}`, {
        method: 'GET',
      });
      if (response.success && response.booking) {
        return {
          success: true,
          data: response.booking,
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to fetch booking',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to fetch booking';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Create booking
  async createBooking(
    journeyId: string,
    passengerId?: string,
    seatsBooked: number = 1,
    pickupLocation?: string,
    dropoffLocation?: string
  ): Promise<ApiResponse<Booking>> {
    try {
      const payload: Record<string, any> = {
        journeyId,
        seatsBooked,
      };
      if (passengerId) {
        payload.passengerId = passengerId;
      }
      if (pickupLocation) {
        payload.pickupLocation = pickupLocation;
      }
      if (dropoffLocation) {
        payload.dropoffLocation = dropoffLocation;
      }

      const response = await request<BookingApiResponse>('/bookings', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      if (response.success && response.booking) {
        return {
          success: true,
          data: response.booking,
          message: response.message || 'Booking created successfully',
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to create booking',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to create booking';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Update booking details or status
  async updateBooking(
    bookingId: string,
    updates: {
      status?: string;
      paymentStatus?: string;
      pickupLocation?: string;
      dropoffLocation?: string;
    }
  ): Promise<ApiResponse<Booking>> {
    try {
      const response = await request<BookingApiResponse>(`/bookings/${bookingId}`, {
        method: 'PATCH',
        body: JSON.stringify(updates),
      });
      if (response.success && response.booking) {
        return {
          success: true,
          data: response.booking,
          message: response.message || 'Booking updated successfully',
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to update booking',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to update booking';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Cancel booking
  async cancelBooking(bookingId: string): Promise<ApiResponse<void>> {
    try {
      const response = await request<BookingApiResponse>(`/bookings/${bookingId}/cancel`, {
        method: 'POST',
      });
      if (response.success) {
        return {
          success: true,
          message: response.message || 'Booking cancelled successfully',
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to cancel booking',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to cancel booking';
      return {
        success: false,
        error: message,
      };
    }
  },
};

interface VehicleApiResponse {
  success: boolean;
  vehicle?: Vehicle;
  vehicles?: Vehicle[];
  message?: string;
  error?: string;
}

// Vehicle Service
export const vehicleService = {
  // Get vehicles for the authenticated driver
  async getVehicles(): Promise<ApiResponse<Vehicle[]>> {
    try {
      const response = await request<VehicleApiResponse>('/vehicles');
      if (response.success && response.vehicles) {
        return {
          success: true,
          data: response.vehicles,
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to fetch vehicles',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to fetch vehicles';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Get vehicle by ID
  async getVehicleById(id: string): Promise<ApiResponse<Vehicle>> {
    try {
      const response = await request<VehicleApiResponse>(`/vehicles/${id}`);
      if (response.success && response.vehicle) {
        return {
          success: true,
          data: response.vehicle,
        };
      }
      return {
        success: false,
        error: response.error || 'Vehicle not found',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to fetch vehicle';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Create vehicle
  async createVehicle(vehicle: Omit<Vehicle, 'id' | 'createdAt'>): Promise<ApiResponse<Vehicle>> {
    try {
      const response = await request<VehicleApiResponse>('/vehicles', {
        method: 'POST',
        body: JSON.stringify(vehicle),
      });
      if (response.success && response.vehicle) {
        return {
          success: true,
          data: response.vehicle,
          message: response.message || 'Vehicle created successfully',
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to create vehicle',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to create vehicle';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Update vehicle
  async updateVehicle(id: string, updates: Partial<Vehicle>): Promise<ApiResponse<Vehicle>> {
    try {
      const response = await request<VehicleApiResponse>(`/vehicles/${id}`, {
        method: 'PUT',
        body: JSON.stringify(updates),
      });
      if (response.success && response.vehicle) {
        return {
          success: true,
          data: response.vehicle,
          message: response.message || 'Vehicle updated successfully',
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to update vehicle',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to update vehicle';
      return {
        success: false,
        error: message,
      };
    }
  },

  // Delete vehicle
  async deleteVehicle(id: string): Promise<ApiResponse<void>> {
    try {
      const response = await request<{ success: boolean; message?: string; error?: string }>(`/vehicles/${id}`, {
        method: 'DELETE',
      });
      if (response.success) {
        return {
          success: true,
          message: response.message || 'Vehicle deleted successfully',
        };
      }
      return {
        success: false,
        error: response.error || 'Failed to delete vehicle',
      };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to delete vehicle';
      return {
        success: false,
        error: message,
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
