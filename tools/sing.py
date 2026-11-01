#!/usr/bin/env python3
"""Sing 《濃煙裡的手》.

The old demo froze each character's vowel into a spectral envelope and drove
it with a sine stack, so it buzzed like a vocoder and sang polyphonic words
with no context (屋企, 着, 媽媽, 咗).

This version:
1. Speaks each lyric line with zh-HK-HiuMaanNeural so the reading is the
   word in context, and slices it on word boundaries.
2. TD-PSOLA retunes the real voice onto the melody (formants stay put).
3. Puts a short lexical-tone scoop on the attack, then locks the note.
4. Lays a piano / pad / bass / brush bed under it.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys

import numpy as np
from scipy import signal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from songs.score import SONG  # noqa: E402

CACHE = os.path.join(ROOT, "tools", ".vox-cache")
SR = 24000
VOICE_RATE = "-8%"
SKIP = set("，。、「」：；——…　 “”\"'()（）!！?？,.、 ")

NOTE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
OBSTRUENT = set(list("bpdtgkzc") + ["gw", "kw"])
RACK = {
    "intro": dict(piano=0.85, pad=0.12, bass=0.22, kick=0.0, brush=0.0, hat=0.0),
    "verse": dict(piano=0.72, pad=0.06, bass=0.42, kick=0.0, brush=0.0, hat=0.0),
    "verse2": dict(piano=0.74, pad=0.16, bass=0.48, kick=0.0, brush=0.35, hat=0.08),
    "pre": dict(piano=0.78, pad=0.38, bass=0.58, kick=0.40, brush=0.48, hat=0.16),
    "chorus": dict(piano=0.82, pad=0.55, bass=0.70, kick=0.78, brush=0.55, hat=0.22),
    "bridge": dict(piano=0.62, pad=0.18, bass=0.12, kick=0.0, brush=0.0, hat=0.0),
    "final": dict(piano=0.90, pad=0.68, bass=0.78, kick=0.88, brush=0.58, hat=0.28),
    "outro": dict(piano=0.60, pad=0.22, bass=0.32, kick=0.0, brush=0.18, hat=0.0),
}
VOCAL_GAIN = {
    "verse": 0.94, "verse2": 0.96, "pre": 1.0, "chorus": 1.06,
    "bridge": 0.80, "final": 1.12, "outro": 0.88, "intro": 1.0,
}


def tts_text(display):
    t = display.replace("　", "，").strip()
    if not t.endswith(("。", "！", "？", "」")):
        t += "。"
    return t


def lyric_chars(text):
    return [c for c in text if c not in SKIP and not c.isspace()]


def midi_of(sci):
    m = re.match(r"^([A-G])([#b]?)(-?\d)$", sci)
    acc = 1 if m.group(2) == "#" else -1 if m.group(2) == "b" else 0
    return (int(m.group(3)) + 1) * 12 + NOTE_PC[m.group(1)] + acc


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def parse_chord(sym):
    minor = sym.endswith("m")
    body = sym[:-1] if minor else sym
    m = re.match(r"^([A-G])([#b]?)$", body)
    acc = 1 if m.group(2) == "#" else -1 if m.group(2) == "b" else 0
    root = NOTE_PC[m.group(1)] + acc + 60
    third = 3 if minor else 4
    return [root, root + third, root + 7]


def tone_of(jp):
    m = re.search(r"([1-6])$", jp)
    return int(m.group(1)) if m else 3


def initial_of(jp):
    base = re.sub(r"[1-6]$", "", jp)
    for ini in ("gw", "kw", "ng"):
        if base.startswith(ini) and len(base) > len(ini):
            return ini
    if base and base[0] in "bpmfdtnlgkhwzcsj" and not (base[0] in "aeiouy"):
        # bare vowel syllables: aa, o, ... and 'm'
        if base[0] in "aeiou":
            return ""
        return base[0]
    return ""


def is_sonorant(jp):
    ini = initial_of(jp)
    return ini in ("", "m", "n", "ng", "l", "w", "j")


def is_checked(jp):
    base = re.sub(r"[1-6]$", "", jp)
    return base.endswith(("p", "t", "k")) and not base.endswith("ng")


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------
def cache_key(text, voice):
    h = hashlib.sha1((voice + "|" + VOICE_RATE + "|" + text).encode()).hexdigest()[:16]
    return h


async def _fetch(text, voice):
    import edge_tts
    last = None
    for attempt in range(4):
        try:
            comm = edge_tts.Communicate(text, voice, rate=VOICE_RATE, boundary="WordBoundary")
            audio = bytearray()
            words = []
            async for ch in comm.stream():
                if ch["type"] == "audio":
                    audio += ch["data"]
                elif ch["type"] == "WordBoundary":
                    words.append({
                        "t": ch["text"],
                        "o": ch["offset"] / 1e7,
                        "d": ch["duration"] / 1e7,
                    })
            if len(audio) < 400 or not words:
                raise RuntimeError("empty tts")
            return bytes(audio), words
        except Exception as exc:
            last = exc
            await asyncio.sleep(0.8 * (attempt + 1))
    raise RuntimeError("TTS failed for %r: %s" % (text, last))


async def ensure_tts(text, voice):
    os.makedirs(CACHE, exist_ok=True)
    key = cache_key(text, voice)
    mp3 = os.path.join(CACHE, key + ".mp3")
    meta = os.path.join(CACHE, key + ".json")
    if os.path.exists(mp3) and os.path.exists(meta) and os.path.getsize(mp3) > 400:
        return mp3, meta
    audio, words = await _fetch(text, voice)
    with open(mp3, "wb") as f:
        f.write(audio)
    with open(meta, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False)
    return mp3, meta


async def ensure_all(texts, voice):
    sem = asyncio.Semaphore(3)

    async def one(text):
        async with sem:
            await ensure_tts(text, voice)

    await asyncio.gather(*[one(t) for t in dict.fromkeys(texts)])


def decode_mp3(path):
    wav = path[:-4] + ".wav"
    if not os.path.exists(wav) or os.path.getmtime(wav) < os.path.getmtime(path):
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", str(SR), wav],
            check=True,
        )
    import soundfile as sf
    x, sr = sf.read(wav, dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != SR:
        raise RuntimeError("bad sr")
    return x


def load_line_audio(text, voice):
    key = cache_key(text, voice)
    mp3 = os.path.join(CACHE, key + ".mp3")
    meta = os.path.join(CACHE, key + ".json")
    audio = decode_mp3(mp3)
    words = json.load(open(meta, encoding="utf-8"))
    return audio, words


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------
def trim(x, sr, thresh=0.012, pad=0.012):
    if len(x) < 8:
        return x
    idx = np.flatnonzero(np.abs(x) > thresh)
    if len(idx) == 0:
        return x
    a = max(0, int(idx[0] - pad * sr))
    b = min(len(x), int(idx[-1] + pad * sr))
    return np.ascontiguousarray(x[a:b])


def split_counts(e, k):
    """Split a smoothed energy envelope into k syllable spans (frame indices)."""
    m = len(e)
    if k <= 1 or m < k * 2:
        return [0, m]
    min_f = max(2, int(m / (k * 3.2)))
    if k == 2:
        # Cantonese syllables inside one word are similar in length.
        # Search near the midpoint so a quiet initial doesn't steal the vowel.
        lo = max(min_f, int(m * 0.32))
        hi = min(m - min_f, int(m * 0.68))
        if hi <= lo:
            return [0, m // 2, m]
        idx = np.arange(lo, hi)
        score = e[lo:hi] / (float(np.mean(e)) + 1e-6) + 1.8 * np.abs(idx / m - 0.5)
        cut = int(idx[int(np.argmin(score))])
        return [0, cut, m]
    # DP for 3+ syllables inside one word
    target = m / k
    mean_e = float(np.mean(e)) + 1e-6
    INF = 1e18
    dp = np.full((m + 1, k + 1), INF)
    prv = np.full((m + 1, k + 1), -1, dtype=np.int32)
    dp[0, 0] = 0.0
    for s in range(1, k + 1):
        for i in range(s * min_f, m + 1):
            j0 = (s - 1) * min_f
            j1 = i - min_f
            best, arg = INF, -1
            for j in range(j0, j1 + 1):
                cut = 0.0 if j == 0 else float(e[min(j, m - 1)])
                pen = 0.85 * abs((i - j) - target) * mean_e
                sc = dp[j, s - 1] + cut + pen
                if sc < best:
                    best, arg = sc, j
            dp[i, s] = best
            prv[i, s] = arg
    if dp[m, k] >= INF / 2:
        return [int(round(i * m / k)) for i in range(k + 1)]
    pts = [m]
    i, s = m, k
    while s:
        j = int(prv[i, s])
        if j < 0:
            return [int(round(t * m / k)) for t in range(k + 1)]
        pts.append(j)
        i, s = j, s - 1
    pts.reverse()
    return pts


def syllables_from_line(audio, words, chars, sr):
    flat = "".join(w["t"] for w in words)
    want = "".join(chars)
    if flat != want:
        return None
    hop = int(0.005 * sr)
    pieces = []
    for w in words:
        a = max(0, int(w["o"] * sr))
        b = min(len(audio), int((w["o"] + w["d"]) * sr))
        # keep a hair of the gap when there is one, so bursts aren't clipped
        seg = audio[a:b]
        k = len(w["t"])
        if k == 1 or len(seg) < hop * (k + 2):
            pieces.append(trim(seg, sr))
            continue
        n = len(seg) // hop
        env = np.array([
            np.sqrt(np.mean(seg[i * hop:(i + 1) * hop] ** 2) + 1e-12) for i in range(n)
        ])
        env = np.convolve(env, np.ones(3) / 3.0, mode="same")
        pts = split_counts(env, k)
        for i in range(k):
            s0 = pts[i] * hop
            s1 = pts[i + 1] * hop if i < k - 1 else len(seg)
            pieces.append(trim(seg[s0:s1], sr))
    if len(pieces) != len(chars):
        return None
    return pieces


def yin_f0(x, sr, fmin=70.0, fmax=520.0):
    """Frame autocorrelation. Short Cantonese vowels fail a strict YIN gate
    even when the lag peak is obvious, so this follows that peak."""
    hop = int(0.007 * sr)
    win = int(0.028 * sr)
    if len(x) < win // 2:
        return np.zeros(1), hop
    nframes = max(1, 1 + (len(x) - win // 2) // hop)
    f0 = np.zeros(nframes)
    x64 = np.asarray(x, dtype=np.float64)
    tau_min = max(2, int(sr / fmax))
    tau_max = int(sr / fmin)
    for i in range(nframes):
        fr = x64[i * hop:i * hop + win]
        if len(fr) < win // 2:
            break
        if np.sqrt(np.mean(fr * fr)) < 0.006:
            continue
        fr = fr - np.mean(fr)
        nfft = 1 << (2 * len(fr) - 1).bit_length()
        ac = np.fft.irfft(np.abs(np.fft.rfft(fr, nfft)) ** 2)[:len(fr)]
        hi = min(tau_max, len(ac) - 2)
        if hi <= tau_min + 2 or ac[0] <= 0:
            continue
        k = tau_min + int(np.argmax(ac[tau_min:hi]))
        conf = ac[k] / ac[0]
        if conf < 0.42:
            continue
        a, b, c = ac[k - 1], ac[k], ac[k + 1]
        den = a - 2 * b + c
        if den != 0:
            k = k + float(np.clip(0.5 * (a - c) / den, -0.6, 0.6))
        if k > 1:
            f0[i] = sr / k
    last = 0.0
    for i in range(len(f0)):
        if f0[i] <= 0:
            last = 0.0
            continue
        if last > 0 and (f0[i] > last * 1.65 or f0[i] < last / 1.65):
            cands = [c for c in (f0[i], f0[i] / 2, f0[i] * 2) if fmin * 0.75 < c < fmax * 1.2]
            if cands:
                f0[i] = min(cands, key=lambda c: abs(np.log(c / last)))
        last = f0[i] if f0[i] > 0 else last
    return f0, hop


def pitch_marks(x, f0, hop, sr):
    if len(x) < 32 or not np.any(f0 > 0):
        return []
    b, a = signal.butter(3, 380 / (sr / 2), btype="low")
    y = signal.filtfilt(b, a, x).astype(np.float64)
    v0 = int(np.flatnonzero(f0 > 0)[0])
    t = v0 * hop
    # lock polarity to the stronger peak in the first voiced period
    f = f0[v0] if f0[v0] > 60 else 180.0
    P0 = int(sr / f)
    w0 = y[t:t + max(8, P0)]
    polarity = 1 if (len(w0) and np.max(w0) >= -np.min(w0)) else -1
    marks = []
    last_f = None
    n = len(x)
    guard = 0
    while t < n - 8 and guard < n:
        guard += 1
        frame = min(len(f0) - 1, t // hop)
        f = f0[frame]
        if f < 65:
            t += hop
            last_f = None
            continue
        if last_f and (f > last_f * 1.55 or f < last_f / 1.55):
            f = last_f
        P = max(16, int(round(sr / f)))
        a0 = max(0, t - int(0.35 * P))
        b0 = min(n, t + int(0.45 * P))
        local = polarity * y[a0:b0]
        if len(local) < 4:
            break
        mark = a0 + int(np.argmax(local))
        if marks and mark <= marks[-1] + 4:
            mark = marks[-1] + P
        if mark >= n - 2:
            break
        marks.append(int(mark))
        last_f = f
        t = mark + max(16, int(round(sr / f)))
    return marks


# ---------------------------------------------------------------------------
# TD-PSOLA note
# ---------------------------------------------------------------------------
def tone_curve(n, sr, target, prev, tone, dur):
    t = np.arange(n) / sr
    gesture = np.ones(n)
    # cents of offset that resolves to the written note
    if tone == 1:
        cents = 35 * np.exp(-t / 0.055)
    elif tone == 2:
        cents = -190 * np.clip(1 - t / 0.145, 0, 1) ** 1.15
    elif tone == 4:
        cents = 150 * np.clip(1 - t / 0.11, 0, 1) ** 1.15
    elif tone == 5:
        cents = -120 * np.clip(1 - t / 0.16, 0, 1) ** 1.2
    elif tone == 6:
        cents = -25 * np.exp(-t / 0.07)
    else:
        cents = np.zeros(n)
    intended = target * (2 ** (cents / 1200.0))
    if prev and prev > 0:
        g = np.clip(t / 0.06, 0, 1)
        g = g * g * (3 - 2 * g)
        f = np.exp((1 - g) * np.log(prev) + g * np.log(np.maximum(intended, 40)))
    else:
        # small scoop into the first note of a phrase
        scoop = 2 ** ((-40 * np.exp(-t / 0.05)) / 1200.0)
        f = intended * scoop
    if dur >= 0.85:
        depth = 0.016 if dur < 1.6 else 0.022  # ~28–38 cents
        vib = np.clip((t - 0.30) / 0.22, 0, 1)
        vib = vib * vib
        f = f * (1 + depth * vib * np.sin(2 * np.pi * 5.35 * t))
    # slow bounded wobble, a few cents, so a held note isn't a comb
    wob = np.random.randn(n)
    wob = signal.lfilter([0.0008], [1.0, -0.9992], wob)
    wob /= np.max(np.abs(wob)) + 1e-9
    f = f * (1 + 0.0035 * wob)
    return np.clip(f, 70, 900)


def psola_vowel(x, sr, f_inst):
    """Place source pitch marks at the target period.

    The window is two *synthesis* periods long, so a note sung below the
    spoken pitch still overlaps instead of dropping to zero every cycle.
    """
    f0, hop = yin_f0(x, sr)
    marks = pitch_marks(x, f0, hop, sr)
    n_out = len(f_inst)
    if len(marks) < 4:
        return None
    gcount = len(marks)
    x64 = np.asarray(x, dtype=np.float64)
    y = np.zeros(n_out, dtype=np.float64)
    wsum = np.zeros(n_out, dtype=np.float64)
    # Sustain the loudest part of the vowel, not the stop closure at the end
    # of a checked syllable (呎, 一, 屋).
    rms_m = np.array([
        np.sqrt(np.mean(x64[max(0, m - 80):min(len(x64), m + 80)] ** 2) + 1e-12)
        for m in marks
    ])
    peak_i = int(np.argmax(rms_m))
    thr = 0.5 * float(rms_m[peak_i])
    g0 = peak_i
    while g0 > 0 and rms_m[g0 - 1] >= thr and peak_i - (g0 - 1) <= 4:
        g0 -= 1
    g1 = peak_i
    while g1 < gcount - 1 and rms_m[g1 + 1] >= thr and (g1 + 1) - peak_i <= 4:
        g1 += 1
    if g1 <= g0:
        g1 = min(gcount - 1, g0 + 1)
    span = max(1, g1 - g0)
    attack_t = min(0.12, n_out / sr * 0.4)
    g_attack = max(1, peak_i)
    pos = 0
    while pos < n_out - 4:
        f = float(f_inst[min(pos, n_out - 1)])
        step = max(18, int(round(sr / max(f, 70))))
        half = step * 2  # four synthesis periods, 75% overlap, less buzzy
        tt = pos / sr
        if tt < attack_t:
            gi = int((tt / max(attack_t, 1e-4)) * (g_attack - 1))
        else:
            phase = ((tt - attack_t) / 0.16) % 2.0
            if phase > 1.0:
                phase = 2.0 - phase
            gi = g0 + int(phase * (span - 1))
        gi = int(np.clip(gi, 0, gcount - 1))
        center = marks[gi]
        a = center - half
        b = center + half
        win = np.hanning(b - a)
        seg = np.zeros(b - a, dtype=np.float64)
        src_a = max(0, a)
        src_b = min(len(x64), b)
        if src_b > src_a:
            seg[src_a - a:src_a - a + (src_b - src_a)] = x64[src_a:src_b]
        seg *= win
        dst_a = pos - half
        dst_b = dst_a + len(seg)
        lo = max(0, dst_a)
        hi = min(n_out, dst_b)
        if hi > lo:
            sl = lo - dst_a
            y[lo:hi] += seg[sl:sl + (hi - lo)]
            wsum[lo:hi] += win[sl:sl + (hi - lo)]
        pos += step
    voiced = wsum > 0.2
    y[voiced] /= wsum[voiced]
    # fill tiny holes by interpolating rather than hard zeros
    if np.any(~voiced):
        idx = np.arange(n_out)
        good = np.flatnonzero(voiced)
        if len(good) > 4:
            y[~voiced] = np.interp(idx[~voiced], good, y[good])
            hole = ~voiced
            y[hole] *= 0.15
    return y.astype(np.float32)


def render_note(src, sr, target_hz, dur, prev_hz, jp, legato_next, gain):
    src = np.asarray(src, dtype=np.float32)
    if len(src) < int(0.03 * sr):
        src = np.pad(src, (0, int(0.03 * sr)))
    f0, hop = yin_f0(src, sr)
    voiced = np.flatnonzero(f0 > 0)
    if len(voiced):
        v0 = int(voiced[0] * hop)
        # include a few ms before voicing so a voiced nasal isn't chopped,
        # but keep a clear unvoiced burst when there is one
        v0 = max(0, v0)
    else:
        v0 = 0
    raw_head = src[:v0]
    if len(raw_head) > int(0.12 * sr):
        raw_head = raw_head[-int(0.12 * sr):]
    vowel = src[v0:]
    n_out = max(int(dur * sr), int(0.06 * sr))
    tone = tone_of(jp)
    f_inst = tone_curve(n_out, sr, target_hz, prev_hz if prev_hz else 0, tone, dur)
    body = psola_vowel(vowel if len(vowel) > int(0.04 * sr) else src, sr, f_inst)
    if body is None:
        # last resort: loop the source under the new duration
        reps = int(np.ceil(n_out / max(1, len(src))))
        body = np.tile(src, reps)[:n_out]
    else:
        body = body[:n_out]
        if len(body) < n_out:
            body = np.pad(body, (0, n_out - len(body)))

    # consonant lead, then vowel on the beat
    head = raw_head.astype(np.float32)
    if len(head):
        hr = np.sqrt(np.mean(head ** 2)) + 1e-9
        vr = np.sqrt(np.mean(body ** 2)) + 1e-9
        if hr > vr * 1.35:
            head *= (vr * 1.15) / hr
        # don't sing the speech pitch of an unvoiced burst; just duck the edge
        fade = min(len(head), int(0.008 * sr))
        if fade:
            head[:fade] *= np.linspace(0, 1, fade)
            head[-fade:] *= np.linspace(1, 0.4, fade)

    # musical envelope on the vowel. Sonorant legato keeps a shorter release
    # because the next note will cover the join.
    env = np.ones(n_out, dtype=np.float32)
    atk = min(n_out // 4, int(0.012 * sr))
    rel = int((0.045 if legato_next else min(0.16, max(0.06, dur * 0.22))) * sr)
    rel = min(rel, n_out // 2)
    if atk:
        env[:atk] = np.linspace(0, 1, atk)
    if rel:
        env[-rel:] *= np.linspace(1, 0, rel) ** (1.15 if legato_next else 1.5)
    # gentle swell on long notes
    if dur > 0.7:
        env *= 0.92 + 0.08 * np.sin(np.pi * np.clip(np.arange(n_out) / n_out, 0, 1))
    body *= env * gain

    # a little aspiration, more on higher notes, following the envelope
    rng = np.random.default_rng(int(target_hz * 10) + n_out)
    noise = rng.standard_normal(n_out).astype(np.float32)
    noise = signal.lfilter([0.15], [1, -0.85], noise)
    air = 0.012 + 0.018 * np.clip((target_hz - 260) / 220, 0, 1)
    body += noise * env * air * gain

    rms = np.sqrt(np.mean(body ** 2)) + 1e-9
    body *= min(0.22 / rms, 3.0)
    return head, body


def measure_cents(body, sr, target):
    if len(body) < int(0.08 * sr):
        return None
    a = len(body) // 5
    b = max(a + 8, len(body) * 3 // 5)
    f0, _ = yin_f0(body[a:b], sr, fmin=80, fmax=800)
    v = f0[f0 > 0]
    if len(v) < 3:
        return None
    med = float(np.median(v))
    return 1200 * np.log2(med / target), med


# ---------------------------------------------------------------------------
# bed
# ---------------------------------------------------------------------------
def piano_note(freq, n, sr, vel, rng):
    t = np.arange(n) / sr
    y = np.zeros(n, dtype=np.float64)
    B = 0.00032
    for k in range(1, 13):
        fk = freq * k * np.sqrt(1.0 + B * k * k)
        if fk >= sr / 2 - 80:
            break
        decay = np.exp(-t * (1.05 + 0.42 * k) / (0.55 + 0.9 * vel))
        y += (vel / (k ** 1.2)) * np.sin(2 * np.pi * fk * t + rng.uniform(0, 0.4)) * decay
    hn = min(n, int(0.015 * sr))
    ht = np.arange(hn) / sr
    y[:hn] += rng.standard_normal(hn) * np.exp(-ht / 0.0025) * 0.05 * vel
    y *= np.minimum(1.0, t / 0.004)
    peak = np.max(np.abs(y)) + 1e-9
    return (y / peak).astype(np.float32) * (0.18 * vel)


def add_at(buf, start, sig):
    if start >= len(buf) or len(sig) == 0:
        return
    if start < 0:
        sig = sig[-start:]
        start = 0
    end = min(len(buf), start + len(sig))
    buf[start:end] += sig[:end - start]


def render_bed(chords, sr, total, bpm):
    """chords: list of {beat, bars, sym, style}"""
    spb = 60.0 / bpm
    piano = np.zeros(total, dtype=np.float32)
    pad = np.zeros(total, dtype=np.float32)
    bass = np.zeros(total, dtype=np.float32)
    drums = np.zeros(total, dtype=np.float32)
    rng = np.random.default_rng(11)
    for ch in chords:
        rack = RACK[ch["style"]]
        tri = parse_chord(ch["sym"])
        dur_s = ch["bars"] * 4 * spb
        s0 = int(ch["beat"] * spb * sr)
        n = int(dur_s * sr) + int(0.8 * sr)
        # pad: slow strings, detuned
        if rack["pad"] > 0 and s0 < total:
            tt = np.arange(min(n, total - s0)) / sr
            env = np.minimum(1, tt / 0.45) * np.minimum(1, (tt[::-1] if False else np.clip((len(tt) / sr - tt) / 0.5, 0, 1)))
            # simpler release
            env = np.minimum(1, tt / 0.5)
            env *= np.clip((len(tt) / sr - tt) / 0.55, 0, 1)
            tone = np.zeros(len(tt), dtype=np.float64)
            for m in tri:
                f = hz(m)
                for det in (-7, 0, 7):
                    fd = f * (2 ** (det / 1200))
                    for k, amp in ((1, 1.0), (2, 0.35), (3, 0.16), (4, 0.07)):
                        tone += amp * np.sin(2 * np.pi * fd * k * tt)
            tone /= (np.max(np.abs(tone)) + 1e-9)
            pad[s0:s0 + len(tt)] += (tone * env * 0.09 * rack["pad"]).astype(np.float32)
        # bass
        if rack["bass"] > 0:
            bn = int(min(dur_s, 1.6) * sr)
            tb = np.arange(bn) / sr
            fb = hz(tri[0] - 12)
            wave = np.sin(2 * np.pi * fb * tb) + 0.35 * np.sin(2 * np.pi * fb * 0.5 * tb)
            wave *= np.exp(-tb / (dur_s * 0.85)) * np.minimum(1, tb / 0.02)
            add_at(bass, s0, (wave * 0.22 * rack["bass"]).astype(np.float32))
            # pickup on beat 3 for chorus-like styles
            if rack["kick"] > 0:
                s3 = s0 + int(2 * spb * sr)
                add_at(bass, s3, (wave[: int(0.7 * sr)] * 0.55).astype(np.float32))
        # piano: block on the downbeat, sparse arpeggio after
        if rack["piano"] > 0:
            vel = 0.55 + 0.35 * rack["piano"]
            # left + right together on beat 1, held
            held = int(min(dur_s * 0.92, 2.4) * sr)
            for m in (tri[0] - 12, tri[0], tri[1], tri[2]):
                add_at(piano, s0, piano_note(hz(m), held, sr, vel * (0.7 if m < tri[0] else 1.0), rng))
            steps = int(ch["bars"] * 4 / 0.5)
            if ch["style"] in ("bridge", "intro", "verse", "outro"):
                pattern = [0, 2, 4]  # fewer
            else:
                pattern = list(range(steps))
            arp = [tri[0] + 12, tri[1] + 12, tri[2] + 12, tri[1] + 12]
            for k in pattern:
                if k == 0:
                    continue
                if ch["style"] in ("verse", "outro", "bridge") and k % 2:
                    continue
                a0 = s0 + int(k * 0.5 * spb * sr)
                note = piano_note(hz(arp[k % len(arp)]), int(0.55 * sr), sr, vel * 0.55, rng)
                add_at(piano, a0, note)
        # drums
        beats = int(ch["bars"] * 4)
        for b in range(beats):
            t0 = s0 + int(b * spb * sr)
            if rack["kick"] > 0 and b % 2 == 0:
                nn = int(0.22 * sr)
                kt = np.arange(nn) / sr
                fr = 140 * np.exp(-kt / 0.045) + 48
                kick = np.sin(2 * np.pi * np.cumsum(fr) / sr) * np.exp(-kt / 0.12)
                add_at(drums, t0, (kick * 0.34 * rack["kick"]).astype(np.float32))
            if rack["brush"] > 0 and b % 2 == 1:
                nn = int(0.12 * sr)
                bt = np.arange(nn) / sr
                br = rng.standard_normal(nn).astype(np.float32)
                br = signal.lfilter([0.2], [1, -0.8], br)
                br *= np.exp(-bt / 0.04)
                add_at(drums, t0, br * (0.08 * rack["brush"]))
            if rack["hat"] > 0:
                nn = int(0.04 * sr)
                ht = np.arange(nn) / sr
                hat = rng.standard_normal(nn).astype(np.float32)
                hat = np.diff(hat, prepend=0)
                hat *= np.exp(-ht / 0.012)
                add_at(drums, t0, hat * (0.025 * rack["hat"]))
                if ch["style"] in ("chorus", "final"):
                    add_at(drums, t0 + int(0.5 * spb * sr), hat * (0.012 * rack["hat"]))
    return piano, pad, bass, drums


def reverb(x, sr, wet, decay, seed):
    if wet <= 0:
        return x
    rng = np.random.default_rng(seed)
    n = int(decay * sr)
    ir = rng.standard_normal(n).astype(np.float32)
    ir *= np.exp(-np.arange(n) / (decay * 0.33 * sr))
    ir[: int(0.018 * sr)] *= np.linspace(0, 1, int(0.018 * sr))
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    wet_sig = signal.fftconvolve(x, ir, mode="full")[: len(x)].astype(np.float32)
    return ((1 - wet) * x + wet * wet_sig * 2.4).astype(np.float32)


# ---------------------------------------------------------------------------
# song assembly
# ---------------------------------------------------------------------------
def iter_sections(song, only):
    for sec in song["sections"]:
        if only and sec["id"] not in only:
            continue
        yield sec


def collect_lines(song, only):
    out = []
    beat = 0.0
    for sec in song["sections"]:
        use = (not only) or (sec["id"] in only)
        if not sec["lines"]:
            bars = len(sec.get("chords") or [])
            if use:
                out.append(("chords", beat, sec, [{"sym": c, "bars": 1} for c in sec["chords"]]))
            beat += 4 * bars
            continue
        line_beats = []
        for ln in sec["lines"]:
            line_beats.append((beat, ln))
            beat += 4 * len(ln["chords"])
        if use:
            out.append(("sung", sec, line_beats))
    return out, beat


def build(song, only, out_dir):
    voice = song["voice"]
    bpm = song["bpm"]
    spb = 60.0 / bpm
    events, total_beats = collect_lines(song, only)
    # When previewing one section, re-base beats to 0
    if only:
        first = None
        for ev in events:
            if ev[0] == "sung":
                first = ev[2][0][0]
                break
            if ev[0] == "chords":
                first = ev[1]
                break
        first = first or 0
        shifted = []
        end = 0.0
        for ev in events:
            if ev[0] == "chords":
                b0 = ev[1] - first
                shifted.append(("chords", b0, ev[2], ev[3]))
                end = max(end, b0 + 4 * sum(c["bars"] for c in ev[3]))
            else:
                lines = [(b - first, ln) for b, ln in ev[2]]
                shifted.append(("sung", ev[1], lines))
                for b0, ln in lines:
                    end = max(end, b0 + sum(n["d"] for n in ln["notes"]))
        events = shifted
        total_beats = end

    texts = []
    for ev in events:
        if ev[0] != "sung":
            continue
        for _, ln in ev[2]:
            texts.append(tts_text(ln["text"]))
    print("TTS %d lines…" % len(set(texts)))
    asyncio.run(ensure_all(texts, voice))

    tail = int(2.8 * SR)
    total = int(total_beats * spb * SR) + tail
    vocal = np.zeros(total, dtype=np.float32)
    timeline = []
    cents = []
    beat_cursor_note = 0

    chord_events = []
    for ev in events:
        if ev[0] == "chords":
            b0, sec, chords = ev[1], ev[2], ev[3]
            acc = 0
            for c in chords:
                chord_events.append({"beat": b0 + acc, "bars": c["bars"], "sym": c["sym"], "style": sec["style"]})
                acc += 4 * c["bars"]
            timeline.append({
                "id": sec["id"], "name": sec["name"], "en": sec["en"],
                "start": round(b0 * spb, 3), "lines": [],
            })
            continue
        sec, lines = ev[1], ev[2]
        sec_tl = {
            "id": sec["id"], "name": sec["name"], "en": sec["en"],
            "start": round(lines[0][0] * spb, 3), "lines": [],
        }
        gain = VOCAL_GAIN.get(sec["style"], 1.0)
        for b0, ln in lines:
            text = tts_text(ln["text"])
            audio, words = load_line_audio(text, voice)
            chars = [n["s"] for n in ln["notes"]]
            pieces = syllables_from_line(audio, words, chars, SR)
            if pieces is None:
                flat = "".join(w["t"] for w in words)
                print("  align fallback:", "".join(chars), "!=", flat)
                pieces = []
                for ch in chars:
                    # speak the character inside the line's clause by reusing
                    # a single-character fetch, cached
                    asyncio.run(ensure_all([ch + "。"], voice))
                    ax, wx = load_line_audio(ch + "。", voice)
                    pieces.append(trim(ax, SR))
            prev = 0.0
            notes_tl = []
            tbeat = b0
            for i, note in enumerate(ln["notes"]):
                src = pieces[i] if i < len(pieces) else pieces[-1]
                target = hz(midi_of(note["n"]))
                dur = note["d"] * spb
                nxt = ln["notes"][i + 1]["j"] if i + 1 < len(ln["notes"]) else None
                legato = bool(nxt) and is_sonorant(nxt)
                head, body = render_note(src, SR, target, dur, prev, note["j"], legato, gain)
                # vowel lands on the beat; consonant leads by up to 70ms
                lead = min(len(head), int(0.07 * SR))
                onset = int(tbeat * spb * SR) - lead
                if lead:
                    add_at(vocal, onset, head[-lead:] * gain)
                add_at(vocal, int(tbeat * spb * SR), body)
                err = measure_cents(body, SR, target)
                if err is not None:
                    cents.append(abs(err[0]))
                    if abs(err[0]) > 60:
                        print("  pitch %s %s target %.1f got %.1f (%+.0f cents)" % (
                            note["s"], note["n"], target, err[1], err[0]))
                notes_tl.append({
                    "s": note["s"], "j": note["j"], "n": note["n"],
                    "d": note["d"], "t": round(tbeat * spb, 3),
                })
                prev = target
                tbeat += note["d"]
            # chords under the line
            acc = 0.0
            for sym in ln["chords"]:
                chord_events.append({"beat": b0 + acc, "bars": 1, "sym": sym, "style": sec["style"]})
                acc += 4
            sec_tl["lines"].append({
                "text": ln["text"],
                "start": round(b0 * spb, 3),
                "notes": notes_tl,
            })
        timeline.append(sec_tl)
        beat_cursor_note = tbeat

    if cents:
        print("pitch median error %.0f cents, max %.0f, notes %d" % (
            float(np.median(cents)), float(np.max(cents)), len(cents)))

    print("bed…")
    piano, pad, bass, drums = render_bed(chord_events, SR, total, bpm)

    # per-bus peak tame
    def tame(x, peak=0.9):
        m = np.max(np.abs(x)) + 1e-9
        if m > peak:
            x *= peak / m
        return x

    vocal = tame(vocal, 0.8)
    piano, pad, bass, drums = tame(piano, 0.7), tame(pad, 0.7), tame(bass, 0.8), tame(drums, 0.8)

    # auto level: vocal sits clearly above the bed where someone is singing
    bed_mono = piano * 0.85 + pad * 0.7 + bass * 0.9 + drums * 0.55
    mask = np.abs(vocal) > 0.02
    if np.any(mask):
        vr = float(np.sqrt(np.mean(vocal[mask] ** 2)))
        br = float(np.sqrt(np.mean(bed_mono[mask] ** 2))) + 1e-9
        # about +7 dB
        vocal *= np.clip((br * 2.2) / vr, 0.5, 3.5)

    vocal = reverb(vocal, SR, wet=0.16, decay=1.35, seed=3)
    pad = reverb(pad, SR, wet=0.28, decay=1.6, seed=5)
    piano = reverb(piano, SR, wet=0.12, decay=1.1, seed=8)

    # stereo: vocal + bass center, piano a touch left, drums a touch right, pad wide
    def stereo(mono, pan):
        # pan -1..1
        l = np.cos((pan + 1) * np.pi / 4)
        r = np.sin((pan + 1) * np.pi / 4)
        return np.stack([mono * l, mono * r], axis=1)

    mix = stereo(vocal, 0.0)
    mix += stereo(piano, -0.18)
    mix += stereo(bass, 0.0)
    mix += stereo(drums, 0.16)
    # pad haas width
    delay = int(0.012 * SR)
    pad_r = np.zeros_like(pad)
    pad_r[delay:] = pad[:-delay]
    mix[:, 0] += pad * 0.85
    mix[:, 1] += pad_r

    # fade
    fade_in = int(0.03 * SR)
    fade_out = int(2.4 * SR)
    mix[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    mix[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    # gentle glue
    mix = np.tanh(mix * 1.15) / np.tanh(1.15)
    peak = np.max(np.abs(mix)) + 1e-9
    mix *= 0.89 / peak

    vocal_st = stereo(tame(vocal, 0.9), 0.0)
    bed = mix - stereo(vocal * 0.0, 0)  # placeholder, real bed below
    bed = stereo(piano, -0.18) + stereo(bass, 0) + stereo(drums, 0.16)
    bed[:, 0] += pad * 0.85
    bed[:, 1] += pad_r
    bed *= 0.89 / (np.max(np.abs(bed)) + 1e-9)

    os.makedirs(out_dir, exist_ok=True)
    import soundfile as sf
    stem_v = os.path.join(out_dir, "vocal.wav")
    stem_b = os.path.join(out_dir, "bed.wav")
    stem_m = os.path.join(out_dir, "mix.wav")
    sf.write(stem_v, np.clip(vocal, -1, 1), SR, subtype="PCM_16")
    sf.write(stem_b, np.clip(bed, -1, 1), SR, subtype="PCM_16")
    sf.write(stem_m, np.clip(mix, -1, 1), SR, subtype="PCM_16")

    def mp3(src, dst):
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-codec:a", "libmp3lame",
             "-q:a", "2", dst],
            check=True,
        )

    mp3(stem_m, os.path.join(out_dir, "hand-in-smoke.mp3"))
    mp3(stem_v, os.path.join(out_dir, "hand-in-smoke-vocal.mp3"))
    mp3(stem_b, os.path.join(out_dir, "hand-in-smoke-bed.mp3"))
    for p in (stem_v, stem_b, stem_m):
        os.remove(p)

    payload = {
        "id": song["id"],
        "title": song["title"],
        "subtitle": song["subtitle"],
        "dedication": song["dedication"],
        "bpm": bpm,
        "key": song["key"],
        "finalKey": song["final_key"],
        "meter": song["meter"],
        "style": song["style"],
        "voice": song["voice_name"],
        "duration": round(total / SR, 2),
        "audio": "audio/hand-in-smoke.mp3",
        "vocal": "audio/hand-in-smoke-vocal.mp3",
        "bed": "audio/hand-in-smoke-bed.mp3",
        "notes": song["notes"],
        "sections": timeline,
    }
    with open(os.path.join(out_dir, "song.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("wrote", out_dir, "duration %.1fs" % (total / SR))
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", default="", help="comma-separated section ids to render")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    only = {s for s in args.section.split(",") if s} or None
    out = args.out or (os.path.join("/tmp", "sing-preview") if only else os.path.join(ROOT, "public", "audio"))
    # song.json for the full render lives next to the site, audio files in public/audio
    if not only:
        out = os.path.join(ROOT, "public", "audio")
    build(SONG, only, out)
    if not only:
        src = os.path.join(out, "song.json")
        dst = os.path.join(ROOT, "public", "song.json")
        os.replace(src, dst)


if __name__ == "__main__":
    main()
