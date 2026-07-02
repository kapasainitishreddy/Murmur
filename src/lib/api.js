const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function parse(response) {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || 'Murmur could not complete that request.');
  }
  if (response.status === 204) return null;
  return response.json();
}

export async function fetchMurmurs({ space, query, tag } = {}) {
  const params = new URLSearchParams();
  if (space && space !== 'All murmurs') params.set('space', space);
  if (query) params.set('query', query);
  if (tag) params.set('tag', tag);
  const suffix = params.toString() ? `?${params}` : '';
  return parse(await fetch(`${API_URL}/api/murmurs${suffix}`));
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

export async function voiceSearch(blob) {
  const body = new FormData();
  body.append('audio', blob, `search-${Date.now()}.webm`);
  return parse(await fetch(`${API_URL}/api/search/voice`, { method: 'POST', body }));
}

export async function semanticSearch(q) {
  return parse(await fetch(`${API_URL}/api/search?q=${encodeURIComponent(q)}`));
}

export async function fetchRelated(id) {
  return parse(await fetch(`${API_URL}/api/murmurs/${id}/related`));
}

export async function fetchTasks() {
  return parse(await fetch(`${API_URL}/api/tasks`));
}

export async function fetchTimeline() {
  return parse(await fetch(`${API_URL}/api/timeline`));
}

export async function fetchTags() {
  return parse(await fetch(`${API_URL}/api/tags`));
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

export async function shareMurmur(id, target) {
  return parse(await fetch(`${API_URL}/api/murmurs/${id}/share`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target }),
  }));
}

export async function fetchStats() {
  return parse(await fetch(`${API_URL}/api/stats`));
}

export async function fetchIntegrations() {
  return parse(await fetch(`${API_URL}/api/integrations`));
}

export async function fetchDigest(days = 7) {
  return parse(await fetch(`${API_URL}/api/digest?days=${days}`));
}

export async function sendDigest(days = 7) {
  return parse(await fetch(`${API_URL}/api/digest/send?days=${days}`, { method: 'POST' }));
}

export function exportUrl(format = 'csv') {
  return `${API_URL}/api/export.${format}`;
}

export function calendarUrl() {
  return `${API_URL}/api/calendar.ics`;
}

export async function checkHealth() {
  return parse(await fetch(`${API_URL}/health`));
}
