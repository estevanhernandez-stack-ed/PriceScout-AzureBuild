import { setupServer } from 'msw/node';
import { handlers } from './handlers';

// Create the mock server
export const server = setupServer(...handlers);
