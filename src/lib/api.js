const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function parse(response) {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || 'Murmur could not complete that request.');
  }
  if (response.status === 204) return null;
  return response.json();
}

export async function fetchMurmurs() {
  return parse(await fetch(`${API_URL}/api/murmurs`));
}

export async function createTextMurmur(transcript) {
  return parse(await fetch(`${API_URL}/api/murmurs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript }),
  }));
}

export async function transcribeRecording(blob) {
  const body = new FormData();
  body.append('audio', blob, `murmur-${Date.now()}.webm`);
  return parse(await fetch(`${API_URL}/api/transcribe`, { method: 'POST', body }));
}

export async function fetchSkills() {
  return parse(await fetch(`${API_URL}/api/skills`));
}

export async function processMurmur(transcript, skill = null) {
  return parse(await fetch(`${API_URL}/api/process`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript, skill }),
  }));
}

export async function deleteMurmur(id) {
  return parse(await fetch(`${API_URL}/api/murmurs/${id}`, { method: 'DELETE' }));
}

export async function fetchStats() {
  return parse(await fetch(`${API_URL}/api/stats`));
}

export function exportUrl() {
  return `${API_URL}/api/export.csv`;
}

export async function checkHealth() {
  return parse(await fetch(`${API_URL}/health`));
}
