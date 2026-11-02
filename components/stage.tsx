"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type Note = { s: string; j: string; n: string; d: number; t: number };
type Line = { text: string; start: number; notes: Note[] };
type Section = { id: string; name: string; en: string; start: number; lines: Line[] };
type Song = {
  title: string;
  subtitle: string;
  dedication: string;
  bpm: number;
  key: string;
  finalKey: string;
  meter: string;
  style: string;
  voice: string;
  duration: number;
  audio: string;
  vocal: string;
  bed: string;
  notes: string[];
  sections: Section[];
};

type Mode = "mix" | "vocal" | "bed";

const MODES: { id: Mode; label: string }[] = [
  { id: "mix", label: "成首" },
  { id: "vocal", label: "人聲" },
  { id: "bed", label: "伴奏" },
];

const PUNCT = new Set("，。、「」：；——…　 “”\"'()（）!！?？,.、 ");
const BASE = process.env.NEXT_PUBLIC_BASE_PATH || "";

function fmt(sec: number) {
  if (!Number.isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function toneOf(jp: string) {
  const m = jp.match(/([1-6])$/);
  return m ? m[1] : "";
}

function phrases(line: Line): Note[][] {
  const chunks = line.text.split(/　+/);
  const sizes = chunks.map((c) => [...c].filter((ch) => !PUNCT.has(ch) && ch.trim()).length);
  const groups: Note[][] = [];
  let i = 0;
  for (const n of sizes) {
    if (n > 0) groups.push(line.notes.slice(i, i + n));
    i += n;
  }
  if (i < line.notes.length) groups.push(line.notes.slice(i));
  return groups.filter((g) => g.length);
}

export function Stage() {
  const [song, setSong] = useState<Song | null>(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<Mode>("mix");
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [audioError, setAudioError] = useState("");
  const audioRef = useRef<HTMLAudioElement>(null);
  const pendingSeek = useRef<{ t: number; was: boolean } | null>(null);
  const activeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let gone = false;
    fetch(`${BASE}/song.json`)
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data: Song) => {
        if (!gone) setSong(data);
      })
      .catch(() => {
        if (!gone) setError("歌單載入唔到。刷新再試一次。");
      });
    return () => {
      gone = true;
    };
  }, []);

  const src = song
    ? mode === "vocal"
      ? `${BASE}/${song.vocal}`
      : mode === "bed"
        ? `${BASE}/${song.bed}`
        : `${BASE}/${song.audio}`
    : "";

  const flat = useMemo(() => {
    if (!song) return [];
    return song.sections.flatMap((sec) =>
      sec.lines.flatMap((line) => line.notes.map((n) => ({ ...n, lineStart: line.start, secId: sec.id }))),
    );
  }, [song]);

  const active = useMemo(() => {
    if (!song || !flat.length) return -1;
    const beat = 60 / song.bpm;
    for (let i = flat.length - 1; i >= 0; i--) {
      const n = flat[i];
      if (time + 0.03 >= n.t && time < n.t + n.d * beat - 0.01) return i;
    }
    return -1;
  }, [flat, song, time]);

  const indexByKey = useMemo(() => {
    const map = new Map<string, number>();
    flat.forEach((n, i) => map.set(`${n.t}-${n.s}`, i));
    return map;
  }, [flat]);

  const activeLineStart = active >= 0 ? flat[active].lineStart : -1;

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [active]);

  const toggle = useCallback(() => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) {
      a.play().catch(() => setAudioError("播唔到。再按一次播放。"));
    } else {
      a.pause();
    }
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "BUTTON") return;
      e.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  const switchMode = (next: Mode) => {
    if (next === mode) return;
    const a = audioRef.current;
    pendingSeek.current = { t: a?.currentTime ?? time, was: a ? !a.paused : false };
    setMode(next);
    setAudioError("");
  };

  useEffect(() => {
    const el = audioRef.current;
    const job = pendingSeek.current;
    if (!el || !job || !src) return;
    pendingSeek.current = null;
    const seek = () => {
      const dur = Number.isFinite(el.duration) ? el.duration : job.t;
      el.currentTime = Math.min(job.t, Math.max(0, dur - 0.05));
      if (job.was) el.play().catch(() => setAudioError("播唔到。再按一次播放。"));
    };
    const readyForThis = el.readyState >= 1 && el.currentSrc.includes(src.replace(/^\//, ""));
    if (readyForThis) seek();
    else el.addEventListener("loadedmetadata", seek, { once: true });
  }, [src]);

  const seekTo = (t: number) => {
    const a = audioRef.current;
    if (!a) return;
    const apply = () => {
      const dur = a.duration;
      const target = Number.isFinite(dur) && dur > 0.2 ? Math.min(t, Math.max(0, dur - 0.05)) : t;
      a.currentTime = target;
      setTime(target);
      if (a.paused) a.play().catch(() => setAudioError("播唔到。再按一次播放。"));
    };
    if (a.readyState >= 1) apply();
    else a.addEventListener("loadedmetadata", apply, { once: true });
  };

  const sectionNow = song
    ? [...song.sections].reverse().find((s) => time >= s.start - 0.05)?.name ?? song.sections[0]?.name
    : "";

  return (
    <main className="stage min-h-screen">
      <div className="mx-auto max-w-3xl px-5 pb-52 pt-12 sm:px-8 sm:pt-16">
        <p className="text-[0.72rem] tracking-[0.28em] text-[var(--faint)]">廣東話原創 · 01</p>
        <h1 className="serif mt-3 text-4xl font-semibold tracking-tight text-[var(--ink)] sm:text-5xl">
          濃煙裡的手
        </h1>
        <p className="mt-2 text-sm text-[var(--muted)]">Hand in the Smoke</p>
        <p className="serif mt-6 max-w-xl text-lg leading-relaxed text-[var(--ember-2)]">
          寫給每一位香港消防員，同埋喺屋企等佢哋返嚟嘅人。
        </p>
        <p className="mt-4 max-w-xl text-sm leading-7 text-[var(--muted)]">
          旋律跟住粵語聲調走：高平聲坐高音，低降聲坐低，上聲喺音頭帶一個短上升，然後先鎖實個音。
          歌詞一個字都冇改。人聲係曉曼把聲，用成句讀音唱返出嚟，唔再逐隻字孤立咁讀。
        </p>

        {song && (
          <dl className="mt-6 flex flex-wrap gap-2 text-xs text-[var(--muted)]">
            {[
              `${song.key} → ${song.finalKey}`,
              `${song.bpm} BPM`,
              song.meter,
              song.style,
              `人聲 · ${song.voice}`,
              fmt(song.duration),
            ].map((item) => (
              <dd key={item} className="rounded-full border border-[var(--line)] bg-[var(--paper)] px-3 py-1">
                {item}
              </dd>
            ))}
          </dl>
        )}

        <section className="fixed inset-x-0 bottom-0 z-30 border-t border-[var(--line)] bg-[var(--bg)]/95 px-4 py-3 shadow-[0_-16px_40px_rgba(0,0,0,0.35)] backdrop-blur-md sm:px-8">
          <div className="mx-auto max-w-3xl">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={toggle}
              disabled={!song}
              aria-label={playing ? "暫停" : "播放"}
              className="flex h-14 w-14 items-center justify-center rounded-full bg-[var(--ember)] text-[#2a160c] transition hover:bg-[var(--ember-2)] disabled:opacity-40"
            >
              {playing ? <PauseIcon /> : <PlayIcon />}
            </button>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-3">
                <p className="truncate text-sm text-[var(--ember-2)]">{sectionNow || "前奏"}</p>
                <p className="shrink-0 tabular-nums text-xs text-[var(--faint)]">
                  {fmt(time)} / {fmt(duration || song?.duration || 0)}
                </p>
              </div>
              <input
                className="mt-3"
                type="range"
                min={0}
                max={duration || song?.duration || 0}
                step={0.05}
                value={Math.min(time, duration || song?.duration || 0)}
                aria-label="播放進度"
                disabled={!song}
                onChange={(e) => seekTo(Number(e.target.value))}
              />
            </div>
          </div>
          <div className="mt-4 flex gap-1 rounded-full bg-black/25 p-1" role="group" aria-label="聲軌">
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                aria-pressed={mode === m.id}
                onClick={() => switchMode(m.id)}
                className={`flex-1 rounded-full px-3 py-1.5 text-sm transition ${
                  mode === m.id
                    ? "bg-[var(--ember)] text-[#2a160c]"
                    : "text-[var(--muted)] hover:text-[var(--ink)]"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
          {audioError && <p className="mt-3 text-sm text-[#e7b2a0]">{audioError}</p>}
          </div>
        </section>

        {error && <p className="mt-8 text-sm text-[#e7b2a0]">{error}</p>}
        {!song && !error && <p className="mt-8 text-sm text-[var(--muted)]">載入緊歌詞同聲軌…</p>}

        {song && (
          <article className="mt-10 space-y-10">
            {song.sections.map((sec) => (
              <section key={sec.id} aria-label={sec.name}>
                <header className="mb-3">
                  <button
                    type="button"
                    onClick={() => seekTo(sec.start)}
                    aria-label={`跳去${sec.name} ${fmt(sec.start)}`}
                    className="flex w-full items-baseline justify-between gap-3 text-left"
                  >
                    <span className="text-sm tracking-[0.18em] text-[var(--ember)]">{sec.name}</span>
                    <span className="text-xs tabular-nums text-[var(--faint)]">
                      {sec.en} · {fmt(sec.start)}
                    </span>
                  </button>
                </header>
                {sec.lines.length === 0 ? (
                  <p className="text-sm text-[var(--faint)]">鋼琴四小節，未開口。</p>
                ) : (
                  <div className="space-y-4">
                    {sec.lines.map((line) => {
                      const on = line.start === activeLineStart;
                      return (
                        <div key={line.start} className={on ? "" : "opacity-70"}>
                          <div className="flex flex-wrap gap-x-3 gap-y-1">
                            {phrases(line).map((group, gi) => (
                              <span key={gi} className="inline-flex flex-wrap">
                                {group.map((note) => {
                                  const idx = indexByKey.get(`${note.t}-${note.s}`) ?? -1;
                                  const isOn = idx === active;
                                  return (
                                    <button
                                      key={`${note.t}-${note.s}`}
                                      type="button"
                                      ref={isOn ? activeRef : undefined}
                                      className={`syl ${on ? "line-on" : ""} ${isOn ? "on" : ""}`}
                                      onClick={() => seekTo(note.t)}
                                      aria-current={isOn ? "true" : undefined}
                                      aria-label={`${note.s} ${note.j}`}
                                    >
                                      <i className="jp">
                                        {note.j.replace(/[1-6]$/, "")}
                                        <span className="text-[var(--ember)]">{toneOf(note.j)}</span>
                                      </i>
                                      <span className="serif ch">{note.s}</span>
                                    </button>
                                  );
                                })}
                              </span>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            ))}
          </article>
        )}

        {song && (
          <section className="mt-14 border-t border-[var(--line)] pt-8">
            <h2 className="text-sm tracking-[0.18em] text-[var(--ember)]">點解咁唱</h2>
            <ul className="mt-4 space-y-3 text-sm leading-7 text-[var(--muted)]">
              <li>成句交俾粵語語音讀，再切開每個音節。屋企、媽媽、着鞋、咗、哋都跟住個詞嘅讀音，唔會讀成孤立字。</li>
              <li>唱腔保留把聲嘅共振峰，只係將音高搬去譜上。長音先加顫音，聲調嘅升降留喺音頭幾十毫秒。</li>
              <li>副歌唔再將「路」「返」「伸手」放喺同聲調相反嘅音高。聽得清，先至聽得見句承諾。</li>
            </ul>
            <h2 className="mt-10 text-sm tracking-[0.18em] text-[var(--ember)]">創作筆記</h2>
            <ul className="mt-4 space-y-3 text-sm leading-7 text-[var(--muted)]">
              {song.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {src && (
        <audio
          ref={audioRef}
          src={src}
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
          onDurationChange={(e) => setDuration(e.currentTarget.duration)}
          onError={() => setAudioError("音檔載入唔到。檢查網絡之後再試。")}
        />
      )}
    </main>
  );
}

function PlayIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M8 5.5v13l11-6.5-11-6.5z" fill="currentColor" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 5h4v14H6V5zm8 0h4v14h-4V5z" fill="currentColor" />
    </svg>
  );
}
