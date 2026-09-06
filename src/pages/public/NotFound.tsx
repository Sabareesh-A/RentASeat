import React from 'react';
import { Link } from 'react-router-dom';
import { Navbar, Footer } from '../../components/ui';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/StateComponents';

const NotFoundPage: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Navbar />
      <div style={{ flex: 1, paddingTop: '5rem' }}>
        <EmptyState
          icon="😕"
          title="Page Not Found"
          message="The page you're looking for doesn't exist or has been moved."
          action={
            <Link to="/">
              <Button variant="primary">Go Back Home</Button>
            </Link>
          }
        />
      </div>
      <Footer />
    </div>
  );
};

export default NotFoundPage;
