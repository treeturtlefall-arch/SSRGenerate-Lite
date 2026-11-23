# SSRGenerate-Lite — エージェント作業規約

写真 1 枚から **16.0 秒（縦 `540×960` / 横 `960×540`、24fps）の SSR ガチャ当選演出 MP4** と **フル解像度カード静止画（`.card.png`、縦 `900×1590` / 横 `1480×860`）** を同時生成する、AI エージェント（Muse VM 等）向けの軽量版 HyperFrames プロジェクト。
本家 `SSRGenerate` からの起点コミット・デチューン内容は [`UPSTREAM.md`](./UPSTREAM.md)、エージェント実行手順は [`skill/SKILL.md`](./skill/SKILL.md) を参照してください。

## 絶対ルール

1. **総尺と余白**: 全体 **16.0 秒**（冒頭 `0.5s` 無音・黒フェードイン ＋ 本編 `15.0s` ＋ 末尾 `0.5s` 無音・黒フェードアウト、音声は `15.3s` で無音着地）。
2. **終盤の固定ルール**: 本編 `12.0s 〜 15.0s`（全体 `12.5s 〜 15.5s`）はカード・文字・星・粒子の位置とサイズを完全固定し、光の微動（ホロシマー・リムグレア・背景ハロー・スパークル/玉ボケ明滅）のみ動かす。
3. **写真保護**: 入力写真（`assets/photo.jpg` 等）は 100% クリアなまま無加工で維持する。顔被りは Z 順・軌道・中央減衰マスクで回避する。
4. **決定論的レンダリング**: `Math.random()`・`Date.now()`・実行時ネットワーク `fetch()` を禁止する。Mulberry32 疑似乱数と登録済み GSAP タイムラインのみで描画する。
5. **内部座標系と出力解像度の分離（動画 540p ＋ カード PNG フル解像度維持）**:
   - 動画出力解像度は **縦 `540×960` / 横 `960×540`（24fps）** だが、コンポジション内部レイアウト座標系とカード寸法（縦 `900×1590` / 横 `1480×860`）は本家 `1080×1920` 基準のまま維持し、`#scene-summon-stage` / `#scene-result-stage` の `transform: scale(0.5)` で縮小出力する。同時出力されるカード静止画（`.card.png`）は本家と同一のフル解像度（縦 `900×1590` / 横 `1480×860`）で出力する。
   - `<html>` の向き属性には `data-orientation="portrait|landscape"` を使用する（`data-resolution` は HyperFrames の 1080p 強制予約属性のため使用しない）。

## プロジェクト地図

- `agent/` — AI エージェント層（`ssr_agent.py` CLI、`request.schema.json`、`examples/`、`setup_env.sh` / `.ps1`）
- `skill/` — エージェント向けスキル定義（`SKILL.md`, `skill.yaml`）
- `UPSTREAM.md` — 本家 `SSRGenerate` の起点コミット（`0df40be`）とデチューン変更一覧
- `card-config.js` / `index.html` — カード設定（`--variables` 上書き対応）と 16.0s ルートコンポジション
- `compositions/` — サブコンポジション（`scene-summon.*`, `scene-result.*`）および共通基盤（`shared-base.css`, `shared-utils.js`）
- `scripts/` — Python 決定論的アセット生成（`build_all.py`, `render_*.py`, `render_card_png.py`, `generate_se.py`）、レンダリングラッパー（`render_video.mjs`）、自動定量 QA（`qa_video.py`）

## コマンド

```bash
# エージェント CLI (推奨)
python agent/ssr_agent.py setup
python agent/ssr_agent.py capabilities --json
python agent/ssr_agent.py render --request agent/examples/sheet_cute_portrait.json --json
python agent/ssr_agent.py omakase --photo assets/photo.jpg --style cute --json
python agent/ssr_agent.py qa --file renders/SSR_cute-pastel_20261122.mp4 --json

# npm コマンド
npm run build:assets   # 全ての生成アセットを一括並列生成
npm run check          # lint + runtime + layout + motion + contrast 検証
npm run render         # MP4 (540p / 24fps / CRF 20) + フル解像度 .card.png 同時書き出し
npm run render:card    # フル解像度 card.png (900x1590 / 1480x860) 単体書き出し
npm run qa -- renders/SSR_cute-pastel_20261122.mp4 --check-audio
```
