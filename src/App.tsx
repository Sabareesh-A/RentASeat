import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './styles/globals.css';

// Pages
import HomePage from './pages/public/HomePage';
import SearchPage from './pages/public/SearchPage';
import JourneyDetailsPage from './pages/public/JourneyDetailsPage';
import LoginPage from './pages/public/LoginPage';
import RegisterPage from './pages/public/RegisterPage';
import ForgotPasswordPage from './pages/public/ForgotPasswordPage';
import PassengerDashboard from './pages/passenger/Dashboard';
import PassengerBookings from './pages/passenger/Bookings';
import PassengerProfile from './pages/passenger/Profile';
import DriverDashboard from './pages/driver/Dashboard';
import DriverJourneys from './pages/driver/Journeys';
import CreateJourney from './pages/driver/CreateJourney';
import AdminDashboard from './pages/admin/Dashboard';
import NotFoundPage from './pages/public/NotFound';

function App() {
  return (
    <Router>
      <Routes>
        {/* Public Routes */}
        <Route path="/" element={<HomePage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/journey/:id" element={<JourneyDetailsPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />

        {/* Passenger Routes */}
        <Route path="/passenger/dashboard" element={<PassengerDashboard />} />
        <Route path="/passenger/bookings" element={<PassengerBookings />} />
        <Route path="/passenger/profile" element={<PassengerProfile />} />

        {/* Driver Routes */}
        <Route path="/driver/dashboard" element={<DriverDashboard />} />
        <Route path="/driver/journeys" element={<DriverJourneys />} />
        <Route path="/driver/journeys/create" element={<CreateJourney />} />

        {/* Admin Routes */}
        <Route path="/admin/dashboard" element={<AdminDashboard />} />

        {/* 404 */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Router>
  );
}

export default App;
