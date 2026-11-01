"""《濃煙裡的手》— tone-aligned score.

Melody rules (Cantonese singability):
- tone 1 sits high and level, tone 4/6 sit lower
- tone 2 and 5 get a step up into the note; the engine also scoops the attack
- compounds that contrast (媽媽 maa4→maa1, 一步一步, 窗外, 返嚟) keep that leap
Lyrics are unchanged. Final chorus is the same tune up a whole step.
"""
import re

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SKIP = set("，。、「」：；——…　 “”\"'()（）!！?？,.、 ")


def line(text, chords, rows):
    notes = []
    for row in rows:
        syl, jp, note, dur = row.split()
        notes.append({"s": syl, "j": jp, "n": note, "d": float(dur)})
    chars = [c for c in text if c not in SKIP and not c.isspace()]
    got = [n["s"] for n in notes]
    if got != chars:
        raise AssertionError("lyric mismatch\n text %s\n notes %s" % ("".join(chars), "".join(got)))
    need = 4 * len(chords)
    got_b = round(sum(n["d"] for n in notes), 4)
    if abs(got_b - need) > 1e-6:
        raise AssertionError("%s beats %s want %s" % (text, got_b, need))
    return {"text": text, "chords": list(chords), "notes": notes}


def _midi(sci):
    m = re.match(r"^([A-G])([#b]?)(-?\d)$", sci)
    if not m:
        raise ValueError(sci)
    acc = 1 if m.group(2) == "#" else -1 if m.group(2) == "b" else 0
    return (int(m.group(3)) + 1) * 12 + PC[m.group(1)] + acc


def _sci(midi):
    return NAMES[midi % 12] + str(midi // 12 - 1)


def _chord_pc(sym):
    minor = sym.endswith("m")
    body = sym[:-1] if minor else sym
    m = re.match(r"^([A-G])([#b]?)$", body)
    acc = 1 if m.group(2) == "#" else -1 if m.group(2) == "b" else 0
    return PC[m.group(1)] + acc, minor


def shift_chord(sym, semis):
    pc, minor = _chord_pc(sym)
    return NAMES[(pc + semis) % 12] + ("m" if minor else "")


def shift_section(sec, semis, sid, name, en, style):
    lines = []
    for ln in sec["lines"]:
        notes = []
        for n in ln["notes"]:
            notes.append({**n, "n": _sci(_midi(n["n"]) + semis)})
        lines.append({
            "text": ln["text"],
            "chords": [shift_chord(c, semis) for c in ln["chords"]],
            "notes": notes,
        })
    return {"id": sid, "name": name, "en": en, "style": style, "lines": lines}


def S():
    v1 = {
        "id": "v1", "name": "主歌一", "en": "Verse 1", "style": "verse",
        "lines": [
            line("凌晨三點　鐘聲一響", ["C", "G"], [
                "凌 ling4 A3 0.5", "晨 san4 A3 1.0", "三 saam1 C4 0.5", "點 dim2 D4 2.0",
                "鐘 zung1 C4 0.5", "聲 sing1 C4 1.0", "一 jat1 D4 0.5", "響 hoeng2 E4 2.0",
            ]),
            line("鞋都未着好　就跳上車廂", ["Am", "Em"], [
                "鞋 haai4 A3 0.5", "都 dou1 D4 0.5", "未 mei6 A3 0.5", "着 zoek3 B3 0.5", "好 hou2 D4 2.0",
                "就 zau6 A3 0.5", "跳 tiu3 B3 0.5", "上 soeng5 C4 0.5", "車 ce1 E4 0.5", "廂 soeng1 E4 2.0",
            ]),
            line("街燈向後退　我望住窗外", ["F", "C"], [
                "街 gaai1 D4 0.5", "燈 dang1 D4 0.5", "向 hoeng3 B3 0.5", "後 hau6 A3 0.5", "退 teoi3 B3 2.0",
                "我 ngo5 C4 0.5", "望 mong6 A3 0.5", "住 zyu6 A3 0.5", "窗 coeng1 D4 0.5", "外 ngoi6 A3 2.0",
            ]),
            line("唔係唔驚　只怕慢咗一秒", ["Dm", "G"], [
                "唔 m4 A3 0.5", "係 hai6 A3 0.5", "唔 m4 G3 0.5", "驚 geng1 E4 2.0",
                "只 zi2 D4 0.5", "怕 paa3 C4 0.5", "慢 maan6 A3 0.5", "咗 zo2 C4 0.5", "一 jat1 D4 0.5", "秒 miu5 C4 2.0",
            ]),
        ],
    }
    pre = {
        "id": "pre", "name": "導歌", "en": "Pre-Chorus", "style": "pre",
        "lines": [
            line("手機入面　老婆留咗句", ["F", "C"], [
                "手 sau2 D4 0.5", "機 gei1 E4 0.5", "入 jap6 A3 0.5", "面 min6 A3 2.0",
                "老 lou5 C4 0.5", "婆 po4 A3 0.5", "留 lau4 A3 0.5", "咗 zo2 C4 0.5", "句 geoi3 B3 2.5",
            ]),
            line("「記得食飯　記得返嚟」", ["Am", "G"], [
                "記 gei3 B3 0.5", "得 dak1 E4 0.5", "食 sik6 A3 1.0", "飯 faan6 A3 2.0",
                "記 gei3 B3 0.5", "得 dak1 D4 0.5", "返 faan1 E4 1.0", "嚟 lai4 A3 2.0",
            ]),
            line("我冇時間覆　只係望一望", ["F", "Em"], [
                "我 ngo5 C4 0.5", "冇 mou5 C4 0.5", "時 si4 A3 0.5", "間 gaan3 B3 0.5", "覆 fuk1 E4 1.5",
                "只 zi2 D4 0.5", "係 hai6 A3 0.5", "望 mong6 A3 0.5", "一 jat1 D4 0.5", "望 mong6 A3 2.5",
            ]),
            line("然後戴上面罩　走入呢片灰", ["Dm", "G"], [
                "然 jin4 A3 0.5", "後 hau6 A3 0.5", "戴 daai3 B3 0.5", "上 soeng5 C4 0.5", "面 min6 A3 0.5", "罩 zaau3 B3 0.5",
                "走 zau2 D4 0.5", "入 jap6 A3 0.5", "呢 ni1 E4 0.5", "片 pin3 B3 0.5", "灰 fui1 E4 3.0",
            ]),
        ],
    }
    ch = {
        "id": "ch", "name": "副歌", "en": "Chorus", "style": "chorus",
        "lines": [
            line("濃煙裡面　我伸手搵你", ["C", "G"], [
                "濃 nung4 A3 0.5", "煙 jin1 C4 0.5", "裡 leoi5 D4 1.0", "面 min6 A3 1.0",
                "我 ngo5 B3 0.5", "伸 san1 D4 0.5", "手 sau2 E4 0.5", "搵 wan2 E4 0.5", "你 nei5 C4 3.0",
            ]),
            line("睇唔到路　都要行前多一呎", ["Am", "Em"], [
                "睇 tai2 E4 0.5", "唔 m4 A3 0.5", "到 dou3 C4 0.5", "路 lou6 A3 1.5",
                "都 dou1 E4 0.5", "要 jiu3 C4 0.5", "行 haang4 A3 0.5", "前 cin4 G3 0.5", "多 do1 C4 0.5", "一 jat1 E4 0.5", "呎 cek3 C4 2.0",
            ]),
            line("如果呢個城市　仲有人等緊返屋企", ["F", "C"], [
                "如 jyu4 A3 0.5", "果 gwo2 C4 0.5", "呢 ni1 E4 0.5", "個 go3 D4 0.5", "城 sing4 C4 0.5", "市 si5 D4 0.5",
                "仲 zung6 A3 0.5", "有 jau5 C4 0.5", "人 jan4 A3 0.5", "等 dang2 C4 0.5", "緊 gan2 D4 0.5", "返 faan1 E4 0.5", "屋 uk1 E4 0.5", "企 kei2 F4 1.5",
            ]),
            line("就算熏到眼痛　都唔會放開你", ["F", "G"], [
                "就 zau6 A3 0.5", "算 syun3 B3 0.5", "熏 fan1 E4 0.5", "到 dou3 C4 0.5", "眼 ngaan5 A3 0.5", "痛 tung3 B3 0.5",
                "都 dou1 D4 0.5", "唔 m4 A3 0.5", "會 wui5 C4 0.5", "放 fong3 D4 0.5", "開 hoi1 F4 1.0", "你 nei5 D4 2.0",
            ]),
        ],
    }
    ch2 = {
        "id": "ch2", "name": "副歌（後半）", "en": "Chorus II", "style": "chorus",
        "lines": [
            line("你唔使驚　我跟住你背脊", ["C", "G"], [
                "你 nei5 C4 0.5", "唔 m4 A3 0.5", "使 sai2 D4 0.5", "驚 geng1 E4 1.5",
                "我 ngo5 B3 0.5", "跟 gan1 D4 0.5", "住 zyu6 A3 0.5", "你 nei5 C4 0.5", "背 bui3 D4 0.5", "脊 zek3 D4 2.5",
            ]),
            line("一步一步　我哋行返出去", ["Am", "Em"], [
                "一 jat1 E4 0.5", "步 bou6 A3 0.5", "一 jat1 E4 0.5", "步 bou6 A3 1.5",
                "我 ngo5 C4 0.5", "哋 dei6 A3 0.5", "行 haang4 B3 0.5", "返 faan1 E4 0.5", "出 ceot1 E4 0.5", "去 heoi3 C4 2.5",
            ]),
            line("如果呢個城市　仲有人肯為人留低", ["F", "C"], [
                "如 jyu4 A3 0.5", "果 gwo2 C4 0.5", "呢 ni1 E4 0.5", "個 go3 D4 0.5", "城 sing4 C4 0.5", "市 si5 D4 0.5",
                "仲 zung6 A3 0.5", "有 jau5 C4 0.5", "人 jan4 A3 0.5", "肯 hang2 E4 0.5", "為 wai6 A3 0.5", "人 jan4 A3 0.5", "留 lau4 A3 0.5", "低 dai1 E4 1.5",
            ]),
            line("我呢條命　就唔算白過一日", ["F", "G"], [
                "我 ngo5 C4 0.5", "呢 ni1 E4 0.5", "條 tiu4 A3 0.5", "命 ming6 A3 1.5",
                "就 zau6 A3 0.5", "唔 m4 G3 0.5", "算 syun3 B3 0.5", "白 baak6 A3 0.5", "過 gwo3 B3 0.5", "一 jat1 E4 0.5", "日 jat6 A3 2.0",
            ]),
        ],
    }
    v2 = {
        "id": "v2", "name": "主歌二", "en": "Verse 2", "style": "verse2",
        "lines": [
            line("十八樓　走廊已經塌咗", ["C", "G"], [
                "十 sap6 A3 0.5", "八 baat3 B3 0.5", "樓 lau4 A3 2.5",
                "走 zau2 D4 0.5", "廊 long4 A3 0.5", "已 ji5 C4 0.5", "經 ging1 D4 0.5", "塌 taap3 B3 0.5", "咗 zo2 D4 2.0",
            ]),
            line("條水喉扯到盡　手心都震", ["Am", "Em"], [
                "條 tiu4 A3 0.5", "水 seoi2 D4 0.5", "喉 hau4 A3 1.0", "扯 ce2 D4 0.5", "到 dou3 C4 0.5", "盡 zeon6 A3 1.0",
                "手 sau2 D4 0.5", "心 sam1 E4 0.5", "都 dou1 E4 0.5", "震 zan3 C4 2.5",
            ]),
            line("有個細路　攬實我隻腳", ["F", "C"], [
                "有 jau5 C4 0.5", "個 go3 B3 0.5", "細 sai3 B3 0.5", "路 lou6 A3 2.0",
                "攬 laam2 D4 0.5", "實 sat6 A3 0.5", "我 ngo5 C4 0.5", "隻 zek3 B3 0.5", "腳 goek3 B3 2.5",
            ]),
            line("佢話：「叔叔，我媽媽仲喺裡面。」", ["Dm", "G"], [
                "佢 keoi5 C4 0.5", "話 waa6 A3 0.5", "叔 suk1 E4 0.5", "叔 suk1 E4 1.0",
                "我 ngo5 C4 0.5", "媽 maa4 A3 0.5", "媽 maa1 E4 0.5", "仲 zung6 A3 0.5", "喺 hai2 D4 0.5", "裡 leoi5 C4 0.5", "面 min6 A3 2.5",
            ]),
        ],
    }
    pre2 = {
        "id": "pre2", "name": "導歌二", "en": "Pre-Chorus 2", "style": "pre",
        "lines": [
            line("我冇講嘢　只係點一點頭", ["F", "C"], [
                "我 ngo5 C4 0.5", "冇 mou5 C4 0.5", "講 gong2 D4 0.5", "嘢 je5 C4 1.5",
                "只 zi2 D4 0.5", "係 hai6 A3 0.5", "點 dim2 D4 0.5", "一 jat1 E4 0.5", "點 dim2 D4 0.5", "頭 tau4 A3 2.5",
            ]),
            line("抱起佢　交俾下一個兄弟", ["Am", "G"], [
                "抱 pou5 C4 0.5", "起 hei2 E4 0.5", "佢 keoi5 C4 1.5",
                "交 gaau1 E4 0.5", "俾 bei2 D4 0.5", "下 haa6 A3 0.5", "一 jat1 E4 0.5", "個 go3 C4 0.5", "兄 hing1 E4 0.5", "弟 dai6 A3 2.5",
            ]),
            line("轉身再入去　熱到面罩都溶", ["F", "Em"], [
                "轉 zyun3 B3 0.5", "身 san1 E4 0.5", "再 zoi3 B3 0.5", "入 jap6 A3 0.5", "去 heoi3 B3 1.0",
                "熱 jit6 A3 0.5", "到 dou3 B3 0.5", "面 min6 A3 0.5", "罩 zaau3 B3 0.5", "都 dou1 E4 0.5", "溶 jung4 A3 2.5",
            ]),
            line("但我記得　佢媽媽對眼", ["Dm", "G"], [
                "但 daan6 A3 0.5", "我 ngo5 C4 0.5", "記 gei3 B3 0.5", "得 dak1 E4 1.5",
                "佢 keoi5 C4 0.5", "媽 maa4 A3 0.5", "媽 maa1 E4 1.0", "對 deoi3 C4 0.5", "眼 ngaan5 D4 2.5",
            ]),
        ],
    }
    bridge = {
        "id": "bridge", "name": "橋段", "en": "Bridge", "style": "bridge",
        "lines": [
            line("唔係想做英雄", ["Am", "F"], [
                "唔 m4 A3 0.5", "係 hai6 A3 0.5", "想 soeng2 D4 0.5", "做 zou6 A3 1.5", "英 jing1 E4 1.0", "雄 hung4 A3 4.0",
            ]),
            line("只係有人要救", ["C", "G"], [
                "只 zi2 D4 0.5", "係 hai6 A3 0.5", "有 jau5 C4 0.5", "人 jan4 A3 1.5", "要 jiu3 C4 1.0", "救 gau3 C4 4.0",
            ]),
            line("每次行入去", ["Am", "Em"], [
                "每 mui5 C4 0.5", "次 ci3 B3 0.5", "行 haang4 A3 1.0", "入 jap6 A3 1.0", "去 heoi3 B3 5.0",
            ]),
            line("都可能冇得行返出嚟", ["F", "G"], [
                "都 dou1 E4 0.5", "可 ho2 D4 0.5", "能 nang4 A3 0.5", "冇 mou5 C4 0.5", "得 dak1 E4 0.5",
                "行 haang4 A3 0.5", "返 faan1 E4 0.5", "出 ceot1 E4 0.5", "嚟 lai4 A3 4.0",
            ]),
            line("但有一句　我哋冇寫喺牆上", ["Am", "F"], [
                "但 daan6 A3 0.5", "有 jau5 C4 0.5", "一 jat1 E4 0.5", "句 geoi3 C4 1.0",
                "我 ngo5 C4 0.5", "哋 dei6 A3 0.5", "冇 mou5 C4 0.5", "寫 se2 D4 0.5", "喺 hai2 D4 0.5", "牆 coeng4 A3 0.5", "上 soeng6 A3 2.5",
            ]),
            line("先救人　後講自己", ["C", "G"], [
                "先 sin1 E4 1.0", "救 gau3 C4 0.5", "人 jan4 A3 1.5",
                "後 hau6 A3 0.5", "講 gong2 D4 0.5", "自 zi6 A3 0.5", "己 gei2 D4 3.5",
            ]),
        ],
    }
    outro = {
        "id": "outro", "name": "尾聲", "en": "Outro", "style": "outro",
        "lines": [
            line("天光嘅時候　火已經熄", ["D", "A"], [
                "天 tin1 D4 0.5", "光 gwong1 D4 0.5", "嘅 ge3 B3 0.5", "時 si4 A3 0.5", "候 hau6 A3 2.0",
                "火 fo2 D4 0.5", "已 ji5 C#4 0.5", "經 ging1 E4 0.5", "熄 sik1 D4 2.5",
            ]),
            line("我坐喺路邊　除低頂帽", ["Bm", "G"], [
                "我 ngo5 C#4 0.5", "坐 co5 C#4 0.5", "喺 hai2 E4 0.5", "路 lou6 A3 0.5", "邊 bin1 D4 2.0",
                "除 ceoi4 A3 0.5", "低 dai1 E4 0.5", "頂 deng2 F#4 0.5", "帽 mou6 A3 2.5",
            ]),
            line("有人遞支水　講聲「多謝你」", ["D", "A"], [
                "有 jau5 C#4 0.5", "人 jan4 A3 0.5", "遞 dai6 A3 0.5", "支 zi1 D4 0.5", "水 seoi2 E4 1.0",
                "講 gong2 E4 0.5", "聲 sing1 F#4 0.5", "多 do1 F#4 0.5", "謝 ze6 A3 0.5", "你 nei5 C#4 3.0",
            ]),
            line("我笑一笑　話：「呢啲係我哋嘅工作。」", ["G", "D", "A", "D"], [
                "我 ngo5 C#4 0.5", "笑 siu3 B3 1.0", "一 jat1 E4 0.5", "笑 siu3 B3 2.0",
                "話 waa6 A3 1.0", "呢 ni1 E4 0.5", "啲 di1 E4 0.5", "係 hai6 A3 2.0",
                "我 ngo5 C#4 0.5", "哋 dei6 A3 0.5", "嘅 ge3 B3 1.0", "工 gung1 E4 1.0", "作 zok3 C#4 5.0",
            ]),
            line("然後望住個天　等下一次鐘聲", ["D", "A", "G", "D"], [
                "然 jin4 A3 0.5", "後 hau6 A3 0.5", "望 mong6 A3 0.5", "住 zyu6 A3 2.5",
                "個 go3 B3 0.5", "天 tin1 F#4 3.5",
                "等 dang2 E4 0.5", "下 haa6 A3 0.5", "一 jat1 E4 0.5", "次 ci3 B3 0.5", "鐘 zung1 E4 1.0", "聲 sing1 E4 5.0",
            ]),
        ],
    }
    sections = [
        {"id": "intro", "name": "前奏", "en": "Intro", "style": "intro", "lines": [], "chords": ["C", "Am", "F", "G"]},
        v1, pre, ch, ch2, v2, pre2,
        shift_section(ch, 0, "ch-re", "副歌（重唱）", "Chorus", "chorus"),
        bridge,
        shift_section(ch, 2, "final", "副歌（升 key）", "Final Chorus", "final"),
        shift_section(ch2, 2, "final2", "副歌（升 key · 後半）", "Final Chorus II", "final"),
        outro,
    ]
    return {
        "id": "hand-in-smoke",
        "title": "濃煙裡的手",
        "subtitle": "Hand in the Smoke",
        "dedication": "寫給每一位香港消防員，同埋喺屋企等佢哋返嚟嘅人。",
        "voice": "zh-HK-HiuMaanNeural",
        "voice_name": "曉曼",
        "bpm": 76,
        "key": "C 大調",
        "final_key": "D 大調",
        "meter": "4/4",
        "style": "廣東流行 · 抒情搖滾",
        "sections": sections,
        "notes": [
            "全首歌用「一個人嘅視角」寫，唔講口號，只講動作：着鞋、上車、伸手、抱人、除帽。",
            "副歌刻意用一句最簡單嘅承諾——「唔會放開你」，因為火場裡面，手係唯一嘅語言。",
            "橋段收細，留白畀「先救人　後講自己」。",
            "尾聲唔用大團圓，用「等下一次鐘聲」收尾：呢份工冇完場，只有下一更。",
        ],
    }


SONG = S()
