const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:5000';
const TOKEN_STORAGE_KEY = 'ring_rag_api_token';

export function getApiToken() {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY) || '';
  } catch (error) {
    return '';
  }
}

export function setApiToken(token) {
  const trimmed = (token || '').trim();
  try {
    if (trimmed) {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, trimmed);
    } else {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch (error) {
    // Ignore storage failures; the request will be rejected without a token.
  }
}

export async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getApiToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
}

export async function readApiPayload(response) {
  try {
    return await response.json();
  } catch (error) {
    return {};
  }
}
