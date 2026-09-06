import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Navbar, Footer } from '../../components/ui';
import { Button } from '../../components/ui/Button';
import { Input, Select } from '../../components/ui/Input';
import './HomePage.css';

const HomePage: React.FC = () => {
  const [searchData, setSearchData] = useState({
    from: '',
    to: '',
    date: '',
    seats: '1',
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    // Navigate to search page
    window.location.href = `/search?from=${searchData.from}&to=${searchData.to}&date=${searchData.date}&seats=${searchData.seats}`;
  };

  return (
    <div className="home-page">
      <Navbar
        links={[
          { label: 'Search Rides', href: '/search' },
          { label: 'How it Works', href: '#how-it-works' },
          { label: 'Safety', href: '#safety' },
        ]}
        authLinks={
          <div style={{ display: 'flex', gap: '1rem' }}>
            <Link to="/login">
              <Button variant="ghost" size="sm">
                Login
              </Button>
            </Link>
            <Link to="/register">
              <Button variant="primary" size="sm">
                Sign Up
              </Button>
            </Link>
          </div>
        }
      />

      {/* Hero Section */}
      <section className="hero">
        <div className="container">
          <div className="hero-content">
            <h1>Share Your Journey</h1>
            <p>Find rides, save money, meet new people</p>

            {/* Search Form */}
            <form className="search-form" onSubmit={handleSearch}>
              <Input
                placeholder="From"
                value={searchData.from}
                onChange={(e) => setSearchData({ ...searchData, from: e.target.value })}
                required
              />
              <Input
                placeholder="To"
                value={searchData.to}
                onChange={(e) => setSearchData({ ...searchData, to: e.target.value })}
                required
              />
              <Input
                type="date"
                value={searchData.date}
                onChange={(e) => setSearchData({ ...searchData, date: e.target.value })}
                required
              />
              <Select
                options={[
                  { value: '1', label: '1 Seat' },
                  { value: '2', label: '2 Seats' },
                  { value: '3', label: '3 Seats' },
                  { value: '4', label: '4 Seats' },
                ]}
                value={searchData.seats}
                onChange={(e) => setSearchData({ ...searchData, seats: e.target.value })}
              />
              <Button type="submit" fullWidth>
                Search Rides
              </Button>
            </form>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="how-it-works" id="how-it-works">
        <div className="container">
          <h2>How RentASeat Works</h2>
          <div className="steps">
            <div className="step">
              <div className="step-icon">🔍</div>
              <h3>Search</h3>
              <p>Find rides that match your route and schedule</p>
            </div>
            <div className="step">
              <div className="step-icon">📍</div>
              <h3>Book</h3>
              <p>Reserve your seats with just a few clicks</p>
            </div>
            <div className="step">
              <div className="step-icon">🚗</div>
              <h3>Ride</h3>
              <p>Meet your driver and enjoy a comfortable journey</p>
            </div>
            <div className="step">
              <div className="step-icon">⭐</div>
              <h3>Rate</h3>
              <p>Share your experience and help others</p>
            </div>
          </div>
        </div>
      </section>

      {/* Benefits */}
      <section className="benefits">
        <div className="container">
          <h2>Why Choose RentASeat?</h2>
          <div className="benefits-grid">
            <div className="benefit-card">
              <h3>💰 Save Money</h3>
              <p>Share costs and travel affordably</p>
            </div>
            <div className="benefit-card">
              <h3>🌍 Sustainable</h3>
              <p>Reduce carbon footprint by carpooling</p>
            </div>
            <div className="benefit-card">
              <h3>👥 Community</h3>
              <p>Meet new people and make friends</p>
            </div>
            <div className="benefit-card">
              <h3>🔒 Safe & Secure</h3>
              <p>Verified drivers and passengers</p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Sections */}
      <section className="cta-section passenger-cta">
        <div className="container">
          <h2>Ready to Save on Your Next Trip?</h2>
          <p>Join thousands of passengers booking affordable rides</p>
          <Link to="/register">
            <Button size="lg" variant="primary">
              Book a Ride
            </Button>
          </Link>
        </div>
      </section>

      <section className="cta-section driver-cta">
        <div className="container">
          <h2>Have an Empty Seat?</h2>
          <p>Earn money by sharing your ride with passengers going the same way</p>
          <Link to="/register">
            <Button size="lg" variant="primary">
              Start Earning
            </Button>
          </Link>
        </div>
      </section>

      {/* Safety Section */}
      <section className="safety" id="safety">
        <div className="container">
          <h2>Your Safety Comes First</h2>
          <div className="safety-features">
            <div className="safety-feature">
              <h3>✅ Verified Profiles</h3>
              <p>All drivers and passengers must verify their identity</p>
            </div>
            <div className="safety-feature">
              <h3>📱 In-App Communication</h3>
              <p>Keep all conversations within the app for safety</p>
            </div>
            <div className="safety-feature">
              <h3>⭐ Ratings & Reviews</h3>
              <p>See ratings from other users before booking</p>
            </div>
            <div className="safety-feature">
              <h3>📞 24/7 Support</h3>
              <p>Our support team is always ready to help</p>
            </div>
          </div>
        </div>
      </section>

      <Footer
        sections={[
          {
            title: 'Company',
            links: [
              { label: 'About Us', href: '#' },
              { label: 'Blog', href: '#' },
              { label: 'Careers', href: '#' },
            ],
          },
          {
            title: 'Support',
            links: [
              { label: 'Help Center', href: '#' },
              { label: 'Contact Us', href: '#' },
              { label: 'Safety', href: '#' },
            ],
          },
          {
            title: 'Legal',
            links: [
              { label: 'Privacy Policy', href: '#' },
              { label: 'Terms of Service', href: '#' },
              { label: 'Accessibility', href: '#' },
            ],
          },
        ]}
        socialLinks={[
          { icon: 'f', url: '#' },
          { icon: 't', url: '#' },
          { icon: 'i', url: '#' },
        ]}
      />
    </div>
  );
};

export default HomePage;
