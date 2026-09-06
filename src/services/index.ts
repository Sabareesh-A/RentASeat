import type {
  Journey,
  Booking,
  Vehicle,
  User,
  SearchParams,
  JourneyFilterOptions,
  JourneySortOption,
  ApiResponse,
} from '../types';
import { BookingStatus, JourneyStatus } from '../types';
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
    } catch (error) {
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
    } catch (error) {
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
    } catch (error) {
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
    } catch (error) {
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
    } catch (error) {
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
    } catch (error) {
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
    } catch (error) {
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
    } catch (error) {
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
    } catch (error) {
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
    } catch (error) {
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
    } catch (error) {
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
    } catch (error) {
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
    } catch (error) {
      return {
        success: false,
        error: 'Failed to update profile',
      };
    }
  },
};

// Authentication Service
export const authService = {
  // Login
  async login(email: string, password: string): Promise<ApiResponse<User>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 800));

      // Demo: Accept any email/password combination for testing
      if (!email || !password) {
        return {
          success: false,
          error: 'Email and password are required',
        };
      }

      // For demo purposes, return a default user
      const user = Object.values(mockUsers)[0];

      return {
        success: true,
        data: user,
        message: 'Login successful',
      };
    } catch (error) {
      return {
        success: false,
        error: 'Login failed',
      };
    }
  },

  // Register
  async register(userData: any): Promise<ApiResponse<User>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 1000));

      const newUser: User = {
        id: `user_${Date.now()}`,
        ...userData,
        createdAt: new Date(),
      };

      return {
        success: true,
        data: newUser,
        message: 'Registration successful',
      };
    } catch (error) {
      return {
        success: false,
        error: 'Registration failed',
      };
    }
  },

  // Logout
  async logout(): Promise<ApiResponse<void>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 300));
      return {
        success: true,
        message: 'Logout successful',
      };
    } catch (error) {
      return {
        success: false,
        error: 'Logout failed',
      };
    }
  },

  // Reset password request
  async resetPasswordRequest(_email: string): Promise<ApiResponse<void>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 500));
      return {
        success: true,
        message: 'Password reset email sent',
      };
    } catch (error) {
      return {
        success: false,
        error: 'Failed to send reset email',
      };
    }
  },

  // Reset password
  async resetPassword(_token: string, _newPassword: string): Promise<ApiResponse<void>> {
    try {
      await new Promise((resolve) => setTimeout(resolve, 500));
      return {
        success: true,
        message: 'Password reset successful',
      };
    } catch (error) {
      return {
        success: false,
        error: 'Failed to reset password',
      };
    }
  },
};
