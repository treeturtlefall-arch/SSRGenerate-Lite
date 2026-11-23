# SSRGenerate-Lite

写真 1 枚から **16.0 秒（縦 `540×960` / 横 `960×540`、24fps）の SSR ガチャ当選演出 MP4** と **フル解像度カード静止画（`.card.png`、縦 `900×1590` / 横 `1480×860`）** を同時生成・定量 QA・納品する、**AI エージェント（Muse VM 等）向け軽量版リポジトリ**です。

フル品質版（1080p / 30fps）の本家リポジトリおよび起点コミットとの関係は [`UPSTREAM.md`](./UPSTREAM.md) を参照してください。

---

## 特徴

1. **エージェント自律実行 CLI（`agent/ssr_agent.py`）＆ スキル（`skill/SKILL.md`）同梱**
   - **記入シート (`sheet`)** / **自然文 (`free`)** / **おまかせ (`omakase`)** の 3 モードに対応し、すべて再現可能な `request.json` に正規化して MP4・フル解像度 `.card.png`・QA レポートを出力します。
2. **GPU なし仮想環境（4 vCPU / RAM 7.7 GiB 等）向けに最適化された既定デチューン ＆ カード PNG フル解像度維持**
   - 動画出力解像度 **540×960**（横 **960×540**、qHD 540p）、フレームレート **24fps**、エンコード **CRF 20**。
   - 内部レイアウト座標系は本家 `1080×1920`（横 `1920×1080`）をそのまま維持し、動画出力ステージのみ `0.5`（1/2 整数比）スケーリングすることで本家との互換性を 100% 保持。
   - 同時出力されるカード静止画（`renders/SSR_{preset}_{YYYYMMDD}.card.png`）は、Python ダイレクト合成（`scripts/render_card_png.py`）により **本家 1080p と完全同一のフル解像度（縦 `900×1590` / 横 `1480×860`）** を約 0.2 秒で生成します。
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
npm run render         # 540p / 24fps / CRF 20 で MP4 + フル解像度 .card.png 同時書き出し
npm run render:card    # フル解像度 card.png (900x1590 / 1480x860) 単体書き出し
npm run qa -- renders/SSR_cute-pastel_20261122.mp4 --check-audio  # 定量 QA
```
