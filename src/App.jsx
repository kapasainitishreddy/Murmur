import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BookOpen, BriefcaseBusiness, Bug, Check, ChevronRight, CircleUserRound, Download, FileText, Home, LoaderCircle, Mic, Moon, MoreHorizontal, PawPrint, Pin, Search, Settings, ShieldCheck, Sparkles, Square, Sun, Trash2, Upload, Waves, Wifi, WifiOff, X } from 'lucide-react';
import { checkHealth, createTextMurmur, deleteMurmur, eraseAllMurmurs, exportBackup, fetchMurmurs, restoreBackup, transcribeRecording, updateMurmur } from './lib/api';

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

function messageOf(reason, fallback) {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}

function tagsFromInput(value) {
  return value
    .split(',')
    .map(tag => tag.trim())
    .filter(Boolean);
}

export default function App() {
  const [dark, setDark] = useState(true);
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [online, setOnline] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [query, setQuery] = useState('');
  const [activeSpace, setActiveSpace] = useState('All murmurs');
  const [showComposer, setShowComposer] = useState(false);
  const [showData, setShowData] = useState(false);
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [editTranscript, setEditTranscript] = useState('');
  const [editSpace, setEditSpace] = useState('Memory');
  const [editTags, setEditTags] = useState('');
  const [editPinned, setEditPinned] = useState(false);
  const [error, setError] = useState('');
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const importRef = useRef(null);

  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; }, [dark]);

  const refresh = useCallback(async () => {
    try {
      await checkHealth();
      const records = await fetchMurmurs();
      setItems(records);
      setOnline(true);
      setError('');
    } catch (reason) {
      setOnline(false);
      setError(messageOf(reason, 'Murmur backend is offline. Drafts stay on screen until you reconnect.'));
    }
  }, []);

  useEffect(() => {
    refresh();
    return () => streamRef.current?.getTracks().forEach(track => track.stop());
  }, [refresh]);

  const filtered = useMemo(() => items.filter(item => {
    const text = `${item.title} ${item.transcript} ${item.space} ${(item.tags || []).join(' ')}`.toLowerCase();
    return text.includes(query.toLowerCase()) && (activeSpace === 'All murmurs' || item.space === activeSpace);
  }), [items, query, activeSpace]);

  const counts = useMemo(() => Object.fromEntries(spaces.map(s => [s.name, items.filter(i => i.space === s.name).length])), [items]);

  async function beginCapture() {
    setError('');
    setTranscript('');
    setShowComposer(true);
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('Audio recording is unavailable here. You can still type your murmur.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      streamRef.current = stream;
      chunksRef.current = [];
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : undefined;
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorder.ondataavailable = event => { if (event.data.size) chunksRef.current.push(event.data); };
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        stream.getTracks().forEach(track => track.stop());
        streamRef.current = null;
        if (!blob.size) {
          setError('No audio was captured. Type your murmur or record again.');
          return;
        }
        setProcessing(true);
        try {
          const saved = await transcribeRecording(blob);
          setItems(prev => [saved, ...prev]);
          setTranscript(saved.transcript);
          setOnline(true);
        } catch (reason) {
          setError(messageOf(reason, 'Voice transcription failed. Your typed draft is still available.'));
          setOnline(false);
        } finally {
          setProcessing(false);
        }
      };
      recorderRef.current = recorder;
      recorder.start(250);
      setRecording(true);
    } catch {
      setError('Microphone permission was not granted. Type your murmur instead.');
    }
  }

  function stopCapture() {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
    setRecording(false);
  }

  function closeComposer() {
    stopCapture();
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
    setShowComposer(false);
  }

  async function saveTypedMurmur() {
    if (!transcript.trim()) return;
    setProcessing(true);
    setError('');
    try {
      const saved = await createTextMurmur(transcript.trim());
      setItems(prev => [saved, ...prev]);
      setOnline(true);
      setTranscript('');
      setShowComposer(false);
    } catch (reason) {
      setError(messageOf(reason, 'Could not save. Your draft is still here.'));
      setOnline(false);
    } finally {
      setProcessing(false);
    }
  }

  function openRecord(item) {
    setSelected(item);
    setEditTitle(item.title);
    setEditTranscript(item.transcript);
    setEditSpace(item.space);
    setEditTags((item.tags || []).join(', '));
    setEditPinned(Boolean(item.pinned));
    setError('');
  }

  async function saveRecord() {
    if (!selected) return;
    setProcessing(true);
    setError('');
    try {
      const saved = await updateMurmur(selected.id, {
        title: editTitle,
        transcript: editTranscript,
        space: editSpace,
        tags: editTags,
        pinned: editPinned,
      });
      const tags = tagsFromInput(editTags);
      const normalizedSaved = { ...saved, tags: saved.tags || tags, pinned: Boolean(saved.pinned) };
      setItems(prev => prev
        .map(item => item.id === normalizedSaved.id ? normalizedSaved : item)
        .sort((a, b) => Number(Boolean(b.pinned)) - Number(Boolean(a.pinned)) || new Date(b.created_at) - new Date(a.created_at)));
      setSelected(normalizedSaved);
      setOnline(true);
    } catch (reason) {
      setError(messageOf(reason, 'Could not update this murmur.'));
    } finally {
      setProcessing(false);
    }
  }

  async function removeRecord() {
    if (!selected || !window.confirm('Delete this murmur permanently?')) return;
    setProcessing(true);
    try {
      await deleteMurmur(selected.id);
      setItems(prev => prev.filter(item => item.id !== selected.id));
      setSelected(null);
    } catch (reason) {
      setError(messageOf(reason, 'Could not delete this murmur.'));
    } finally {
      setProcessing(false);
    }
  }

  async function downloadBackup() {
    setProcessing(true);
    setError('');
    try {
      const backup = await exportBackup();
      const blob = new Blob([JSON.stringify(backup, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `murmur-backup-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(messageOf(reason, 'Could not export your backup.'));
    } finally {
      setProcessing(false);
    }
  }

  async function importBackup(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!window.confirm('Restore this backup and replace the current Murmur library?')) return;
    setProcessing(true);
    setError('');
    try {
      const backup = JSON.parse(await file.text());
      await restoreBackup(backup, 'replace');
      await refresh();
      setShowData(false);
    } catch (reason) {
      setError(messageOf(reason, 'Backup restore failed. Your existing library was not intentionally changed.'));
    } finally {
      setProcessing(false);
    }
  }

  async function eraseLibrary() {
    if (!window.confirm('Erase every murmur on this backend? This cannot be undone.')) return;
    if (!window.confirm('Confirm permanent deletion of the entire Murmur library.')) return;
    setProcessing(true);
    setError('');
    try {
      await eraseAllMurmurs();
      setItems([]);
      setSelected(null);
      setShowData(false);
    } catch (reason) {
      setError(messageOf(reason, 'Could not erase the library.'));
    } finally {
      setProcessing(false);
    }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Waves size={22}/></div><div><strong>Murmur</strong><span>Voice, organized.</span></div></div>
      <nav>
        <button className={activeSpace === 'All murmurs' ? 'nav-item active' : 'nav-item'} onClick={() => setActiveSpace('All murmurs')}><Home size={19}/>All murmurs<span>{items.length}</span></button>
        <p className="nav-label">SPACES</p>
        {spaces.map(({name,label,icon:Icon}) => <button key={name} className={activeSpace === name ? 'nav-item active' : 'nav-item'} onClick={() => setActiveSpace(name)}><Icon size={19}/>{label || name}<span>{counts[name] || 0}</span></button>)}
      </nav>
      <div className="privacy-card"><ShieldCheck size={20}/><div><strong>Private by design</strong><span>Self-hosted transcription and storage.</span></div></div>
      <button className="profile" onClick={() => setShowData(true)}><CircleUserRound size={28}/><div><strong>Local workspace</strong><span>{online ? 'Backend connected' : 'Backend offline'}</span></div>{online ? <Wifi size={17}/> : <WifiOff size={17}/>}</button>
    </aside>

    <main>
      <header><div className="mobile-brand"><div className="brand-mark"><Waves size={20}/></div><strong>Murmur</strong></div><div className="search"><Search size={19}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search your murmurs…"/><kbd>⌘ K</kbd></div><div className="header-actions"><button className="icon-button" aria-label="Toggle theme" onClick={() => setDark(v => !v)}>{dark ? <Sun size={19}/> : <Moon size={19}/>}</button><button className="icon-button" aria-label="Data and settings" onClick={() => setShowData(true)}><Settings size={19}/></button></div></header>
      <section className="content">
        <div className="hero-row"><div><span className="eyebrow"><Sparkles size={14}/> PRIVATE VOICE WORKSPACE</span><h1>{activeSpace}</h1><p>Capture naturally. Murmur transcribes through your configured backend, organizes the result and keeps it searchable.</p></div><button className="new-button" onClick={beginCapture}><Mic size={18}/>New murmur</button></div>
        <section className={recording ? 'voice-console listening' : 'voice-console'}>
          <div className="orb-wrap"><div className="pulse pulse-one"/><div className="pulse pulse-two"/><button className="voice-orb" disabled={processing} onClick={recording ? stopCapture : beginCapture}>{processing ? <LoaderCircle className="spin" size={28}/> : recording ? <Square size={25} fill="currentColor"/> : <Mic size={30}/>}</button></div>
          <div className="waveform">{Array.from({length:34}).map((_,i)=><i key={i} style={{animationDelay:`${i*35}ms`,height:`${12+((i*13)%38)}px`}} />)}</div>
          <div className="voice-copy"><strong>{processing ? 'Working…' : recording ? 'Listening…' : 'What’s on your mind?'}</strong><span>{recording ? 'Pause naturally. Stop when you are finished.' : online ? 'Your configured Murmur backend is connected.' : 'Backend offline. Drafts stay on screen until you reconnect.'}</span></div>
        </section>
        {error && <div className="error-banner" role="status">{error}</div>}
        <div className="section-heading"><div><h2>Recent murmurs</h2><span>{filtered.length} saved captures</span></div></div>
        <div className="murmur-grid">
          {filtered.length === 0 ? <article className="murmur-card"><div><span className="space-pill">YOUR LIBRARY</span><h3>No murmurs yet</h3><p>{items.length ? 'No saved murmurs match this search or space.' : 'Record or type your first murmur. Nothing is pre-filled with demo history.'}</p></div></article> : filtered.map(item => <article className="murmur-card" key={item.id} onClick={() => openRecord(item)}><div className="card-top"><span className={`type-icon ${iconClass(item.space)}`}>{typeIcon(item.space)}</span><button aria-label={`Open ${item.title}`} onClick={event => {event.stopPropagation();openRecord(item)}}><MoreHorizontal size={18}/></button></div><div><span className="space-pill">{item.space} · {item.source || 'text'}</span>{item.pinned && <span className="space-pill"><Pin size={12}/> Pinned</span>}<h3>{item.title}</h3><p>{item.transcript}</p>{item.tags?.length > 0 && <p>{item.tags.map(tag => `#${tag}`).join(' ')}</p>}</div><footer><span>{friendlyTime(item.created_at)}</span><button onClick={event => {event.stopPropagation();openRecord(item)}}>Open <ChevronRight size={15}/></button></footer></article>)}
        </div>
      </section>
    </main>
    <button className="floating-mic" aria-label="New murmur" onClick={beginCapture}><Mic size={24}/></button>

    {showComposer && <div className="modal-backdrop" onMouseDown={() => !recording && !processing && closeComposer()}><div className="composer" onMouseDown={e => e.stopPropagation()}><div className="composer-head"><div><span className="eyebrow"><Sparkles size={13}/> CAPTURE</span><h2>{recording ? 'Listening…' : processing ? 'Processing voice…' : 'New murmur'}</h2></div><button className="icon-button" aria-label="Close capture" disabled={processing} onClick={closeComposer}><X size={20}/></button></div><textarea autoFocus value={transcript} onChange={e => setTranscript(e.target.value)} disabled={recording || processing} placeholder="Speak or type anything. Murmur will choose the right space…"/>{error && <div className="error-banner">{error}</div>}<div className="composer-actions"><button className={recording ? 'record-control active' : 'record-control'} disabled={processing} onClick={recording ? stopCapture : beginCapture}>{processing ? <><LoaderCircle className="spin" size={17}/>Processing</> : recording ? <><Square size={17}/>Stop and transcribe</> : <><Mic size={17}/>Record voice</>}</button><button className="save-button" onClick={saveTypedMurmur} disabled={!transcript.trim() || processing || recording}><Check size={17}/>Save murmur</button></div></div></div>}

    {selected && <div className="modal-backdrop" onMouseDown={() => !processing && setSelected(null)}><div className="composer" onMouseDown={e => e.stopPropagation()}><div className="composer-head"><div><span className="eyebrow"><FileText size={13}/> SAVED MURMUR</span><h2>Edit record</h2></div><button className="icon-button" aria-label="Close record" disabled={processing} onClick={() => setSelected(null)}><X size={20}/></button></div><label>Title<input value={editTitle} onChange={e => setEditTitle(e.target.value)} /></label><label>Space<select value={editSpace} onChange={e => setEditSpace(e.target.value)}>{spaces.map(space => <option key={space.name}>{space.name}</option>)}</select></label><label>Tags<input value={editTags} onChange={e => setEditTags(e.target.value)} placeholder="travel, important" /></label><label><input type="checkbox" checked={editPinned} onChange={e => setEditPinned(e.target.checked)} /> Pinned</label><label>Transcript<textarea value={editTranscript} onChange={e => setEditTranscript(e.target.value)} /></label><div className="composer-actions"><button className="record-control" disabled={processing} onClick={removeRecord}><Trash2 size={17}/>Delete</button><button className="save-button" disabled={processing || !editTitle.trim() || !editTranscript.trim()} onClick={saveRecord}><Check size={17}/>Save changes</button></div></div></div>}

    {showData && <div className="modal-backdrop" onMouseDown={() => !processing && setShowData(false)}><div className="composer" onMouseDown={e => e.stopPropagation()}><div className="composer-head"><div><span className="eyebrow"><ShieldCheck size={13}/> DATA OWNERSHIP</span><h2>Backup and privacy</h2></div><button className="icon-button" aria-label="Close data settings" disabled={processing} onClick={() => setShowData(false)}><X size={20}/></button></div><p>Your saved Murmurs live on the backend you configured. Export a portable JSON backup before destructive changes.</p><input ref={importRef} type="file" accept="application/json,.json" hidden onChange={importBackup}/><div className="composer-actions"><button className="record-control" disabled={processing} onClick={downloadBackup}><Download size={17}/>Export JSON</button><button className="record-control" disabled={processing} onClick={() => importRef.current?.click()}><Upload size={17}/>Restore JSON</button></div><div className="composer-actions"><button className="record-control" disabled={processing} onClick={eraseLibrary}><Trash2 size={17}/>Erase all murmurs</button></div></div></div>}
  </div>;
}
