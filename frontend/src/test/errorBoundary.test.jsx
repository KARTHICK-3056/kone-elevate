import { fireEvent, render, screen } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ErrorBoundary } from '../App';

function Broken() {
  throw new Error('boom');
}

function Shell() {
  const { pathname } = useLocation();
  return (
    <>
      <Link to="/fine">Go to a working page</Link>
      <ErrorBoundary resetKey={pathname}>
        <Routes>
          <Route path="/broken" element={<Broken />} />
          <Route path="/fine" element={<p>Working page</p>} />
        </Routes>
      </ErrorBoundary>
    </>
  );
}

describe('ErrorBoundary', () => {
  it('clears a crash when the user navigates to another page', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <MemoryRouter initialEntries={['/broken']}>
        <Shell />
      </MemoryRouter>,
    );
    expect(screen.getByText('This page could not be displayed')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Go to a working page'));
    expect(screen.getByText('Working page')).toBeInTheDocument();
    expect(screen.queryByText('This page could not be displayed')).not.toBeInTheDocument();
    console.error.mockRestore();
  });
});
