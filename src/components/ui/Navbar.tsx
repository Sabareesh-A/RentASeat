import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import './Navbar.css';

interface NavbarProps {
  brand?: string;
  links?: { label: string; href: string }[];
  authLinks?: React.ReactNode;
  onMenuToggle?: (open: boolean) => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  brand = 'RentASeat',
  links,
  authLinks,
  onMenuToggle,
}) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();

  const toggleMobileMenu = () => {
    const newState = !mobileMenuOpen;
    setMobileMenuOpen(newState);
    onMenuToggle?.(newState);
  };

  return (
    <nav className="navbar">
      <div className="navbar-container container">
        {/* Logo/Brand */}
        <Link to="/" className="navbar-brand">
          <span className="navbar-logo">🚗</span>
          <span className="navbar-title">{brand}</span>
        </Link>

        {/* Navigation Links */}
        <div className={`navbar-menu ${mobileMenuOpen ? 'navbar-menu--open' : ''}`}>
          {links && (
            <ul className="navbar-links">
              {links.map((link) => (
                <li key={link.href}>
                  <Link
                    to={link.href}
                    className={`navbar-link ${
                      location.pathname === link.href ? 'navbar-link--active' : ''
                    }`}
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {/* Auth Links */}
          {authLinks && (
            <div className="navbar-auth" onClick={() => setMobileMenuOpen(false)}>
              {authLinks}
            </div>
          )}
        </div>

        {/* Mobile Menu Toggle */}
        <button
          className={`navbar-toggle ${mobileMenuOpen ? 'navbar-toggle--open' : ''}`}
          onClick={toggleMobileMenu}
          aria-label="Toggle navigation menu"
        >
          <span></span>
          <span></span>
          <span></span>
        </button>
      </div>
    </nav>
  );
};

interface FooterProps {
  sections?: {
    title: string;
    links: { label: string; href: string }[];
  }[];
  socialLinks?: { icon: string; url: string }[];
  copyright?: string;
}

export const Footer: React.FC<FooterProps> = ({
  sections,
  socialLinks,
  copyright = `© ${new Date().getFullYear()} RentASeat. All rights reserved.`,
}) => {
  return (
    <footer className="footer">
      <div className="footer-container container">
        {sections && (
          <div className="footer-sections">
            {sections.map((section) => (
              <div key={section.title} className="footer-section">
                <h3 className="footer-section-title">{section.title}</h3>
                <ul className="footer-links">
                  {section.links.map((link) => (
                    <li key={link.href}>
                      <a href={link.href}>{link.label}</a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {socialLinks && (
          <div className="footer-social">
            {socialLinks.map((link) => (
              <a key={link.url} href={link.url} className="footer-social-link">
                {link.icon}
              </a>
            ))}
          </div>
        )}
      </div>

      <div className="footer-bottom">
        <p className="footer-copyright">{copyright}</p>
      </div>
    </footer>
  );
};
