import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Bell, BookOpen, BriefcaseBusiness, Bug, Check, ChevronRight, CircleUserRound, FileText, Home, LoaderCircle, Mic, Moon, MoreHorizontal, PawPrint, Search, Settings, ShieldCheck, Sparkles, Square, Sun, Waves, Wifi, WifiOff, X } from 'lucide-react';
import { checkHealth, createTextMurmur, fetchMurmurs, transcribeRecording } from './lib/api';

const demoItems = [
  { id: 'demo-1', title: 'Passport is in the black suitcase', transcript: 'Second inner pocket, underneath the blue folder.', space: 'Memory', created_at: new Date().toISOString(), source: 'text' },
  { id: 'demo-2', title: 'Checkout freezes after coupon', transcript: 'Payment button stops responding after applying a discount code.', space: 'Bug report', created_at: new Date(Date.now() - 86400000).toISOString(), source: 'voice' },
  { id: 'demo-3', title: 'Contractor scope update', transcript: 'Replace damaged kitchen tiles and finish by Friday.', space: 'Records', created_at: new Date(Date.now() - 172800000).toISOString(), source: 'voice' },
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

export default function App() {
  const [dark, setDark] = useState(true);
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [online, setOnline] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [query, setQuery] = useState('');
  const [activeSpace, setActiveSpace] = useState('All murmurs');
  const [showComposer, setShowComposer] = useState(false);
  const [items, setItems] = useState(demoItems);
  const [error, setError] = useState('');
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);

  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; }, [dark]);
  useEffect(() => {
    Promise.all([checkHealth(), fetchMurmurs()])
      .then(([, records]) => { setOnline(true); if (records.length) setItems(records); })
      .catch(() => setOnline(false));
    return () => streamRef.current?.getTracks().forEach(track => track.stop());
  }, []);

  const filtered = useMemo(() => items.filter(item => {
    const text = `${item.title} ${item.transcript} ${item.space}`.toLowerCase();
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
      const recorder = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : undefined });
      recorder.ondataavailable = event => { if (event.data.size) chunksRef.current.push(event.data); };
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        stream.getTracks().forEach(track => track.stop());
        if (!blob.size) return;
        setProcessing(true);
        try {
          const saved = await transcribeRecording(blob);
          setItems(prev => [saved, ...prev.filter(item => !String(item.id).startsWith('demo-'))]);
          setTranscript(saved.transcript);
          setOnline(true);
        } catch (reason) {
          setError(reason.message);
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

  async function saveTypedMurmur() {
    if (!transcript.trim()) return;
    setProcessing(true);
    setError('');
    try {
      const saved = await createTextMurmur(transcript.trim());
      setItems(prev => [saved, ...prev.filter(item => !String(item.id).startsWith('demo-'))]);
      setOnline(true);
      setTranscript('');
      setShowComposer(false);
    } catch (reason) {
      setError(reason.message);
      setOnline(false);
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
      <button className="profile"><CircleUserRound size={28}/><div><strong>Sai Nitish</strong><span>{online ? 'Backend connected' : 'Offline preview'}</span></div>{online ? <Wifi size={17}/> : <WifiOff size={17}/>}</button>
    </aside>

    <main>
      <header><div className="mobile-brand"><div className="brand-mark"><Waves size={20}/></div><strong>Murmur</strong></div><div className="search"><Search size={19}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search anything you’ve said…"/><kbd>⌘ K</kbd></div><div className="header-actions"><button className="icon-button" onClick={() => setDark(v => !v)}>{dark ? <Sun size={19}/> : <Moon size={19}/>}</button><button className="icon-button"><Bell size={19}/></button><button className="icon-button"><Settings size={19}/></button></div></header>
      <section className="content">
        <div className="hero-row"><div><span className="eyebrow"><Sparkles size={14}/> PRIVATE VOICE WORKSPACE</span><h1>{activeSpace}</h1><p>Capture naturally. Murmur removes silence, transcribes locally, organizes the result and keeps it searchable.</p></div><button className="new-button" onClick={beginCapture}><Mic size={18}/>New murmur</button></div>
        <section className={recording ? 'voice-console listening' : 'voice-console'}>
          <div className="orb-wrap"><div className="pulse pulse-one"/><div className="pulse pulse-two"/><button className="voice-orb" disabled={processing} onClick={recording ? stopCapture : beginCapture}>{processing ? <LoaderCircle className="spin" size={28}/> : recording ? <Square size={25} fill="currentColor"/> : <Mic size={30}/>}</button></div>
          <div className="waveform">{Array.from({length:34}).map((_,i)=><i key={i} style={{animationDelay:`${i*35}ms`,height:`${12+((i*13)%38)}px`}} />)}</div>
          <div className="voice-copy"><strong>{processing ? 'Turning voice into a murmur…' : recording ? 'I’m listening…' : 'What’s on your mind?'}</strong><span>{recording ? 'Pause naturally. Silence is filtered automatically.' : online ? 'Whisper backend connected and ready.' : 'Backend offline. Preview data is shown.'}</span></div>
        </section>
        {error && <div className="error-banner">{error}</div>}
        <div className="section-heading"><div><h2>Recent murmurs</h2><span>{filtered.length} organized captures</span></div><button>View timeline <ChevronRight size={16}/></button></div>
        <div className="murmur-grid">{filtered.map(item => <article className="murmur-card" key={item.id}><div className="card-top"><span className={`type-icon ${iconClass(item.space)}`}>{typeIcon(item.space)}</span><button><MoreHorizontal size={18}/></button></div><div><span className="space-pill">{item.space} · {item.source || 'text'}</span><h3>{item.title}</h3><p>{item.transcript}</p></div><footer><span>{friendlyTime(item.created_at)}</span><button>Open <ChevronRight size={15}/></button></footer></article>)}</div>
      </section>
    </main>
    <button className="floating-mic" onClick={beginCapture}><Mic size={24}/></button>
    {showComposer && <div className="modal-backdrop" onMouseDown={() => !recording && !processing && setShowComposer(false)}><div className="composer" onMouseDown={e => e.stopPropagation()}><div className="composer-head"><div><span className="eyebrow"><Sparkles size={13}/> SMART CAPTURE</span><h2>{recording ? 'Listening…' : processing ? 'Processing voice…' : 'New murmur'}</h2></div><button className="icon-button" disabled={processing} onClick={() => {stopCapture();setShowComposer(false)}}><X size={20}/></button></div><textarea autoFocus value={transcript} onChange={e => setTranscript(e.target.value)} disabled={recording || processing} placeholder="Speak or type anything. Murmur will choose the right space…"/>{error && <div className="error-banner">{error}</div>}<div className="composer-actions"><button className={recording ? 'record-control active' : 'record-control'} disabled={processing} onClick={recording ? stopCapture : beginCapture}>{processing ? <><LoaderCircle className="spin" size={17}/>Processing</> : recording ? <><Square size={17}/>Stop and transcribe</> : <><Mic size={17}/>Record voice</>}</button><button className="save-button" onClick={saveTypedMurmur} disabled={!transcript.trim() || processing || recording}><Check size={17}/>Organize murmur</button></div></div></div>}
  </div>;
}
