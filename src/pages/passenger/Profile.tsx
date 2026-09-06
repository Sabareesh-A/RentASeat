import React, { useState, useEffect } from 'react';
import { Navbar } from '../../components/ui';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card } from '../../components/ui/Card';
import { userService } from '../../services';

const PassengerProfile: React.FC = () => {
  const [user, setUser] = useState<any>(null);
  const [editMode, setEditMode] = useState(false);
  const [formData, setFormData] = useState<any>({});

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = () => {
    const userData = JSON.parse(localStorage.getItem('user') || '{}');
    setUser(userData);
    setFormData(userData);
  };

  const handleSave = async () => {
    try {
      const response = await userService.updateProfile(user.id, formData);
      if (response.success) {
        setUser(response.data);
        localStorage.setItem('user', JSON.stringify(response.data));
        setEditMode(false);
      }
    } catch (err) {
      console.error('Failed to update profile');
    }
  };

  return (
    <div>
      <Navbar />
      <div className="container" style={{ padding: '2rem', maxWidth: '600px' }}>
        <h1>My Profile</h1>

        {user && (
          <Card elevated style={{ marginTop: '2rem' }}>
            <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
              <img
                src={user.avatar}
                alt={user.name}
                style={{
                  width: '100px',
                  height: '100px',
                  borderRadius: '50%',
                  marginBottom: '1rem',
                }}
              />
              <h2 style={{ margin: 0 }}>{user.name}</h2>
              <p style={{ color: '#6b7280', margin: '0.5rem 0 0 0' }}>{user.role}</p>
            </div>

            {editMode ? (
              <form style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <Input
                  label="Name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
                <Input
                  label="Email"
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                />
                <Input
                  label="Phone"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                />

                <div style={{ display: 'flex', gap: '1rem' }}>
                  <Button onClick={handleSave} variant="primary" fullWidth>
                    Save Changes
                  </Button>
                  <Button onClick={() => setEditMode(false)} variant="secondary" fullWidth>
                    Cancel
                  </Button>
                </div>
              </form>
            ) : (
              <>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div>
                    <label style={{ fontWeight: 'bold', color: '#6b7280' }}>Email</label>
                    <p>{user.email}</p>
                  </div>
                  <div>
                    <label style={{ fontWeight: 'bold', color: '#6b7280' }}>Phone</label>
                    <p>{user.phone}</p>
                  </div>
                  {user.rating && (
                    <div>
                      <label style={{ fontWeight: 'bold', color: '#6b7280' }}>Rating</label>
                      <p>⭐ {user.rating} ({user.reviews} reviews)</p>
                    </div>
                  )}
                </div>

                <Button onClick={() => setEditMode(true)} variant="primary" fullWidth style={{ marginTop: '1rem' }}>
                  Edit Profile
                </Button>
              </>
            )}
          </Card>
        )}
      </div>
    </div>
  );
};

export default PassengerProfile;
