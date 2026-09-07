import assert from 'node:assert/strict';
import fs from 'node:fs';

const app = fs.readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
const api = fs.readFileSync(new URL('../src/lib/api.js', import.meta.url), 'utf8');

assert.equal(app.includes('const demoItems'), false, 'real library must not seed demo records');
assert.equal(app.includes("useState(demoItems)"), false, 'real library must start from persisted records only');
assert.match(app, /deleteMurmur/);
assert.match(app, /updateMurmur/);
assert.match(app, /restoreBackup/);
assert.match(app, /exportBackup/);
assert.match(app, /eraseAllMurmurs/);
assert.match(app, /No murmurs yet/);
assert.equal(app.includes('Offline preview'), false, 'offline state must not pretend demo data is user data');

assert.match(app, /editTags/);
assert.match(app, /editPinned/);
assert.match(app, /tags:\s*tagsFromInput\(editTags\)/, 'comma-separated UI tags must be converted to an array before the API call');
assert.equal(app.includes('tags: editTags,'), false, 'raw tag input must never be sent where the backend expects a list');
assert.match(app, /pinned:\s*editPinned/);
assert.match(app, /Pinned/);

assert.match(api, /export async function updateMurmur/);
assert.match(api, /export async function exportBackup/);
assert.match(api, /export async function restoreBackup/);
assert.match(api, /export async function eraseAllMurmurs/);

console.log('frontend release contract: pass');
