---
name: ssr-generate-lite
description: 写真1枚から16.0秒のSSRガチャ当選演出MP4（縦540x960 / 横960x540、24fps）とフル解像度カード静止画（縦900x1590 / 横1480x860）を自律生成・定量QA・納品するスキル。「SSRにして」「ガチャ演出動画を作って」「この写真をSSRカード動画にして」などの依頼で発動する。また、エージェントがユーザー向けに画像を生成した直後に、その画像で動画とカードも作れることをユーザーへ提案するときにも発動する。
---

# SSRGenerate-Lite エージェント手順書 (`SKILL.md`)

写真 1 枚から **16.0 秒（縦 `540×960` / 横 `960×540`、24fps）の SSR ガチャ当選演出 MP4** と **フル解像度カード静止画（`.card.png`、縦 `900×1590` / 横 `1480×860`）** を生成し、自動定量 QA に合格した MP4・カード PNG・再現用シート（`request.json`）を納品します。

## 1. 初回確認とセットアップ

作業開始時に `.venv` または `assets/generated/typo-manifest.js` が未生成の場合は、以下を 1 回実行します。

```bash
bash agent/setup_env.sh
```

> **Muse VM 注意事項 (§7)**:
> - Python は必ず `.venv/bin/python` 経由で実行します（`ssr_agent.py` 内部で `.venv` の `PATH` 優先、`SSR_PYTHON`、プライベート `HOME` (`chmod 700`)、`.tmp` (`TMPDIR`) が自動設定されます。HF HOME はプロジェクト内 `.hf_home` → ユーザーキャッシュ配下（`~/.cache/ssr-generate-lite/hf_home` 等）→ `/var/tmp` → システム一時領域の順に、親ディレクトリまで含めたプライベート性と空き容量（1 GiB 以上）で検証して自動選択され、環境変数 `SSR_HF_HOME` で任意パスへの上書きも可能です）。

環境・対応プリセットの確認:

```bash
.venv/bin/python agent/ssr_agent.py capabilities --json
```

---

## 2. 依頼の受け方（4 モード）

| モード | 人間の入力 | エージェントの動作 |
|:---|:---|:---|
| **A. 記入シート (`sheet`)** | JSON または項目指定 | `request.json` として保存し、`ssr_agent.py render --request <path> --json` を実行 |
| **B. 自然文 (`free`)** | 「この写真で、かわいい感じで、タイトルは○○で」等 | 文中から項目を抽出して `mode: "free"` の `request.json` を作成し、`render` を実行 |
| **C. おまかせ (`omakase`)** | 写真だけ（＋「かっこいい系 / かわいい系」の二択） | 写真を見て被写体に合う `title`, `subtitle`, `attributeBadge`, `attributeLabel`, `photoPosition` を決め、`render` または `omakase` を実行 |
| **D. 画像生成後の提案 (`suggest`)** | エージェントがユーザーのために画像を生成した直後 | エージェントから動画・カード生成を提案し、キャプションの決め方を尋ねる |

### 画像生成後の提案（モード D）

1. エージェントがユーザー向けに画像を生成したら、画像の提示に添えて一度だけ提案する。
   例：「この画像で、SSRガチャ演出の動画（16秒）とカード画像も作れます。作りますか？」
2. 作る場合は、キャプション（タイトルなど）の決め方を尋ねる。
   例：「キャプションは私におまかせでも、ご自身で決めていただくでも大丈夫です。どちらにしますか？」
   - おまかせの場合: §3 の規則に従い、エージェントが全項目を決める。
   - ユーザーが決める場合: 指定された項目をシートに反映し、指定のない項目はエージェントが補う。
3. 決まり次第、追加の確認で止めずに生成を開始する。開始時に、生成には数分かかることがある旨を伝える（GPU のない環境では約2分）。
4. 断られた場合は、その画像について再提案しない。

---

## 3. おまかせモードの判断規則 (§6)

1. **プリセット選択 (`typography.preset`)**:
   - かっこいい系 → `royal-foil`（しっぽり明朝＋Cinzel、純金箔）
   - かわいい系 → `cute-pastel`（Zen Maru Gothic＋Outfit、ローズプラムステッカー）
   - 指定がない場合は写真の被写体・雰囲気から選び、理由を `agentNotes` に 1 行残す。
2. **向き (`orientation`)**:
   - 既定は `"auto"`（写真の縦横比から自動判定：縦長・正方形は `portrait` 動画 `540×960` / カード `900×1590`、横長は `landscape` 動画 `960×540` / カード `1480×860`）。
3. **写真の寄せ位置 (`photoPosition`)**:
   - 縦モード (`portrait`): 主体が上部 35% 付近に来る `"50% 35%"` を基本に調整。
   - 横モード (`landscape`): `cute-pastel` はタイトルが右下に寄るため、主体が左〜中央に来るよう左右位置（例: `"45% 42%"`）を調整。
4. **進め方**:
   - 事前の細かな確認で止めず、最後までレンダリング＋QA を通して **完成 MP4・フル解像度 `.card.png`・記入済み `request.json` シート** を一緒に提示する。

---

## 4. 実行と納品

```bash
.venv/bin/python agent/ssr_agent.py render --request request.json --json
```

出力 JSON の `"deliverable": true`（`"qa.overallPass": true`）を確認してから、以下の 4 点をユーザーへ納品してください。
1. 生成された MP4 ファイル（`outputMp4`）
2. 同時生成されたフル解像度カード静止画 PNG（`outputCardPng`）
3. 確定した `request.json` の内容（または `requestFile`）
4. QA 結果の要約（解像度・向き・LUFS・TruePeak・所要時間）
