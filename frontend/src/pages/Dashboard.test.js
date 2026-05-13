import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import Dashboard from './Dashboard';
import client from '../api/client';

// 1. MOCK THE API
// We don't want the frontend actually calling the backend during component tests
jest.mock('../api/client', () => ({
  get: jest.fn().mockResolvedValue({ data: [] }),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
}));

// 2. MOCK WINDOW.OPEN
// We want to prove the button works without actually opening a browser tab
const mockWindowOpen = jest.fn();
window.open = mockWindowOpen;

describe('Dashboard Component - Client Operator View', () => {
  beforeEach(() => {
    // Inject a fake client operator into session storage before each test
    sessionStorage.setItem(
      'user',
      JSON.stringify({ email: 'hospital@test.com', role: 'client_operator' })
    );
  });

  afterEach(() => {
    sessionStorage.clear();
    jest.clearAllMocks();
  });

  test('renders the Client Operator Workspace', async () => {
    // Wrap Dashboard in BrowserRouter because it uses the navigate hook
    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

    // Wait for the mock API call to finish
    await waitFor(() => expect(client.get).toHaveBeenCalled());

    // Assert the workspace title exists
    expect(screen.getByText('Client Operator Workspace')).toBeInTheDocument();
  });

  test('triggers the Mac (.dmg) download when the button is clicked', async () => {
    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

    await waitFor(() => expect(client.get).toHaveBeenCalled());

    // Find the exact Mac download button
    const macButton = screen.getByText(' Mac (.dmg)');
    expect(macButton).toBeInTheDocument();

    // Simulate a human clicking the button
    fireEvent.click(macButton);

    // Assert that the code perfectly triggered the correct FastAPI endpoint
    expect(mockWindowOpen).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/download/client/mac',
      '_blank'
    );
  });
});