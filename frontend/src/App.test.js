import { render } from '@testing-library/react';
import App from './App';

test("renders the main app without crashing", () => {
  // We just render App directly, because App.js already contains the BrowserRouter
  render(<App />);
});