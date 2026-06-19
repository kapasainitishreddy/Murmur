import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Archive, Bell, BookOpen, BriefcaseBusiness, Bug, Check, ChevronRight,
  CircleUserRound, FileText, Home, Mic, Moon, MoreHorizontal, PawPrint,
  Search, Settings, ShieldCheck, Sparkles, Square, Sun, Waves, X
} from 'lucide-react';

const starterItems = [
  { id: 1, title: 'Passport is in the black suitcase', body: 'Second inner pocket, underneath the blue folder.', space: 'Memory', time: 'Today, 9:42 AM', icon: 'memory' },
  { id: 2, title: 'Checkout freezes after coupon', body: 'Payment button stops responding after applying a discount code.', space: 'Bug report', time: 'Yesterday', icon: 'bug' },
  { id: 3, title: 'Contractor scope update', body: 'Replace damaged kitchen tiles and finish by Friday.', space: 'Records', time: 'Jun 16', icon: 'record' },
  { id: 4, title: 'Pebble care note', body: 'Ate half the food and scratched the left ear twice.', space: 'Care', time: 'Jun 15', icon: 'care' }
];

const spaces = [
  { name: 'Memory', icon: BookOpen, count: 18, hint: 'Things, places and moments' },
  { name: 'Work', icon: BriefcaseBusiness, count: 12, hint: 'Tasks, SOPs and updates' },
  { name: 'Records', icon: FileText, count: 9, hint: 'Inspections and agreements' },
  { name: 'Care', icon: PawPrint, count: 7, hint: 'Health and pet notes' },
  { name: 'Bugs', icon: Bug, count: 5, hint: 'Issues and reproduction steps' }
];

function detectSpace(text) {
  const value = text.toLowerCase();
  if (/bug|error|freeze|broken|crash|button|issue/.test(value)) return 'Bug report';
  if (/contractor|apartment|damage|inspection|warranty|agreed/.test(value)) return 'Records';
  if (/pet|dog|cat|vet|medicine|food|pain|doctor/.test(value)) return 'Care';
  if (/task|client|project|inventory|follow up|work/.test(value)) return 'Work';
  return 'Memory';
}

function iconFor(type) {
  if (type === 'bug') return <Bug size={18} />;
  if (type === 'record') return <FileText size={18} />;
  if (type === 'care') return <PawPrint size={18} />;
  return <BookOpen size={18} />;
}

export default function App() {
  const [dark, setDark] = useState(true);
  const [recording, setRecording] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [query, setQuery] = useState('');
  const [activeSpace, setActiveSpace] = useState('All murmurs');
  const [showComposer, setShowComposer] = useState(false);
  const [items, setItems] = useState(() => {
    const saved = localStorage.getItem('murmur-items');
    return saved ? JSON.parse(saved) : starterItems;
  });
  const recognitionRef = useRef(null);

  useEffect(() => localStorage.setItem('murmur-items', JSON.stringify(items)), [items]);
  useEffect(() => document.documentElement.dataset.theme = dark ? 'dark' : 'light', [dark]);

  const filtered = useMemo(() => items.filter(item => {
    const matchesQuery = `${item.title} ${item.body} ${item.space}`.toLowerCase().includes(query.toLowerCase());
    const matchesSpace = activeSpace === 'All murmurs' || item.space.toLowerCase().includes(activeSpace.toLowerCase().replace('bugs', 'bug'));
    return matchesQuery && matchesSpace;
  }), [items, query, activeSpace]);

  function beginCapture() {
    setShowComposer(true);
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setTranscript('Voice recognition is unavailable in this browser. Type your murmur here instead.');
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    recognition.onresult = event => {
      let value = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) value += event.results[i][0].transcript;
      setTranscript(value.trim());
    };
    recognition.onend = () => setRecording(false);
    recognitionRef.current = recognition;
    recognition.start();
    setRecording(true);
  }

  function stopCapture() {
    recognitionRef.current?.stop();
    setRecording(false);
  }

  function saveMurmur() {
    const clean = transcript.trim();
    if (!clean) return;
    const space = detectSpace(clean);
    const title = clean.length > 54 ? `${clean.slice(0, 54)}…` : clean;
    const icon = space === 'Bug report' ? 'bug' : space === 'Records' ? 'record' : space === 'Care' ? 'care' : 'memory';
    setItems(prev => [{ id: Date.now(), title, body: clean, space, time: 'Just now', icon }, ...prev]);
    setTranscript('');
    setShowComposer(false);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><Waves size={22}/></div><div><strong>Murmur</strong><span>Voice, organized.</span></div></div>
        <nav>
          <button className={activeSpace === 'All murmurs' ? 'nav-item active' : 'nav-item'} onClick={() => setActiveSpace('All murmurs')}><Home size={19}/>All murmurs<span>{items.length}</span></button>
          <p className="nav-label">SPACES</p>
          {spaces.map(({name, icon: Icon, count}) => <button key={name} className={activeSpace === name ? 'nav-item active' : 'nav-item'} onClick={() => setActiveSpace(name)}><Icon size={19}/>{name}<span>{count}</span></button>)}
        </nav>
        <div className="privacy-card"><ShieldCheck size={20}/><div><strong>Private by design</strong><span>Your captures stay on this device.</span></div></div>
        <button className="profile"><CircleUserRound size={28}/><div><strong>Sai Nitish</strong><span>Personal workspace</span></div><MoreHorizontal size={18}/></button>
      </aside>

      <main>
        <header>
          <div className="mobile-brand"><div className="brand-mark"><Waves size={20}/></div><strong>Murmur</strong></div>
          <div className="search"><Search size={19}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search anything you’ve said…"/><kbd>⌘ K</kbd></div>
          <div className="header-actions"><button className="icon-button" onClick={() => setDark(v => !v)}>{dark ? <Sun size={19}/> : <Moon size={19}/>}</button><button className="icon-button"><Bell size={19}/></button><button className="icon-button"><Settings size={19}/></button></div>
        </header>

        <section className="content">
          <div className="hero-row"><div><span className="eyebrow"><Sparkles size={14}/> YOUR VOICE WORKSPACE</span><h1>{activeSpace}</h1><p>Speak naturally. Murmur turns your words into memories, records and useful actions.</p></div><button className="new-button" onClick={beginCapture}><Mic size={18}/>New murmur</button></div>

          <section className={recording ? 'voice-console listening' : 'voice-console'}>
            <div className="orb-wrap"><div className="pulse pulse-one"/><div className="pulse pulse-two"/><button className="voice-orb" onClick={recording ? stopCapture : beginCapture}>{recording ? <Square size={25} fill="currentColor"/> : <Mic size={30}/>}</button></div>
            <div className="waveform">{Array.from({length: 34}).map((_, i) => <i key={i} style={{animationDelay: `${i * 35}ms`, height: `${12 + ((i * 13) % 38)}px`}} />)}</div>
            <div className="voice-copy"><strong>{recording ? 'I’m listening…' : 'What’s on your mind?'}</strong><span>{recording ? 'Speak freely. I’ll organize it when you’re done.' : 'Tap to capture a memory, task, record or thought.'}</span></div>
          </section>

          <div className="section-heading"><div><h2>Recent murmurs</h2><span>{filtered.length} organized captures</span></div><button>View timeline <ChevronRight size={16}/></button></div>
          <div className="murmur-grid">
            {filtered.map(item => <article className="murmur-card" key={item.id}><div className="card-top"><span className={`type-icon ${item.icon}`}>{iconFor(item.icon)}</span><button><MoreHorizontal size={18}/></button></div><div><span className="space-pill">{item.space}</span><h3>{item.title}</h3><p>{item.body}</p></div><footer><span>{item.time}</span><button>Open <ChevronRight size={15}/></button></footer></article>)}
          </div>
        </section>
      </main>

      <button className="floating-mic" onClick={beginCapture}><Mic size={24}/></button>

      {showComposer && <div className="modal-backdrop" onMouseDown={() => !recording && setShowComposer(false)}><div className="composer" onMouseDown={e => e.stopPropagation()}><div className="composer-head"><div><span className="eyebrow"><Sparkles size={13}/> SMART CAPTURE</span><h2>New murmur</h2></div><button className="icon-button" onClick={() => { stopCapture(); setShowComposer(false); }}><X size={20}/></button></div><textarea autoFocus value={transcript} onChange={e => setTranscript(e.target.value)} placeholder="Speak or type anything. Murmur will find the right space…"/><div className="detected"><Sparkles size={16}/><span>Detected space</span><strong>{transcript ? detectSpace(transcript) : 'Waiting for your voice'}</strong></div><div className="composer-actions"><button className={recording ? 'record-control active' : 'record-control'} onClick={recording ? stopCapture : beginCapture}>{recording ? <><Square size={17}/>Stop listening</> : <><Mic size={17}/>Start listening</>}</button><button className="save-button" onClick={saveMurmur} disabled={!transcript.trim()}><Check size={17}/>Organize murmur</button></div></div></div>}
    </div>
  );
}
