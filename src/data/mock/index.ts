import type {
  User,
  Journey,
  Vehicle,
  Booking,
} from '../../types';
import { UserRole, VehicleType, BookingStatus, JourneyStatus } from '../../types';

// Mock Users
export const mockUsers: Record<string, User> = {
  user1: {
    id: 'user1',
    name: 'John Driver',
    email: 'john.driver@example.com',
    phone: '+1-555-0101',
    role: UserRole.DRIVER,
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=John',
    rating: 4.8,
    reviews: 127,
    createdAt: new Date('2023-01-15'),
  },
  user2: {
    id: 'user2',
    name: 'Sarah Passenger',
    email: 'sarah.p@example.com',
    phone: '+1-555-0102',
    role: UserRole.PASSENGER,
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Sarah',
    rating: 4.9,
    reviews: 45,
    createdAt: new Date('2023-03-20'),
  },
  user3: {
    id: 'user3',
    name: 'Mike Driver',
    email: 'mike.driver@example.com',
    phone: '+1-555-0103',
    role: UserRole.DRIVER,
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Mike',
    rating: 4.6,
    reviews: 89,
    createdAt: new Date('2023-02-10'),
  },
  user4: {
    id: 'user4',
    name: 'Emma Admin',
    email: 'emma.admin@example.com',
    phone: '+1-555-0104',
    role: UserRole.ADMIN,
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Emma',
    createdAt: new Date('2022-12-01'),
  },
  user5: {
    id: 'user5',
    name: 'Alex Passenger',
    email: 'alex.p@example.com',
    phone: '+1-555-0105',
    role: UserRole.PASSENGER,
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Alex',
    rating: 4.7,
    reviews: 23,
    createdAt: new Date('2023-04-05'),
  },
  user6: {
    id: 'user6',
    name: 'Lisa Driver',
    email: 'lisa.driver@example.com',
    phone: '+1-555-0106',
    role: UserRole.DRIVER,
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Lisa',
    rating: 4.9,
    reviews: 156,
    createdAt: new Date('2022-11-30'),
  },
};

// Mock Vehicles
export const mockVehicles: Record<string, Vehicle> = {
  vehicle1: {
    id: 'vehicle1',
    driverId: 'user1',
    registrationNumber: 'ABC123',
    vehicleType: VehicleType.SEDAN,
    model: '2022 Toyota Camry',
    colour: 'Silver',
    seatingCapacity: 4,
    image: 'https://images.unsplash.com/photo-1552519507-da3effff991c?w=400',
    createdAt: new Date('2023-01-15'),
  },
  vehicle2: {
    id: 'vehicle2',
    driverId: 'user3',
    registrationNumber: 'XYZ789',
    vehicleType: VehicleType.SUV,
    model: '2023 Honda CR-V',
    colour: 'Black',
    seatingCapacity: 5,
    image: 'https://images.unsplash.com/photo-1606611013016-969c19d4a42f?w=400',
    createdAt: new Date('2023-02-10'),
  },
  vehicle3: {
    id: 'vehicle3',
    driverId: 'user6',
    registrationNumber: 'DEF456',
    vehicleType: VehicleType.MINIVAN,
    model: '2022 Chrysler Pacifica',
    colour: 'White',
    seatingCapacity: 7,
    image: 'https://images.unsplash.com/photo-1605559424843-9e4c3ff86981?w=400',
    createdAt: new Date('2022-11-30'),
  },
};

// Mock Journeys
export const mockJourneys: Record<string, Journey> = {
  journey1: {
    id: 'journey1',
    driverId: 'user1',
    driver: mockUsers.user1,
    from: 'San Francisco, CA',
    to: 'Los Angeles, CA',
    date: new Date(Date.now() + 86400000 * 2).toISOString().split('T')[0],
    departureTime: '09:00',
    arrivalTime: '13:30',
    availableSeats: 2,
    totalSeats: 4,
    pricePerSeat: 45,
    vehicle: mockVehicles.vehicle1,
    status: JourneyStatus.ACTIVE,
    description: 'Comfortable ride with air conditioning and music system',
    stops: ['San Jose'],
    createdAt: new Date(),
  },
  journey2: {
    id: 'journey2',
    driverId: 'user3',
    driver: mockUsers.user3,
    from: 'New York, NY',
    to: 'Boston, MA',
    date: new Date(Date.now() + 86400000 * 1).toISOString().split('T')[0],
    departureTime: '07:30',
    arrivalTime: '12:00',
    availableSeats: 3,
    totalSeats: 5,
    pricePerSeat: 35,
    vehicle: mockVehicles.vehicle2,
    status: JourneyStatus.ACTIVE,
    description: 'Highway travel, pet-friendly',
    createdAt: new Date(),
  },
  journey3: {
    id: 'journey3',
    driverId: 'user6',
    driver: mockUsers.user6,
    from: 'Seattle, WA',
    to: 'Portland, OR',
    date: new Date(Date.now() + 86400000 * 3).toISOString().split('T')[0],
    departureTime: '10:00',
    arrivalTime: '13:00',
    availableSeats: 5,
    totalSeats: 7,
    pricePerSeat: 28,
    vehicle: mockVehicles.vehicle3,
    status: JourneyStatus.ACTIVE,
    description: 'Direct route, spacious vehicle, wifi available',
    stops: ['Salem'],
    createdAt: new Date(),
  },
  journey4: {
    id: 'journey4',
    driverId: 'user1',
    driver: mockUsers.user1,
    from: 'San Francisco, CA',
    to: 'Oakland, CA',
    date: new Date(Date.now() + 86400000 * 4).toISOString().split('T')[0],
    departureTime: '14:00',
    arrivalTime: '14:45',
    availableSeats: 1,
    totalSeats: 4,
    pricePerSeat: 15,
    vehicle: mockVehicles.vehicle1,
    status: JourneyStatus.ACTIVE,
    description: 'Quick commute',
    createdAt: new Date(),
  },
  journey5: {
    id: 'journey5',
    driverId: 'user3',
    driver: mockUsers.user3,
    from: 'Chicago, IL',
    to: 'Milwaukee, WI',
    date: new Date(Date.now() + 86400000 * 5).toISOString().split('T')[0],
    departureTime: '08:00',
    arrivalTime: '10:30',
    availableSeats: 4,
    totalSeats: 5,
    pricePerSeat: 22,
    vehicle: mockVehicles.vehicle2,
    status: JourneyStatus.ACTIVE,
    description: 'Scenic route along Lake Michigan',
    stops: ['Evanston'],
    createdAt: new Date(),
  },
  journey6: {
    id: 'journey6',
    driverId: 'user6',
    driver: mockUsers.user6,
    from: 'Denver, CO',
    to: 'Boulder, CO',
    date: new Date(Date.now() + 86400000 * 2).toISOString().split('T')[0],
    departureTime: '11:00',
    arrivalTime: '12:15',
    availableSeats: 2,
    totalSeats: 7,
    pricePerSeat: 18,
    vehicle: mockVehicles.vehicle3,
    status: JourneyStatus.ACTIVE,
    description: 'Mountain scenery',
    createdAt: new Date(),
  },
};

// Mock Bookings
export const mockBookings: Record<string, Booking> = {
  booking1: {
    id: 'booking1',
    journeyId: 'journey1',
    passengerId: 'user2',
    passenger: mockUsers.user2,
    journey: mockJourneys.journey1,
    seatsBooked: 2,
    totalPrice: 90,
    status: BookingStatus.CONFIRMED,
    bookingReference: 'REN123456789',
    createdAt: new Date(Date.now() - 86400000 * 2),
    pickupLocation: 'Market Street, San Francisco',
    dropoffLocation: 'Hollywood Walk of Fame, Los Angeles',
  },
  booking2: {
    id: 'booking2',
    journeyId: 'journey2',
    passengerId: 'user5',
    passenger: mockUsers.user5,
    journey: mockJourneys.journey2,
    seatsBooked: 1,
    totalPrice: 35,
    status: BookingStatus.CONFIRMED,
    bookingReference: 'REN987654321',
    createdAt: new Date(Date.now() - 86400000 * 1),
    pickupLocation: 'Times Square, New York',
    dropoffLocation: 'Boston Common, Boston',
  },
};

// Function to get all journeys
export const getAllJourneys = (): Journey[] => {
  return Object.values(mockJourneys);
};

// Function to search journeys
export const searchJourneys = (
  from: string,
  to: string,
  date: string
): Journey[] => {
  return getAllJourneys().filter(
    (journey) =>
      journey.from.toLowerCase().includes(from.toLowerCase()) &&
      journey.to.toLowerCase().includes(to.toLowerCase()) &&
      journey.date === date
  );
};

// Function to get journey by ID
export const getJourneyById = (id: string): Journey | undefined => {
  return mockJourneys[id];
};

// Function to get journeys by driver ID
export const getJourneysByDriverId = (driverId: string): Journey[] => {
  return getAllJourneys().filter((journey) => journey.driverId === driverId);
};

// Function to get bookings by passenger ID
export const getBookingsByPassengerId = (passengerId: string): Booking[] => {
  return Object.values(mockBookings).filter(
    (booking) => booking.passengerId === passengerId
  );
};

// Function to get user by ID
export const getUserById = (id: string): User | undefined => {
  return mockUsers[id];
};

// Function to get vehicle by ID
export const getVehicleById = (id: string): Vehicle | undefined => {
  return mockVehicles[id];
};
