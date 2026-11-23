# UPSTREAM.md — 本家 SSRGenerate との同期記録

## 起点情報

- **本家リポジトリ**: `https://github.com/treeturtlefall-arch/SSRGenetate.git` (`SSRGenerate`)
- **起点コミット**: `0df40bea4138a4390ea4027f1f730dd1d86f69fc` (`0df40be`, 2026-11-22)
  - Phase 5 横モード（16:9）実装 (`37c6575`)
  - 未使用フォント省エネ化 (`0ca751c`)
  - アセット生成・動画QAの並列高速化 (`4216ed0`)
  - CLI `--variables` 部分指定時の属性バッジ空文字フォールバック修正 (`0df40be` — 設計メモ §2.1 の問題を解消)

---

## SSRGenerate-Lite でのデチューン変更一覧（既定値として固定）

Muse エージェントの仮想環境（4 vCPU / RAM 7.7 GiB / GPU なし Software Rendering）で **1本 60〜90 秒以内** に生成・検証・納品できるよう、以下のデチューンを既定値として組み込んでいます。

1. **動画出力解像度 540p（縦 `540×960` / 横 `960×540`）＋ 内部座標系 `1080×1920` ＆ フル解像度 `.card.png` 同時出力**
   - `scripts/_utils.py` の `LayoutSpec` に `output_w` / `output_h`（`540×960` / `960×540`）と `fps=24` を定義。
   - HyperFrames の予約プリセット属性 `data-resolution`（1080p 強制）との衝突を避けるため、`<html>` の向き属性を `data-orientation="portrait|landscape"` に変更。
   - コンポジション内部のレイアウト・カード寸法（`900×1590` / `1480×860`）・タイポ PNG 寸法は本家と 100% 同一のまま維持し、`#scene-summon-stage` / `#scene-result-stage` に `transform: scale(0.5); transform-origin: 0 0;` を適用して動画ラスタライズ画素数を 1080p 比 25%（720p 比 56.25%）に削減。これにより Muse VM で 100 秒切りを達成しつつ、本家からのパッチ移植で座標換算が不要。
   - さらに `scripts/render_card_png.py` により、生成済みのフル解像度パーツ群から本家 1080p と完全同一解像度（縦 `900×1590` / 横 `1480×860`）のカード静止画 `renders/SSR_{preset}_{YYYYMMDD}.card.png` を約 0.2 秒で同時出力。
2. **フレームレート `24fps`（384 フレーム）＆ エンコード軽量化（`-q standard --crf 20`）**
   - `index.html`, `compositions/scene-summon.html`, `compositions/scene-result.html`, `scripts/render_video.mjs` を `24fps` 既定に統一。
3. **HyperFrames の `low-memory-mode` 自動1ワーカー制限の解除（`--no-low-memory-mode -w 3`）**
   - RAM 8 GB 以下の VM で HyperFrames が自動的に 1 ワーカーへ固定する挙動を解除し、既定 3 ワーカー並列（環境変数 `SSR_LITE_WORKERS` で変更可）で 4 vCPU を活用。
4. **Software GPU（SwiftShader）向け描画削減**
   - `compositions/shared-base.css`: 全フレームで `mix-blend-mode: overlay` を走らせる `.film-grain-overlay` を `display: none` 化（`scripts/render_material.py` での生成も省略）。
   - `card-config.js`: 全画面 SVG 色収差フィルタ `material.chromaShockPx` の既定値を `0`（OFF）に設定。
   - `compositions/scene-summon.css` / `scene-result.css`: 2枚重ねの巨大ゴッドレイの 2 枚目（`#summon-godrays-b`, `#result-rays-b`）を非表示化、3D カード側面スライスを 5枚 → 2枚（`s1, s5`）に削減、タイポ PNG と重複する CSS `filter: drop-shadow(...)` を撤去。
   - `compositions/scene-summon-setup.js` / `scene-result-setup.js`: 螺旋ウィスプ尾ノード（`42→22`）、浮遊破片（`36+14+20 → 18+8+10`）、スパークル（`22→12`）、金箔フレーク（`18→8`）、玉ボケ（`16→8`）を約半数に最適化。
5. **Muse VM 環境ガード（プライベート HOME `chmod 700` ＆ 大容量 `TMPDIR`）**
   - `scripts/render_video.mjs` および `agent/ssr_agent.py` にて、POSIX 環境で `.hf_home`（毎回 `chmod 700` を再適用）と `.tmp`（プロジェクトディスク側の一時領域）を自動設定。
6. **リポジトリ軽量化（生成物・フォントの初回取得方式）**
   - `assets/generated/*`, `assets/se_*.wav`, `assets/fonts/*.ttf` を `.gitignore` 管理とし、`ssr-agent setup`（または `agent/setup_env.sh` / `.ps1`）で本家固定コミット `0df40bea4138a4390ea4027f1f730dd1d86f69fc` から SHA256 検証付きでフォントを取得＆全アセットを初期生成する構成。
7. **音声事前ミックス＋FFmpeg 高速 mux（`assets/se_mix_16s.wav`）**
   - `scripts/generate_se.py` で 16.0s 統合マスター WAV（`assets/se_mix_16s.wav`）を事前生成し、`scripts/render_video.mjs` の既定動作として一時無音 HTML で映像のみレンダリングした後に `ffmpeg -c:v copy -c:a aac` で高速 mux する（`--no-fast-audio` または `SSR_FAST_AUDIO=0` で従来方式へ切替可能）。これにより HyperFrames の音声処理フェーズ（Muse VM で約 40 秒）を 0 秒化。

---

## 移植履歴

| 日付 | 本家コミット | 内容 |
|:---|:---|:---|
| 2026-11-22 | `0df40be` | 初期構築（Phase 5 横モード＋フォント省エネ化＋並列高速化＋属性フォールバック修正までを取り込み） |
