# SSRGenerate-Lite

写真 1 枚から **16.0 秒（縦 `720×1280` / 横 `1280×720`、24fps）の SSR ガチャ当選演出 MP4** を生成・定量 QA・納品する、**AI エージェント（Muse VM 等）向け軽量版リポジトリ**です。

フル品質版（1080p / 30fps）の本家リポジトリおよび起点コミットとの関係は [`UPSTREAM.md`](./UPSTREAM.md) を参照してください。

---

## 特徴

1. **エージェント自律実行 CLI（`agent/ssr_agent.py`）＆ スキル（`skill/SKILL.md`）同梱**
   - **記入シート (`sheet`)** / **自然文 (`free`)** / **おまかせ (`omakase`)** の 3 モードに対応し、すべて再現可能な `request.json` に正規化して MP4 と QA レポートを出力します。
2. **GPU なし仮想環境（4 vCPU / RAM 7.7 GiB 等）向けに最適化された既定デチューン**
   - 解像度 **720×1280**（横 **1280×720**）、フレームレート **24fps**、エンコード **CRF 20**。
   - 内部レイアウト座標系は本家 `1080×1920`（横 `1920×1080`）をそのまま維持し、出力ステージのみ `2/3` スケーリングすることで本家との互換性を 100% 保持。
   - HyperFrames の RAM 8 GB 以下自動 1 ワーカー制限を解除（`--no-low-memory-mode -w 3`）し、Software GPU で重い全画面 `overlay` グレイン・SVG 色収差・多重ゴッドレイ・パーティクル数を最適化。
3. **超軽量リポジトリ（クローン直後 約 1 MB）**
   - 生成 PNG / WAV とフォントは初回 `setup` で自動取得・決定論生成します（ネットワーク接続が前提。`setup` 後の実働サイズは `.venv`・フォント約 34 MB・生成アセット等を含め約 350〜590 MB）。

---

## クイックスタート（エージェント / CLI）

```bash
# 1. 初回セットアップ（venv 作成・pip install・フォント取得・全アセット生成・事前 check）
#    Linux / macOS / Muse VM:
bash agent/setup_env.sh
#    Windows PowerShell:
#    pwsh -ExecutionPolicy Bypass -File agent/setup_env.ps1

# 2. 環境・対応機能の JSON 確認
.venv/bin/python agent/ssr_agent.py capabilities --json

# 3. 記入シート（request.json）からレンダリング＋自動 QA
.venv/bin/python agent/ssr_agent.py render --request agent/examples/sheet_cute_portrait.json --json

# 4. おまかせモード（写真＋ cool / cute 二択から自動生成）
.venv/bin/python agent/ssr_agent.py omakase --photo assets/photo.jpg --style cute --json

# 5. 既存 MP4 の定量 QA
.venv/bin/python agent/ssr_agent.py qa --file renders/SSR_cute-pastel_20261122.mp4 --json
```

> ※ すでに依存パッケージ（Pillow / numpy 等）が揃った Python 環境を使う場合は `python3 agent/ssr_agent.py setup` を直接実行することもできます。

---

## npm コマンド（本家互換）

```bash
npm run build:assets   # 全ての生成アセット（タイポ・光学・フレーム・効果音）を一括並列生成
npm run check          # HyperFrames lint + runtime + layout + motion 検証
npm run render         # 720p / 24fps / CRF 20 で MP4 書き出し
npm run qa -- renders/SSR_cute-pastel_20261122.mp4 --check-audio  # 定量 QA
```
