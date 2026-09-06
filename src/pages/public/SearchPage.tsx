import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../../components/ui';
import { Button } from '../../components/ui/Button';
import { Input, Select } from '../../components/ui/Input';
import { JourneyCard } from '../../components/journey/JourneyCard';
import { LoadingState, EmptyState, ErrorState } from '../../components/ui/StateComponents';
import { journeyService } from '../../services';
import type { Journey, SearchParams, JourneyFilterOptions } from '../../types';
import './SearchPage.css';

const SearchPage: React.FC = () => {
  const searchParams = new URLSearchParams(window.location.search);
  const [filteredJourneys, setFilteredJourneys] = useState<Journey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchData, setSearchData] = useState<SearchParams>({
    from: searchParams.get('from') || '',
    to: searchParams.get('to') || '',
    date: searchParams.get('date') || '',
    seats: parseInt(searchParams.get('seats') || '1'),
  });

  const [_filters, _setFilters] = useState<JourneyFilterOptions>({});
  const [sortBy, setSortBy] = useState<'price' | 'time' | 'rating'>('price');

  useEffect(() => {
    loadJourneys();
  }, [searchData]);

  const loadJourneys = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await journeyService.searchJourneys(searchData);
      if (response.success && response.data) {
        const journeyData = response.data;
        let results = applySorting(journeyData);
        setFilteredJourneys(results);
      } else {
        setError(response.error || 'Failed to load journeys');
      }
    } catch (err) {
      setError('An unexpected error occurred');
    } finally {
      setLoading(false);
    }
  };

  const applySorting = (data: Journey[]) => {
    const sorted = [...data];
    if (sortBy === 'price') {
      sorted.sort((a, b) => a.pricePerSeat - b.pricePerSeat);
    } else if (sortBy === 'time') {
      sorted.sort((a, b) => a.departureTime.localeCompare(b.departureTime));
    } else if (sortBy === 'rating') {
      sorted.sort((a, b) => (b.driver.rating || 0) - (a.driver.rating || 0));
    }
    return sorted;
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const params = new URLSearchParams({
      from: searchData.from,
      to: searchData.to,
      date: searchData.date,
      seats: searchData.seats.toString(),
    });
    window.location.href = `/search?${params.toString()}`;
  };

  return (
    <div className="search-page">
      <Navbar
        links={[
          { label: 'Home', href: '/' },
          { label: 'About', href: '#' },
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

      <div className="search-container container">
        {/* Search Panel */}
        <form className="search-panel" onSubmit={handleSearch}>
          <h2>Search Rides</h2>
          <div className="search-grid">
            <Input
              label="From"
              placeholder="Departure city"
              value={searchData.from}
              onChange={(e) => setSearchData({ ...searchData, from: e.target.value })}
              required
            />
            <Input
              label="To"
              placeholder="Destination city"
              value={searchData.to}
              onChange={(e) => setSearchData({ ...searchData, to: e.target.value })}
              required
            />
            <Input
              label="Date"
              type="date"
              value={searchData.date}
              onChange={(e) => setSearchData({ ...searchData, date: e.target.value })}
              required
            />
            <Select
              label="Seats"
              options={[
                { value: '1', label: '1 Seat' },
                { value: '2', label: '2 Seats' },
                { value: '3', label: '3 Seats' },
                { value: '4', label: '4 Seats' },
              ]}
              value={searchData.seats.toString()}
              onChange={(e) => setSearchData({ ...searchData, seats: parseInt(e.target.value) })}
            />
          </div>
          <Button type="submit" fullWidth>
            Search
          </Button>
        </form>

        {/* Filter Panel */}
        <div className="filter-panel">
          <h3>Filters</h3>
          <div className="filter-group">
            <label>Sort By</label>
            <Select
              options={[
                { value: 'price', label: 'Price (Low to High)' },
                { value: 'time', label: 'Departure Time' },
                { value: 'rating', label: 'Driver Rating' },
              ]}
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
            />
          </div>
        </div>

        {/* Results Panel */}
        <div className="results-panel">
          <div className="results-header">
            <h2>
              Available Rides
              {filteredJourneys.length > 0 && ` (${filteredJourneys.length})`}
            </h2>
          </div>

          {loading ? (
            <LoadingState message="Finding rides for you..." />
          ) : error ? (
            <ErrorState message={error} retry={loadJourneys} />
          ) : filteredJourneys.length === 0 ? (
            <EmptyState
              icon="🚗"
              title="No Rides Found"
              message="Try adjusting your search criteria"
              action={
                <Link to="/">
                  <Button variant="primary">Back to Home</Button>
                </Link>
              }
            />
          ) : (
            <div className="results-list">
              {filteredJourneys.map((journey) => (
                <JourneyCard
                  key={journey.id}
                  journey={journey}
                  onViewDetails={() => {
                    window.location.href = `/journey/${journey.id}`;
                  }}
                  onBook={() => {
                    // Handle booking
                    alert('Booking feature coming soon!');
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SearchPage;
