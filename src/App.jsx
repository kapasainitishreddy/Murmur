import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Bell, BookOpen, BriefcaseBusiness, Bug, CalendarClock, Check, ChevronRight, CircleUserRound, Clock, Download, FileText, Hash, Home, LayoutGrid, ListTodo, LoaderCircle, Mic, Moon, MoreHorizontal, PawPrint, Search, Send, Settings, Share2, ShieldCheck, Smile, Sparkles, Square, Sun, Trash2, Waves, Wifi, WifiOff, X } from 'lucide-react';
import { calendarUrl, checkHealth, createTextMurmur, deleteMurmur, exportUrl, fetchDigest, fetchIntegrations, fetchMurmurs, fetchRelated, fetchTasks, fetchTimeline, semanticSearch, sendDigest, shareMurmur, transcribeRecording, voiceSearch } from './lib/api';

const demoItems = [
  { id: 'demo-1', title: 'Passport is in the black suitcase', transcript: 'Second inner pocket, underneath the blue folder.', summary: 'Passport is in the black suitcase, second inner pocket.', space: 'Memory', source: 'text', tags: ['passport', 'suitcase', 'folder'], sentiment: 'neutral', created_at: new Date().toISOString() },
  { id: 'demo-2', title: 'Checkout freezes after coupon', transcript: 'Payment button stops responding after applying a discount code.', summary: 'Payment button stops responding after a coupon is applied.', space: 'Bug report', source: 'voice', tags: ['payment', 'coupon', 'checkout'], sentiment: 'negative', created_at: new Date(Date.now() - 86400000).toISOString() },
  { id: 'demo-3', title: 'Contractor scope update', transcript: 'Replace damaged kitchen tiles and finish by Friday.', summary: 'Replace damaged kitchen tiles by Friday.', space: 'Records', source: 'voice', tags: ['contractor', 'kitchen', 'tiles'], sentiment: 'neutral', created_at: new Date(Date.now() - 172800000).toISOString() },
];

const spaces = [
  { name: 'Memory', icon: BookOpen },
  { name: 'Work', icon: BriefcaseBusiness },
  { name: 'Records', icon: FileText },
  { name: 'Care', icon: PawPrint },
  { name: 'Bug report', label: 'Bugs', icon: Bug },
];

function typeIcon(space) {
  if (space === 'Bug report') return <Bug size={18} />;
  if (space === 'Records') return <FileText size={18} />;
  if (space === 'Care') return <PawPrint size={18} />;
  if (space === 'Work') return <BriefcaseBusiness size={18} />;
  return <BookOpen size={18} />;
}

function iconClass(space) {
  if (space === 'Bug report') return 'bug';
  if (space === 'Records') return 'record';
  if (space === 'Care') return 'care';
  return 'memory';
}

function friendlyTime(value) {
  const date = new Date(value);
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

const SpeechRecognition = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition);

function MurmurCard({ item, onOpen, onTag }) {
  return (
    <article className="murmur-card" onClick={() => onOpen(item)}>
      <div className="card-top">
        <span className={`type-icon ${iconClass(item.space)}`}>{typeIcon(item.space)}</span>
        {item.sentiment && item.sentiment !== 'neutral' && <span className={`mood ${item.sentiment}`}><Smile size={13} />{item.sentiment}</span>}
      </div>
      <div>
        <span className="space-pill">{item.space} · {item.source || 'text'}</span>
        <h3>{item.title}</h3>
        <p>{item.summary || item.transcript}</p>
      </div>
      {item.tags?.length > 0 && <div className="tag-row">{item.tags.slice(0, 4).map(tag => <button key={tag} className="tag" onClick={e => { e.stopPropagation(); onTag(tag); }}><Hash size={11} />{tag}</button>)}</div>}
      <footer><span>{friendlyTime(item.created_at)}</span><button onClick={e => { e.stopPropagation(); onOpen(item); }}>Open <ChevronRight size={15} /></button></footer>
    </article>
  );
}

export default function App() {
  const [dark, setDark] = useState(true);
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [online, setOnline] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [activeSpace, setActiveSpace] = useState('All murmurs');
  const [activeTag, setActiveTag] = useState('');
  const [view, setView] = useState('grid');
  const [showComposer, setShowComposer] = useState(false);
  const [items, setItems] = useState(demoItems);
  const [error, setError] = useState('');
  const [duplicate, setDuplicate] = useState(null);
  const [onDevice, setOnDevice] = useState(false);
  const [openItem, setOpenItem] = useState(null);
  const [related, setRelated] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [timelineDays, setTimelineDays] = useState([]);
  const [integrations, setIntegrations] = useState({});
  const [showSettings, setShowSettings] = useState(false);
  const [digest, setDigest] = useState(null);
  const [toast, setToast] = useState('');
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const speechRef = useRef(null);
  const searchModeRef = useRef('capture');

  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; }, [dark]);

  useEffect(() => {
    Promise.all([checkHealth(), fetchMurmurs()])
      .then(([, records]) => { setOnline(true); if (records.length) setItems(records); })
      .catch(() => setOnline(false));
    fetchIntegrations().then(setIntegrations).catch(() => {});
    return () => streamRef.current?.getTracks().forEach(track => track.stop());
  }, []);

  // Semantic search when connected; local filtering as a fallback.
  useEffect(() => {
    if (!online || !query.trim()) { setResults(null); return; }
    const handle = setTimeout(() => {
      semanticSearch(query.trim()).then(data => setResults(data.results)).catch(() => setResults(null));
    }, 300);
    return () => clearTimeout(handle);
  }, [query, online]);

  useEffect(() => {
    if (view === 'tasks' && online) fetchTasks().then(data => setTasks(data.tasks)).catch(() => setTasks([]));
    if (view === 'timeline' && online) fetchTimeline().then(data => setTimelineDays(data.days)).catch(() => setTimelineDays([]));
  }, [view, online, items]);

  useEffect(() => {
    if (!openItem || !online) { setRelated([]); return; }
    fetchRelated(openItem.id).then(data => setRelated(data.related)).catch(() => setRelated([]));
  }, [openItem, online]);

  function flash(message) { setToast(message); setTimeout(() => setToast(''), 2600); }

  const localFiltered = useMemo(() => items.filter(item => {
    const text = `${item.title} ${item.transcript} ${(item.tags || []).join(' ')} ${item.space}`.toLowerCase();
    return text.includes(query.toLowerCase());
  }), [items, query]);

  const base = results ?? localFiltered;
  const visible = useMemo(() => base.filter(item =>
    (activeSpace === 'All murmurs' || item.space === activeSpace) &&
    (!activeTag || (item.tags || []).includes(activeTag))
  ), [base, activeSpace, activeTag]);

  const counts = useMemo(() => Object.fromEntries(spaces.map(s => [s.name, items.filter(i => i.space === s.name).length])), [items]);

  function ingest(saved) {
    setItems(prev => [saved, ...prev.filter(item => !String(item.id).startsWith('demo-') && item.id !== saved.id)]);
  }

  async function beginCapture() {
    setError(''); setTranscript(''); setDuplicate(null); setShowComposer(true);
    searchModeRef.current = 'capture';
    if (onDevice && SpeechRecognition) return startOnDevice('capture');
    return startRecorder('capture');
  }

  async function beginVoiceSearch() {
    setError(''); setQuery('');
    searchModeRef.current = 'search';
    if (onDevice && SpeechRecognition) return startOnDevice('search');
    return startRecorder('search');
  }

  function startOnDevice(mode) {
    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = true;
    recognition.continuous = true;
    let finalText = '';
    recognition.onresult = event => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const chunk = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += chunk + ' '; else interim += chunk;
      }
      const text = (finalText + interim).trim();
      if (mode === 'search') setQuery(text); else setTranscript(text);
    };
    recognition.onerror = () => { setError('On-device speech recognition failed. Type instead.'); setRecording(false); };
    recognition.onend = () => setRecording(false);
    speechRef.current = recognition;
    recognition.start();
    setRecording(true);
  }

  async function startRecorder(mode) {
    if (mode === 'capture') setShowComposer(true);
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('Audio recording is unavailable here. You can still type your murmur.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      streamRef.current = stream;
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : undefined });
      recorder.ondataavailable = event => { if (event.data.size) chunksRef.current.push(event.data); };
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        stream.getTracks().forEach(track => track.stop());
        if (!blob.size) return;
        setProcessing(true);
        try {
          if (mode === 'search') {
            const data = await voiceSearch(blob);
            setQuery(data.query); setResults(data.results); setOnline(true);
          } else {
            const saved = await transcribeRecording(blob);
            ingest(saved); setTranscript(saved.transcript); setOnline(true);
          }
        } catch (reason) { setError(reason.message); setOnline(false); }
        finally { setProcessing(false); }
      };
      recorderRef.current = recorder;
      recorder.start(250);
      setRecording(true);
    } catch {
      setError('Microphone permission was not granted. Type your murmur instead.');
    }
  }

  function stopCapture() {
    if (speechRef.current) { speechRef.current.stop(); speechRef.current = null; }
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
    setRecording(false);
  }

  async function saveTypedMurmur() {
    if (!transcript.trim()) return;
    setProcessing(true); setError('');
    try {
      const saved = await createTextMurmur(transcript.trim());
      ingest(saved); setOnline(true);
      if (saved.duplicate_of) setDuplicate(saved.duplicate_of);
      else { setTranscript(''); setShowComposer(false); }
    } catch (reason) { setError(reason.message); setOnline(false); }
    finally { setProcessing(false); }
  }

  async function removeItem(id) {
    if (online) { try { await deleteMurmur(id); } catch {} }
    setItems(prev => prev.filter(item => item.id !== id));
    setOpenItem(null);
  }

  async function share(id, target) {
    try { await shareMurmur(id, target); flash(`Shared to ${target}.`); }
    catch (reason) { flash(reason.message); }
  }

  async function openDigest() {
    setShowSettings(true);
    if (online) fetchDigest().then(setDigest).catch(() => setDigest(null));
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Waves size={22} /></div><div><strong>Murmur</strong><span>Voice, organized.</span></div></div>
      <nav>
        <button className={activeSpace === 'All murmurs' && view === 'grid' ? 'nav-item active' : 'nav-item'} onClick={() => { setActiveSpace('All murmurs'); setActiveTag(''); setView('grid'); }}><Home size={19} />All murmurs<span>{items.length}</span></button>
        <button className={view === 'timeline' ? 'nav-item active' : 'nav-item'} onClick={() => setView('timeline')}><CalendarClock size={19} />Timeline</button>
        <button className={view === 'tasks' ? 'nav-item active' : 'nav-item'} onClick={() => setView('tasks')}><ListTodo size={19} />Tasks<span>{tasks.length || ''}</span></button>
        <p className="nav-label">SPACES</p>
        {spaces.map(({ name, label, icon: Icon }) => <button key={name} className={activeSpace === name && view === 'grid' ? 'nav-item active' : 'nav-item'} onClick={() => { setActiveSpace(name); setActiveTag(''); setView('grid'); }}><Icon size={19} />{label || name}<span>{counts[name] || 0}</span></button>)}
      </nav>
      <div className="privacy-card"><ShieldCheck size={20} /><div><strong>Private by design</strong><span>{onDevice ? 'On-device transcription active.' : 'Self-hosted transcription and storage.'}</span></div></div>
      <button className="profile" onClick={() => setShowSettings(true)}><CircleUserRound size={28} /><div><strong>Sai Nitish</strong><span>{online ? 'Backend connected' : 'Offline preview'}</span></div>{online ? <Wifi size={17} /> : <WifiOff size={17} />}</button>
    </aside>

    <main>
      <header>
        <div className="mobile-brand"><div className="brand-mark"><Waves size={20} /></div><strong>Murmur</strong></div>
        <div className="search"><Search size={19} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder={online ? 'Search by meaning — “where did I put…”' : 'Search anything you’ve said…'} /><button className="voice-search" title="Search by voice" onClick={beginVoiceSearch}><Mic size={16} /></button></div>
        <div className="header-actions"><button className="icon-button" onClick={() => setDark(v => !v)}>{dark ? <Sun size={19} /> : <Moon size={19} />}</button><button className="icon-button" onClick={openDigest}><Bell size={19} /></button><button className="icon-button" onClick={() => setShowSettings(true)}><Settings size={19} /></button></div>
      </header>

      <section className="content">
        {view === 'grid' && <>
          <div className="hero-row">
            <div><span className="eyebrow"><Sparkles size={14} /> PRIVATE VOICE WORKSPACE</span><h1>{activeTag ? `#${activeTag}` : activeSpace}</h1><p>Capture naturally. Murmur removes silence, transcribes{onDevice ? ' on-device' : ' locally'}, tags and organizes the result, and keeps it searchable by meaning.</p></div>
            <button className="new-button" onClick={beginCapture}><Mic size={18} />New murmur</button>
          </div>
          {activeTag && <button className="active-tag" onClick={() => setActiveTag('')}><Hash size={13} />{activeTag} <X size={13} /></button>}
          <section className={recording ? 'voice-console listening' : 'voice-console'}>
            <div className="orb-wrap"><div className="pulse pulse-one" /><div className="pulse pulse-two" /><button className="voice-orb" disabled={processing} onClick={recording ? stopCapture : beginCapture}>{processing ? <LoaderCircle className="spin" size={28} /> : recording ? <Square size={25} fill="currentColor" /> : <Mic size={30} />}</button></div>
            <div className="waveform">{Array.from({ length: 34 }).map((_, i) => <i key={i} style={{ animationDelay: `${i * 35}ms`, height: `${12 + ((i * 13) % 38)}px` }} />)}</div>
            <div className="voice-copy"><strong>{processing ? 'Turning voice into a murmur…' : recording ? 'I’m listening…' : 'What’s on your mind?'}</strong><span>{recording ? 'Pause naturally. Silence is filtered automatically.' : onDevice ? 'On-device mode: nothing leaves your browser.' : online ? 'Whisper backend connected and ready.' : 'Backend offline. Preview data is shown.'}</span></div>
          </section>
          {error && <div className="error-banner">{error}</div>}
          <div className="section-heading"><div><h2>{results ? 'Search results' : 'Recent murmurs'}</h2><span>{visible.length} {results ? 'ranked by relevance' : 'organized captures'}</span></div><div className="view-toggle"><button className="active"><LayoutGrid size={16} /></button><button onClick={() => setView('timeline')}><Clock size={16} /></button></div></div>
          <div className="murmur-grid">{visible.map(item => <MurmurCard key={item.id} item={item} onOpen={setOpenItem} onTag={t => { setActiveTag(t); setResults(null); setQuery(''); }} />)}</div>
        </>}

        {view === 'timeline' && <>
          <div className="hero-row"><div><span className="eyebrow"><CalendarClock size={14} /> TIMELINE</span><h1>Your voice, by day</h1><p>Every capture in chronological order.</p></div><button className="new-button" onClick={beginCapture}><Mic size={18} />New murmur</button></div>
          {!online && <div className="error-banner">Connect the backend to see your full timeline.</div>}
          <div className="timeline">{timelineDays.map(day => <div key={day.date} className="timeline-day"><div className="timeline-date">{new Date(day.date).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}</div><div className="timeline-items">{day.items.map(item => <button key={item.id} className="timeline-item" onClick={() => setOpenItem(item)}><span className={`type-icon ${iconClass(item.space)}`}>{typeIcon(item.space)}</span><div><strong>{item.title}</strong><span>{item.space} · {friendlyTime(item.created_at)}</span></div><ChevronRight size={16} /></button>)}</div></div>)}</div>
        </>}

        {view === 'tasks' && <>
          <div className="hero-row"><div><span className="eyebrow"><ListTodo size={14} /> ACTION ITEMS</span><h1>Extracted tasks</h1><p>Murmur pulls the to-dos out of everything you’ve said.</p></div><button className="new-button" onClick={beginCapture}><Mic size={18} />New murmur</button></div>
          {!online && <div className="error-banner">Connect the backend to extract action items.</div>}
          <div className="task-list">{tasks.map((task, i) => <button key={i} className="task-row" onClick={() => setOpenItem(items.find(m => m.id === task.murmur_id) || null)}><span className="task-check"><Check size={14} /></span><div><strong>{task.action}</strong><span className="space-pill">{task.space}</span></div>{task.due && <span className="due"><CalendarClock size={13} />{new Date(task.due).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>}</button>)}{online && !tasks.length && <p className="empty">No action items found yet.</p>}</div>
        </>}
      </section>
    </main>

    <button className="floating-mic" onClick={beginCapture}><Mic size={24} /></button>

    {toast && <div className="toast">{toast}</div>}

    {showComposer && <div className="modal-backdrop" onMouseDown={() => !recording && !processing && setShowComposer(false)}>
      <div className="composer" onMouseDown={e => e.stopPropagation()}>
        <div className="composer-head"><div><span className="eyebrow"><Sparkles size={13} /> SMART CAPTURE</span><h2>{recording ? 'Listening…' : processing ? 'Processing voice…' : 'New murmur'}</h2></div><button className="icon-button" disabled={processing} onClick={() => { stopCapture(); setShowComposer(false); }}><X size={20} /></button></div>
        <textarea autoFocus value={transcript} onChange={e => setTranscript(e.target.value)} disabled={processing} placeholder="Speak or type anything. Murmur will tag it and choose the right space…" />
        {duplicate && <div className="dup-banner">Looks similar to an existing murmur ({Math.round(duplicate.score * 100)}% match). <button onClick={() => { setTranscript(''); setShowComposer(false); setDuplicate(null); }}>Skip</button> <button onClick={() => { setDuplicate(null); setTranscript(''); setShowComposer(false); }}>Keep both</button></div>}
        {error && <div className="error-banner">{error}</div>}
        <div className="composer-actions">
          <button className={recording ? 'record-control active' : 'record-control'} disabled={processing} onClick={recording ? stopCapture : beginCapture}>{processing ? <><LoaderCircle className="spin" size={17} />Processing</> : recording ? <><Square size={17} />Stop</> : <><Mic size={17} />Record voice</>}</button>
          <button className="save-button" onClick={saveTypedMurmur} disabled={!transcript.trim() || processing || recording}><Check size={17} />Organize murmur</button>
        </div>
      </div>
    </div>}

    {openItem && <div className="modal-backdrop" onMouseDown={() => setOpenItem(null)}>
      <div className="drawer" onMouseDown={e => e.stopPropagation()}>
        <div className="drawer-head"><span className={`type-icon ${iconClass(openItem.space)}`}>{typeIcon(openItem.space)}</span><div><span className="space-pill">{openItem.space} · {openItem.source || 'text'}</span><h2>{openItem.title}</h2></div><button className="icon-button" onClick={() => setOpenItem(null)}><X size={20} /></button></div>
        <p className="drawer-body">{openItem.transcript}</p>
        {openItem.tags?.length > 0 && <div className="tag-row">{openItem.tags.map(tag => <span key={tag} className="tag"><Hash size={11} />{tag}</span>)}</div>}
        <div className="drawer-meta">{openItem.sentiment && <span className={`mood ${openItem.sentiment}`}><Smile size={13} />{openItem.sentiment}</span>}<span>{friendlyTime(openItem.created_at)}</span></div>
        <div className="drawer-actions">
          {integrations.slack && <button onClick={() => share(openItem.id, 'slack')}><Share2 size={15} />Slack</button>}
          {integrations.teams && <button onClick={() => share(openItem.id, 'teams')}><Share2 size={15} />Teams</button>}
          {integrations.notion && <button onClick={() => share(openItem.id, 'notion')}><Send size={15} />Notion</button>}
          <button className="danger" onClick={() => removeItem(openItem.id)}><Trash2 size={15} />Delete</button>
        </div>
        {related.length > 0 && <div className="related"><h4>Related murmurs</h4>{related.map(r => <button key={r.id} className="related-item" onClick={() => setOpenItem(r)}><span>{r.title}</span><small>{Math.round(r.score * 100)}%</small></button>)}</div>}
      </div>
    </div>}

    {showSettings && <div className="modal-backdrop" onMouseDown={() => setShowSettings(false)}>
      <div className="composer settings" onMouseDown={e => e.stopPropagation()}>
        <div className="composer-head"><div><span className="eyebrow"><Settings size={13} /> WORKSPACE</span><h2>Settings & export</h2></div><button className="icon-button" onClick={() => setShowSettings(false)}><X size={20} /></button></div>

        <label className="switch-row"><div><strong>On-device transcription</strong><span>Use your browser’s speech engine — audio never leaves this device.</span></div><button className={onDevice ? 'switch on' : 'switch'} disabled={!SpeechRecognition} onClick={() => setOnDevice(v => !v)}><i /></button></label>
        {!SpeechRecognition && <p className="hint">This browser has no on-device speech engine; the Whisper backend is used instead.</p>}

        <div className="settings-block"><strong>Export</strong><div className="export-grid">
          <a href={exportUrl('csv')}><Download size={15} />CSV</a>
          <a href={exportUrl('json')}><Download size={15} />JSON</a>
          <a href={exportUrl('txt')}><Download size={15} />Transcripts</a>
          <a href={calendarUrl()}><CalendarClock size={15} />Calendar (.ics)</a>
        </div></div>

        <div className="settings-block"><strong>Integrations</strong><div className="integration-list">
          {['slack', 'teams', 'notion', 'email'].map(name => <div key={name} className="integration"><span>{name}</span><em className={integrations[name] ? 'on' : 'off'}>{integrations[name] ? 'connected' : 'not configured'}</em></div>)}
        </div></div>

        <div className="settings-block"><strong>Weekly digest</strong>{digest ? <><p className="hint">{digest.count} captures · {digest.subject}</p><button className="save-button" disabled={!digest.can_email} onClick={() => sendDigest().then(() => flash('Digest emailed.')).catch(e => flash(e.message))}><Send size={16} />{digest.can_email ? 'Email me the digest' : 'Configure SMTP to email'}</button></> : <p className="hint">{online ? 'Loading preview…' : 'Connect the backend to preview your digest.'}</p>}</div>
      </div>
    </div>}
  </div>;
}
