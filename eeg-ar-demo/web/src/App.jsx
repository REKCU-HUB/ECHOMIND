import { eeg, useEEG } from './eegBridge';
import { DemoStatus } from './DemoStatus';
import { input, useInputMode } from './gazeInput';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { toPng } from "html-to-image";
import {
  ArrowsCounterClockwise,
  ArrowsVertical,
  Bed,
  BellRinging,
  Camera,
  CaretLeft,
  CaretRight,
  Check,
  CloudSun,
  Drop,
  Eye,
  EyeSlash,
  Hand,
  HandHeart,
  Heart,
  House,
  Microphone,
  Moon,
  Pause,
  PersonSimple,
  Play,
  Smiley,
  Snowflake,
  SpeakerHigh,
  Sun,
  SunHorizon,
  ThermometerHot,
  ThumbsUp,
  UploadSimple,
  UserCircle,
  Waveform,
  X,
} from "@phosphor-icons/react";

const CARE_ITEMS = [
  { label: "Turn me", icon: ArrowsCounterClockwise },
  { label: "I feel itchy", icon: Hand },
  { label: "I’m thirsty", icon: Drop },
  { label: "I’m in pain", icon: PersonSimple },
  { label: "Adjust the bed", icon: Bed },
  { label: "Too hot", icon: ThermometerHot },
  { label: "Too cold", icon: Snowflake },
  { label: "Call a nurse", icon: BellRinging },
];

const FAMILY_MESSAGES = [
  { sender: "Emma", relation: "Wife", type: "voice", duration: "0:18", preview: "I’m here with you. You’re doing so well." },
  { sender: "Mum & Dad", relation: "Parents", type: "text", preview: "We’re thinking of you every day." },
  { sender: "Noah", relation: "Son", type: "text", preview: "Love you. I drew a picture for you." },
];

const TRANSCRIPT = [
  "I’m here with you.",
  "You’re doing so well.",
  "We’re thinking of you, and we love you.",
];

const REACTIONS = [
  { label: "Heart", icon: Heart },
  { label: "Smile", icon: Smiley },
  { label: "Thumbs up", icon: ThumbsUp },
  { label: "Hug", icon: HandHeart },
];

function DwellButton({ children, className = "", onActivate, duration = 900, ariaLabel, disabled = false, testId }) {
  const id = useId();
  const state = useEEG();
  const callback = useRef(onActivate);
  callback.current = onActivate;
  const disabledRef = useRef(disabled);
  disabledRef.current = disabled;
  const label = ariaLabel?.split(",")[0] || testId || "AR control";
  const active = state.target?.id === id;
  useEffect(() => input.register(id, {
    label, confirm: () => callback.current(), disabled: () => disabledRef.current,
  }), [id, label]);
  useEffect(() => { if (disabled) eeg.leave(id); }, [disabled, id]);
  return <button type="button" className={`dwell-target ${active ? "is-dwelling" : ""} ${active && state.phase === "confirmed" ? "is-eeg-confirmed" : ""} ${className}`}
    aria-label={ariaLabel} disabled={disabled} data-testid={testId} data-eeg-target={id}
    onPointerEnter={() => input.mouseFocus(id)} onPointerLeave={() => input.mouseLeave(id)} onPointerCancel={() => input.mouseLeave(id)}
    onBlur={() => input.mouseLeave(id)} onClick={() => input.mouseFocus(id, "click")}
    style={{ "--dwell-duration": `${state.config.dwell_ms}ms`, "--eeg-progress": active ? state.progress : 0 }}>
    {children}<span className="dwell-line" aria-hidden="true" />
  </button>;
}

function ActivationPrompt({ onActivate }) {
  return (
    <section className="activation-prompt" aria-label="Activate the interface">
      <DwellButton
        className="activation-target"
        onActivate={onActivate}
        duration={1050}
        ariaLabel="Look here to activate. Hold your gaze and focus."
        testId="activation-gaze-target"
      >
        <span className="activation-target__icon" aria-hidden="true"><Eye size={42} weight="light" /></span>
        <span className="activation-target__copy">
          <strong>Look here to activate</strong>
          <small>Hold your gaze and focus</small>
        </span>
      </DwellButton>
      <p>Take your time. The controls will open when you are ready.</p>
    </section>
  );
}

function StatusCard({ type, expanded, onExpand, onCollapse, timeLabel, dateLabel, daypart, DayIcon, onOpenVoice }) {
  const expandTimer = useRef(null);
  const collapseTimer = useRef(null);
  const isDaily = type === "daily";

  const beginExpand = () => {
    window.clearTimeout(collapseTimer.current);
    if (expanded) return;
    expandTimer.current = window.setTimeout(onExpand, 650);
  };

  const beginCollapse = () => {
    window.clearTimeout(expandTimer.current);
    collapseTimer.current = window.setTimeout(onCollapse, 1400);
  };

  useEffect(
    () => () => {
      window.clearTimeout(expandTimer.current);
      window.clearTimeout(collapseTimer.current);
    },
    [],
  );

  return (
    <section
      className={`status-card status-card--${type} ${expanded ? "is-expanded" : "is-collapsed"}`}
      aria-label={isDaily ? "Daily rhythm status" : "Family message status"}
      data-testid={`${type}-status-card`}
      tabIndex={0}
      onPointerEnter={beginExpand}
      onPointerLeave={beginCollapse}
      onFocus={onExpand}
      onBlur={beginCollapse}
      onClick={onExpand}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") onExpand();
      }}
    >
      <div className="status-card__compact">
        <span className="status-card__icon" aria-hidden="true">
          {isDaily ? <DayIcon size={30} weight="light" /> : <Microphone size={28} weight="light" />}
        </span>
        <span className="status-card__compact-copy">
          <strong>{isDaily ? timeLabel : "1 new message"}</strong>
          <small>{isDaily ? daypart : "Emma · voice 0:18"}</small>
        </span>
      </div>

      <div className="status-card__expanded">
        {isDaily ? (
          <>
            <DayIcon className="daily-symbol" size={58} weight="light" aria-hidden="true" />
            <div className="daily-copy">
              <div className="daily-copy__time">{timeLabel}</div>
              <div className="daily-copy__date">{dateLabel}</div>
              <div className="daily-copy__weather"><CloudSun size={18} weight="light" /> 22°C · Clear</div>
              <p>{daypart}. A new day is beginning.</p>
            </div>
          </>
        ) : (
          <>
            <div className="message-card__heading">
              <span><strong>Emma</strong> · Wife</span>
              <span className="unread-dot" aria-label="Unread message" />
            </div>
            <p className="message-card__meta"><Waveform size={18} weight="light" /> Voice message · 0:18</p>
            <p className="message-card__preview">I’m here with you. You’re doing so well.</p>
            <button
              type="button"
              className="message-card__play"
              aria-label="Open Emma’s voice message"
              onClick={(event) => {
                event.stopPropagation();
                onOpenVoice();
              }}
            >
              <Play size={17} weight="fill" /> Listen
            </button>
          </>
        )}
      </div>
    </section>
  );
}

function CareCarousel({ index, onIndexChange, onSelect, activatingItem }) {
  const visible = [-2, -1, 0, 1, 2].map((offset) => {
    const itemIndex = (index + offset + CARE_ITEMS.length) % CARE_ITEMS.length;
    return { ...CARE_ITEMS[itemIndex], itemIndex, offset };
  });

  return (
    <section className={`care-carousel ${activatingItem ? "has-activating-card" : ""}`} aria-label="Care needs carousel" aria-busy={Boolean(activatingItem)} data-testid="care-carousel">
      <button type="button" className="carousel-arrow" aria-label="Previous care need" onClick={() => onIndexChange((index - 1 + CARE_ITEMS.length) % CARE_ITEMS.length)}>
        <CaretLeft size={28} weight="light" />
      </button>
      <div className="care-carousel__track">
        {visible.map(({ label, icon: Icon, itemIndex, offset }) => {
          const centered = offset === 0;
          const activating = centered && activatingItem?.key === label;
          const offsetClass = offset < 0 ? `n${Math.abs(offset)}` : offset;
          return (
            <DwellButton
              key={`${label}-${offset}`}
              className={`care-card care-card--offset-${offsetClass} ${centered ? "is-centered" : ""} ${activating ? "is-activating" : ""}`}
              ariaLabel={`${label}${centered ? ", hold your gaze and focus" : ", bring into focus"}`}
              testId={centered ? "center-care-card" : undefined}
              duration={centered ? 1100 : 650}
              disabled={Boolean(activatingItem)}
              onActivate={() => (centered ? onSelect(CARE_ITEMS[itemIndex]) : onIndexChange(itemIndex))}
            >
              <span className="care-card__icon"><Icon size={centered ? 66 : 44} weight="light" /></span>
              <strong>{label}</strong>
              {centered && <small>{activating ? "Opening request…" : "Hold your gaze and focus"}</small>}
            </DwellButton>
          );
        })}
      </div>
      <button type="button" className="carousel-arrow" aria-label="Next care need" onClick={() => onIndexChange((index + 1) % CARE_ITEMS.length)}>
        <CaretRight size={28} weight="light" />
      </button>
    </section>
  );
}

function FamilyCarousel({ activeIndex, onIndexChange, onSelect, activatingMessage }) {
  const visible = [-1, 0, 1].map((offset) => {
    const messageIndex = (activeIndex + offset + FAMILY_MESSAGES.length) % FAMILY_MESSAGES.length;
    return { message: FAMILY_MESSAGES[messageIndex], messageIndex, offset };
  });

  return (
    <section className={`family-carousel ${activatingMessage ? "has-activating-card" : ""}`} aria-label="Family messages" aria-busy={Boolean(activatingMessage)} data-testid="family-carousel">
      {visible.map(({ message, messageIndex, offset }) => {
        const centered = offset === 0;
        const activating = centered && activatingMessage?.key === message.sender;
        return (
          <DwellButton
            key={`${message.sender}-${offset}`}
            className={`family-message ${centered ? "is-centered" : ""} ${activating ? "is-activating" : ""}`}
            ariaLabel={`${message.sender}, ${message.type} message`}
            duration={centered ? 850 : 600}
            disabled={Boolean(activatingMessage)}
            onActivate={() => {
              if (!centered) return onIndexChange(messageIndex);
              onSelect(message);
            }}
          >
            <span className="family-message__avatar"><UserCircle size={centered ? 50 : 40} weight="light" /></span>
            <span className="family-message__copy"><small>{message.relation}</small><strong>{message.sender}</strong><span>{message.preview}</span></span>
            <span className="family-message__type">{message.type === "voice" ? <Waveform size={26} weight="light" /> : <Heart size={24} weight="light" />}</span>
          </DwellButton>
        );
      })}
    </section>
  );
}

function RequestDialog({ item, onBack, onSend }) {
  const Icon = item.icon;
  return (
    <section className="modal-card request-dialog" role="dialog" aria-modal="true" aria-labelledby="request-title">
      <span className="modal-card__icon"><Icon size={60} weight="light" /></span>
      <p className="eyebrow">CARE REQUEST</p>
      <h2 id="request-title">Send “{item.label}” to your care team?</h2>
      <p>Demo only. No request is sent to a real care team.</p>
      <div className="modal-actions">
        <DwellButton className="secondary-action" onActivate={onBack} duration={700} ariaLabel="Go back">Go back</DwellButton>
        <DwellButton className="primary-action" onActivate={onSend} duration={900} ariaLabel="Send request"><BellRinging size={22} weight="light" /> Send request</DwellButton>
      </div>
    </section>
  );
}

function VoiceMessage({ progress, playbackState, onTogglePlayback, onClose, onReact, reactionSent }) {
  const activePhrase = progress < 31 ? 0 : progress < 64 ? 1 : 2;
  const elapsed = Math.min(18, Math.round((progress / 100) * 18));
  return (
    <section className="modal-card voice-panel" role="dialog" aria-modal="true" aria-labelledby="voice-title" data-testid="voice-panel">
      <button type="button" className="close-button" onClick={onClose} aria-label="Close voice message"><X size={24} weight="light" /></button>
      <p className="eyebrow">FROM YOUR FAMILY</p>
      <div className="voice-panel__sender">
        <UserCircle size={48} weight="light" />
        <div><h2 id="voice-title">Emma · Wife</h2><p>Voice message · 0:18</p></div>
      </div>
      <div className="voice-player">
        <DwellButton className="voice-player__control" onActivate={onTogglePlayback} duration={800} ariaLabel={playbackState === "playing" ? "Pause voice message" : "Play voice message"} testId="voice-play-control">
          {playbackState === "playing" ? <Pause size={28} weight="fill" /> : <Play size={28} weight="fill" />}
        </DwellButton>
        <div className="voice-player__timeline">
          <div className="voice-player__label"><Waveform size={26} weight="light" /><span>00:{String(elapsed).padStart(2, "0")}</span><span>00:18</span></div>
          <div className="audio-progress" aria-label={`${Math.round(progress)} percent played`}><span style={{ width: `${progress}%` }} /></div>
        </div>
      </div>
      <div className="transcript" aria-label="Voice message transcript">
        <div className="transcript__heading"><SpeakerHigh size={20} weight="light" /> Live transcript</div>
        <p>{TRANSCRIPT.map((phrase, index) => <span key={phrase} className={index === activePhrase && progress > 0 ? "is-current" : ""}>{phrase} </span>)}</p>
      </div>
      <div className="reaction-row" aria-label="Respond with a reaction">
        {REACTIONS.map(({ label, icon: Icon }) => (
          <DwellButton key={label} className="reaction-button" onActivate={() => onReact(label)} duration={900} ariaLabel={`Send ${label} to Emma`}>
            <Icon size={26} weight="light" /><span>{label}</span>
          </DwellButton>
        ))}
      </div>
      <p className={`inline-success ${reactionSent ? "has-message" : ""}`} aria-live="polite">
        {reactionSent ? `${reactionSent} sent to Emma.` : "\u00A0"}
      </p>
    </section>
  );
}

function TextMessage({ message, onClose, onReact }) {
  return (
    <section className="modal-card text-panel" role="dialog" aria-modal="true" aria-labelledby="text-title">
      <button type="button" className="close-button" onClick={onClose} aria-label="Close message"><X size={24} weight="light" /></button>
      <p className="eyebrow">FROM YOUR FAMILY</p>
      <h2 id="text-title">{message.sender} · {message.relation}</h2>
      <blockquote>{message.preview}</blockquote>
      <p>Choose a simple response.</p>
      <div className="reaction-row">
        {REACTIONS.map(({ label, icon: Icon }) => (
          <DwellButton key={label} className="reaction-button" onActivate={() => onReact(label)} duration={900} ariaLabel={`Send ${label}`}>
            <Icon size={26} weight="light" /><span>{label}</span>
          </DwellButton>
        ))}
      </div>
    </section>
  );
}

export function App() {
  const inputMode = useInputMode();
  const eegState = useEEG();
  const resetVersion = useRef(null);
  const [now, setNow] = useState(() => new Date());
  const [expandedTop, setExpandedTop] = useState(null);
  const [menuActive, setMenuActive] = useState(false);
  const [activeTab, setActiveTab] = useState("care");
  const [careIndex, setCareIndex] = useState(2);
  const [familyIndex, setFamilyIndex] = useState(0);
  const [pendingRequest, setPendingRequest] = useState(null);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [textOpen, setTextOpen] = useState(null);
  const [playbackState, setPlaybackState] = useState("stopped");
  const [audioProgress, setAudioProgress] = useState(0);
  const [feedback, setFeedback] = useState("");
  const [reactionSent, setReactionSent] = useState("");
  const [selectionTransition, setSelectionTransition] = useState(null);
  const [backgroundImage, setBackgroundImage] = useState(null);
  const [backgroundMode, setBackgroundMode] = useState("icu");
  const [backgroundTransparent, setBackgroundTransparent] = useState(false);
  const [backgroundMenu, setBackgroundMenu] = useState(null);
  const [capturing, setCapturing] = useState(false);
  const [gaze, setGaze] = useState({ x: 960, y: 540, visible: false, still: false });
  const stillTimer = useRef(null);
  const feedbackTimer = useRef(null);
  const selectionTimer = useRef(null);
  const backgroundInput = useRef(null);
  const backgroundUrl = useRef(null);
  const stageRef = useRef(null);

  const timeLabel = useMemo(() => new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false }).format(now), [now]);
  const dateLabel = useMemo(() => new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" }).format(now), [now]);
  const hour = now.getHours();
  const daypart = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const DayIcon = hour < 17 ? Sun : hour < 20 ? SunHorizon : Moon;

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (playbackState !== "playing") return undefined;
    const timer = window.setInterval(() => {
      setAudioProgress((current) => {
        const next = current + 100 / 180;
        if (next >= 100) {
          window.clearInterval(timer);
          setPlaybackState("finished");
          return 100;
        }
        return next;
      });
    }, 100);
    return () => window.clearInterval(timer);
  }, [playbackState]);

  useEffect(() => () => {
    window.clearTimeout(stillTimer.current);
    window.clearTimeout(feedbackTimer.current);
    window.clearTimeout(selectionTimer.current);
    if (backgroundUrl.current) URL.revokeObjectURL(backgroundUrl.current);
    window.speechSynthesis?.cancel();
  }, []);

  const showFeedback = useCallback((message) => {
    window.clearTimeout(feedbackTimer.current);
    setFeedback(message);
    feedbackTimer.current = window.setTimeout(() => setFeedback(""), 2400);
  }, []);

  const handleBackgroundFile = useCallback((event) => {
    const [file] = event.target.files;
    if (!file) return;
    if (backgroundUrl.current) URL.revokeObjectURL(backgroundUrl.current);
    const nextUrl = URL.createObjectURL(file);
    backgroundUrl.current = nextUrl;
    setBackgroundImage(nextUrl);
    setBackgroundMode("custom");
    setBackgroundTransparent(false);
    setBackgroundMenu(null);
    showFeedback(`Background updated · ${file.name}`);
    event.target.value = "";
  }, [showFeedback]);

  const selectDefaultBackground = useCallback((mode) => {
    if (backgroundUrl.current) URL.revokeObjectURL(backgroundUrl.current);
    backgroundUrl.current = null;
    setBackgroundImage(null);
    setBackgroundMode(mode);
    setBackgroundTransparent(false);
    setBackgroundMenu(null);
    showFeedback(mode === "gradient" ? "Soft animated gradient enabled." : "Default ICU background restored.");
  }, [showFeedback]);

  const removeBackground = useCallback(() => {
    setBackgroundMode("transparent");
    setBackgroundTransparent(true);
    setBackgroundMenu(null);
    showFeedback("Background removed · PNG exports will contain UI only.");
  }, [showFeedback]);

  const returnHome = useCallback(() => {
    window.clearTimeout(selectionTimer.current);
    selectionTimer.current = null;
    window.speechSynthesis?.cancel();
    setExpandedTop(null);
    setMenuActive(false);
    setActiveTab("care");
    setCareIndex(2);
    setFamilyIndex(0);
    setPendingRequest(null);
    setVoiceOpen(false);
    setTextOpen(null);
    setPlaybackState("stopped");
    setAudioProgress(0);
    setReactionSent("");
    setSelectionTransition(null);
    setBackgroundMenu(null);
    showFeedback("Returned to home.");
  }, [showFeedback]);

  useEffect(() => {
    if (resetVersion.current !== null && resetVersion.current !== eegState.reset_seq) returnHome();
    resetVersion.current = eegState.reset_seq;
  }, [eegState.reset_seq, returnHome]);

  const exportScreenshot = useCallback(async () => {
    if (capturing || !stageRef.current) return;
    setCapturing(true);
    setBackgroundMenu(null);
    setGaze((current) => ({ ...current, visible: false, still: false }));

    try {
      await new Promise((resolve) => window.requestAnimationFrame(() => window.requestAnimationFrame(resolve)));
      await document.fonts.ready;
      const stage = stageRef.current;
      const transparent = backgroundTransparent;
      const dataUrl = await toPng(stage, {
        cacheBust: true,
        pixelRatio: 1,
        canvasWidth: stage.clientWidth,
        canvasHeight: stage.clientHeight,
        backgroundColor: transparent ? "rgba(0, 0, 0, 0)" : undefined,
        style: transparent ? { backgroundImage: "none", backgroundColor: "transparent" } : undefined,
        filter: (node) => {
          const classes = node.classList;
          if (!classes) return true;
          if (classes.contains("background-context-menu") || classes.contains("background-file-input") || classes.contains("gaze-halo") || classes.contains("feedback-toast")) return false;
          if (transparent && classes.contains("scene-vignette")) return false;
          return true;
        },
      });
      const link = document.createElement("a");
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
      link.download = `echomind-ar-${transparent ? "ui-transparent" : "screenshot"}-${timestamp}.png`;
      link.href = dataUrl;
      document.body.appendChild(link);
      link.click();
      link.remove();
      showFeedback(transparent ? "Transparent UI PNG exported." : "Screenshot PNG exported.");
    } catch (error) {
      console.error("Screenshot export failed", error);
      showFeedback("Screenshot export failed. Please try again.");
    } finally {
      setCapturing(false);
    }
  }, [backgroundTransparent, capturing, showFeedback]);

  const openBackgroundMenu = useCallback((event) => {
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    const menuWidth = 292;
    const menuHeight = 374;
    setBackgroundMenu({
      x: Math.max(16, Math.min(event.clientX - bounds.left, bounds.width - menuWidth - 16)),
      y: Math.max(16, Math.min(event.clientY - bounds.top, bounds.height - menuHeight - 16)),
    });
  }, []);

  const togglePlayback = useCallback(() => {
    if (playbackState === "playing") {
      window.speechSynthesis?.pause();
      setPlaybackState("paused");
      return;
    }
    if (playbackState === "paused") {
      window.speechSynthesis?.resume();
      setPlaybackState("playing");
      return;
    }
    setAudioProgress(0);
    setPlaybackState("playing");
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(TRANSCRIPT.join(" "));
      utterance.rate = 0.78;
      utterance.pitch = 1.03;
      utterance.volume = 0.82;
      utterance.onend = () => {
        setAudioProgress(100);
        setPlaybackState("finished");
      };
      window.speechSynthesis.speak(utterance);
    }
  }, [playbackState]);

  const closeVoice = useCallback(() => {
    window.speechSynthesis?.cancel();
    setVoiceOpen(false);
    setPlaybackState("stopped");
    setAudioProgress(0);
    setReactionSent("");
  }, []);

  const openVoice = useCallback(() => {
    setActiveTab("family");
    setTextOpen(null);
    setVoiceOpen(true);
    setExpandedTop(null);
  }, []);

  const activateInterface = useCallback(() => {
    setExpandedTop(null);
    setMenuActive(true);
  }, []);

  const beginSelectionTransition = useCallback((kind, key, onComplete) => {
    if (selectionTimer.current) return;
    setExpandedTop(null);
    setSelectionTransition({ kind, key });
    selectionTimer.current = window.setTimeout(() => {
      selectionTimer.current = null;
      setSelectionTransition(null);
      onComplete();
    }, 560);
  }, []);

  const selectCareItem = useCallback((item) => {
    beginSelectionTransition("care", item.label, () => setPendingRequest(item));
  }, [beginSelectionTransition]);

  const selectFamilyMessage = useCallback((message) => {
    beginSelectionTransition("family", message.sender, () => {
      if (message.type === "voice") openVoice();
      else setTextOpen(message);
    });
  }, [beginSelectionTransition, openVoice]);

  const sendReaction = useCallback((reaction) => {
    setReactionSent(reaction);
    showFeedback(`${reaction} sent to Emma.`);
  }, [showFeedback]);

  const handlePointerMove = (event) => {
    if (input.mode() !== 'mouse') return;
    const bounds = event.currentTarget.getBoundingClientRect();
    setGaze({ x: event.clientX - bounds.left, y: event.clientY - bounds.top, visible: true, still: false });
    window.clearTimeout(stillTimer.current);
    stillTimer.current = window.setTimeout(() => setGaze((current) => ({ ...current, still: true })), 800);
  };

  useEffect(() => {
    const onKeyDown = (event) => {
      const key = event.key.toLowerCase();
      if (key === "c") {
        setActiveTab("care");
        setMenuActive(true);
      }
      if (key === "f") {
        setActiveTab("family");
        setMenuActive(true);
      }
      if (key === "arrowleft") {
        event.preventDefault();
        if (activeTab === "care") setCareIndex((current) => (current - 1 + CARE_ITEMS.length) % CARE_ITEMS.length);
        else setFamilyIndex((current) => (current - 1 + FAMILY_MESSAGES.length) % FAMILY_MESSAGES.length);
      }
      if (key === "arrowright") {
        event.preventDefault();
        if (activeTab === "care") setCareIndex((current) => (current + 1) % CARE_ITEMS.length);
        else setFamilyIndex((current) => (current + 1) % FAMILY_MESSAGES.length);
      }
      if (key === "p" && voiceOpen) togglePlayback();
      if (key === "escape") {
        window.clearTimeout(selectionTimer.current);
        selectionTimer.current = null;
        setSelectionTransition(null);
        setBackgroundMenu(null);
        setPendingRequest(null);
        setTextOpen(null);
        if (voiceOpen) closeVoice();
        if (!pendingRequest && !voiceOpen && !textOpen) setMenuActive(false);
        setExpandedTop(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeTab, closeVoice, pendingRequest, textOpen, togglePlayback, voiceOpen]);

  return (
    <main
      ref={stageRef}
      className={`ar-stage ${inputMode === 'mouse' && gaze.still ? "is-gaze-still" : ""} ${menuActive ? "is-menu-active" : "is-relaxed"} ${voiceOpen ? "is-voice-open" : ""} ${backgroundMode === "gradient" ? "is-gradient-background" : ""} ${backgroundTransparent ? "is-background-transparent" : ""} ${capturing ? "is-capturing" : ""}`}
      onPointerMove={handlePointerMove}
      onPointerDown={() => setBackgroundMenu(null)}
      onContextMenu={openBackgroundMenu}
      data-testid="ar-stage"
      style={backgroundImage ? { backgroundImage: `url("${backgroundImage}")` } : undefined}
    >
      <DemoStatus />
      <div className="scene-vignette" aria-hidden="true" />
      <StatusCard type="daily" expanded={expandedTop === "daily"} onExpand={() => setExpandedTop("daily")} onCollapse={() => setExpandedTop((current) => current === "daily" ? null : current)} timeLabel={timeLabel} dateLabel={dateLabel} daypart={daypart} DayIcon={DayIcon} />
      <StatusCard type="message" expanded={expandedTop === "message"} onExpand={() => setExpandedTop("message")} onCollapse={() => { if (!voiceOpen) setExpandedTop((current) => current === "message" ? null : current); }} onOpenVoice={openVoice} timeLabel={timeLabel} dateLabel={dateLabel} daypart={daypart} DayIcon={DayIcon} />

      <div className="primary-experience" data-testid="primary-experience">
        {!pendingRequest && !voiceOpen && !textOpen && !menuActive && <ActivationPrompt onActivate={activateInterface} />}
        {!pendingRequest && !voiceOpen && !textOpen && menuActive && (
          <section className="active-interface" aria-label="Communication controls">
            {activeTab === "care" && <CareCarousel index={careIndex} onIndexChange={setCareIndex} onSelect={selectCareItem} activatingItem={selectionTransition?.kind === "care" ? selectionTransition : null} />}
            {activeTab === "family" && <FamilyCarousel activeIndex={familyIndex} onIndexChange={setFamilyIndex} onSelect={selectFamilyMessage} activatingMessage={selectionTransition?.kind === "family" ? selectionTransition : null} />}
            <nav className={`mode-switcher ${selectionTransition ? "is-transitioning" : ""}`} aria-label="Main modules">
              <button type="button" className={activeTab === "care" ? "is-active" : ""} aria-pressed={activeTab === "care"} onClick={() => setActiveTab("care")}><ArrowsVertical size={21} weight="light" /> Care</button>
              <button type="button" className={activeTab === "family" ? "is-active" : ""} aria-pressed={activeTab === "family"} onClick={() => setActiveTab("family")}><Heart size={21} weight="light" /> Family</button>
            </nav>
          </section>
        )}
        {pendingRequest && <RequestDialog item={pendingRequest} onBack={() => setPendingRequest(null)} onSend={() => { const requested = pendingRequest.label; setPendingRequest(null); showFeedback(`Demo confirmed · “${requested}” care request.`); }} />}
        {voiceOpen && <VoiceMessage progress={audioProgress} playbackState={playbackState} onTogglePlayback={togglePlayback} onClose={closeVoice} onReact={sendReaction} reactionSent={reactionSent} />}
        {textOpen && <TextMessage message={textOpen} onClose={() => setTextOpen(null)} onReact={sendReaction} />}
      </div>

      {feedback && !voiceOpen && <div className="feedback-toast" role="status" aria-live="polite" data-testid="feedback-toast"><span><Check size={22} weight="bold" /></span>{feedback}</div>}
      {backgroundMenu && (
        <div
          className="background-context-menu"
          role="menu"
          aria-label="Interface options"
          style={{ left: backgroundMenu.x, top: backgroundMenu.y }}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <button type="button" role="menuitem" className="context-menu__home" onClick={returnHome}>
            <House size={21} weight="light" />
            <span><strong>Back to Home</strong><small>Collapse all cards</small></span>
          </button>
          <button type="button" role="menuitem" className={backgroundMode === "icu" ? "is-active" : ""} aria-pressed={backgroundMode === "icu"} onClick={() => selectDefaultBackground("icu")}>
            <Bed size={21} weight="light" />
            <span><strong>ICU room</strong><small>Original default scene</small></span>
          </button>
          <button type="button" role="menuitem" className={backgroundMode === "gradient" ? "is-active" : ""} aria-pressed={backgroundMode === "gradient"} onClick={() => selectDefaultBackground("gradient")}>
            <CloudSun size={21} weight="light" />
            <span><strong>Soft gradient</strong><small>Slow blue-green motion</small></span>
          </button>
          <button type="button" role="menuitem" className={backgroundMode === "custom" ? "is-active" : ""} aria-pressed={backgroundMode === "custom"} onClick={() => backgroundInput.current?.click()}>
            <UploadSimple size={21} weight="light" />
            <span><strong>Custom image</strong><small>JPEG, PNG or WebP</small></span>
          </button>
          <button type="button" role="menuitem" className={backgroundTransparent ? "is-active" : ""} aria-pressed={backgroundTransparent} onClick={removeBackground} disabled={backgroundTransparent}>
            <EyeSlash size={21} weight="light" />
            <span><strong>Remove background</strong><small>Prepare transparent UI</small></span>
          </button>
          <button type="button" role="menuitem" onClick={exportScreenshot} disabled={capturing}>
            <Camera size={21} weight="light" />
            <span><strong>{capturing ? "Exporting…" : "Export screenshot"}</strong><small>{backgroundTransparent ? "Transparent PNG · UI only" : "PNG · current view"}</small></span>
          </button>
        </div>
      )}
      <input ref={backgroundInput} className="background-file-input" type="file" accept="image/jpeg,image/png,image/webp" onChange={handleBackgroundFile} tabIndex={-1} aria-hidden="true" />
      <div className={`gaze-halo ${inputMode === 'mouse' && gaze.visible ? "is-visible" : ""}`} aria-hidden="true" style={{ transform: `translate3d(${gaze.x}px, ${gaze.y}px, 0)` }}><span /></div>
      <div className="sr-only" aria-live="polite">{feedback}</div>
    </main>
  );
}
