# 濃煙裡的手

一首跟住粵語聲調唱的廣東歌。寫給每一位香港消防員，同埋喺屋企等佢哋返嚟嘅人。

歌詞沿用原作，一個字都冇改。呢個版本改咗三樣令到廣東話聽得清嘅嘢：

- **成句讀音。** 每一句交俾粵語語音（曉曼）讀完，再按詞界切開。屋企、媽媽、着、咗、哋跟住個詞，唔會變成孤立字嘅錯讀。
- **把聲唱，唔係蜂鳴器。** 用時域疊加把真實聲線嘅音高搬去譜上，共振峰留低。長音先加顫音，聲調嘅升降只留喺音頭。
- **旋律遷就聲調。** 高平聲坐高音，低降聲坐低，上聲向上一步。副歌唔再將「路」「返」「伸手」放喺同聲調相反嘅音。

尾段副歌升一個全音，去 D 大調。

## 聽

```bash
npm install
npm run dev
```

開 [http://127.0.0.1:4178](http://127.0.0.1:4178)。底部播放器可以轉「成首 / 人聲 / 伴奏」。點段名或者時間，跳去嗰一段；點任何一個字，由嗰個音開始唱。字上面係粵拼，色字係聲調。

## 再唱一次

譜喺 `songs/score.py`，合成喺 `tools/sing.py`。需要網絡去拎粵語語音。

```bash
pip install -r requirements.txt
python3 tools/sing.py
```

輸出：

- `public/audio/hand-in-smoke.mp3` 成首
- `public/audio/hand-in-smoke-vocal.mp3` 人聲
- `public/audio/hand-in-smoke-bed.mp3` 伴奏
- `public/song.json` 歌詞、粵拼、每個音嘅時間

只預聽一段：`python3 tools/sing.py --section ch --out /tmp/sing-preview`
