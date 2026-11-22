/**
 * SSRGenerate — スマート・プリフライト＆レンダリングラッパー (renders/SSR_{preset}_{YYYYMMDD}.mp4)
 *
 * - card-config.js と CLI 引数 (--variables '{...}') をマージし、
 *   assets/generated/typo-manifest.js の source スナップショットと差分を比較する。
 * - テキスト・プリセット・4軸上書き・写真/シード変更がある場合は、レンダリング直前に
 *   python scripts/render_typography.py --overrides-stdin を自動実行して物理箔 PNG とビネットを更新する。
 * - 出力ファイル名 renders/SSR_{preset}_{YYYYMMDD}.mp4 も上書き後のプリセット名に同期させる。
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "..");
const RENDERS_DIR = path.join(PROJECT_ROOT, "renders");
const CONFIG_PATH = path.join(PROJECT_ROOT, "card-config.js");
const MANIFEST_PATH = path.join(PROJECT_ROOT, "assets", "generated", "typo-manifest.js");

const VALID_PRESETS = new Set([
  "royal-foil",
  "cute-pastel",
  "foil-brush",
  "handwritten-sign",
  "crisp-emboss",
]);

function roundTo(val, digits) {
  const m = 10 ** digits;
  return Math.round(val * m) / m;
}

function stableNormalize(val) {
  if (Array.isArray(val)) return val.map(stableNormalize);
  if (val && typeof val === "object") {
    const out = {};
    for (const k of Object.keys(val).sort()) {
      out[k] = stableNormalize(val[k]);
    }
    return out;
  }
  return val;
}

function deepEqual(a, b) {
  return JSON.stringify(stableNormalize(a)) === JSON.stringify(stableNormalize(b));
}

function loadCardConfig() {
  if (!fs.existsSync(CONFIG_PATH)) return {};
  try {
    const ctx = { window: {} };
    vm.runInNewContext(fs.readFileSync(CONFIG_PATH, "utf8"), ctx);
    return ctx.window?.SSR_CARD_CONFIG && typeof ctx.window.SSR_CARD_CONFIG === "object"
      ? ctx.window.SSR_CARD_CONFIG
      : {};
  } catch {
    return {};
  }
}

function loadTypoManifest() {
  if (!fs.existsSync(MANIFEST_PATH)) return null;
  try {
    const ctx = { window: {} };
    vm.runInNewContext(fs.readFileSync(MANIFEST_PATH, "utf8"), ctx);
    return ctx.window?.SSR_TYPO_MANIFEST || null;
  } catch {
    return null;
  }
}

function loadVariablesPayload(rawArg, label) {
  let text = rawArg;
  const trimmed = rawArg.trim();
  if (!trimmed.startsWith("{")) {
    const filePath = path.isAbsolute(trimmed) ? trimmed : path.resolve(PROJECT_ROOT, trimmed);
    if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
      text = fs.readFileSync(filePath, "utf8");
    }
  }
  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("must be a JSON object");
    }
    return parsed;
  } catch (err) {
    console.error(`[error] Invalid ${label} JSON: ${err.message}`);
    process.exit(1);
  }
}

function parseCliArgs(argv) {
  let cliVars = {};
  let dryRun = false;
  let forceTypo = false;
  let noAutoTypo = false;
  let noFastAudio = false;
  let explicitOutput = null;
  const passthroughArgs = [];

  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--dry-run") {
      dryRun = true;
      continue;
    }
    if (a === "--force-typo") {
      forceTypo = true;
      continue;
    }
    if (a === "--no-auto-typo") {
      noAutoTypo = true;
      continue;
    }
    if (a === "--no-fast-audio") {
      noFastAudio = true;
      continue;
    }
    if (a === "-o" || a === "--output") {
      if (i + 1 >= argv.length) {
        console.error(`[error] ${a} requires an argument.`);
        process.exit(1);
      }
      explicitOutput = argv[i + 1];
      i += 1;
      continue;
    }
    if (a.startsWith("--output=")) {
      explicitOutput = a.slice("--output=".length);
      continue;
    }
    if (a === "--variables" || a.startsWith("--variables=") || a === "--variables-file" || a.startsWith("--variables-file=")) {
      const isFileFlag = a === "--variables-file" || a.startsWith("--variables-file=");
      const flagName = isFileFlag ? "--variables-file" : "--variables";
      let rawVal = "";
      if (a === flagName) {
        if (i + 1 >= argv.length) {
          console.error(`[error] ${flagName} requires an argument.`);
          process.exit(1);
        }
        rawVal = argv[i + 1];
        i += 1;
      } else {
        rawVal = a.slice(`${flagName}=`.length);
      }
      const parsed = loadVariablesPayload(rawVal, flagName);
      cliVars = { ...cliVars, ...parsed };
      continue;
    }
    passthroughArgs.push(a);
  }

  return { cliVars, dryRun, forceTypo, noAutoTypo, noFastAudio, explicitOutput, passthroughArgs };
}

function applyCliOverrides(baseCfg, overrides) {
  if (!overrides || typeof overrides !== "object") return baseCfg;
  const out = { ...baseCfg };
  const typo = baseCfg.typography && typeof baseCfg.typography === "object" ? { ...baseCfg.typography } : {};

  const strKeys = [
    "orientation",
    "photo",
    "photoFit",
    "photoPosition",
    "rarity",
    "attribute",
    "attributeBadge",
    "attributeLabel",
    "subtitle",
    "title",
    "flavor",
    "cardNo",
    "resultRingMode",
  ];
  for (const k of strKeys) {
    if (Object.prototype.hasOwnProperty.call(overrides, k) && overrides[k] !== null && overrides[k] !== undefined) {
      const s = String(overrides[k]);
      if (k === "orientation" && !s.trim()) continue;
      out[k] = s;
    }
  }

  if (Object.prototype.hasOwnProperty.call(overrides, "photoZoom") && overrides.photoZoom !== null && String(overrides.photoZoom).trim() !== "") {
    const n = Number(overrides.photoZoom);
    if (Number.isFinite(n)) out.photoZoom = n;
  }
  for (const ik of ["stars", "seed"]) {
    if (Object.prototype.hasOwnProperty.call(overrides, ik) && overrides[ik] !== null && String(overrides[ik]).trim() !== "") {
      const n = Number.parseInt(String(overrides[ik]), 10);
      if (Number.isFinite(n)) out[ik] = n;
    }
  }

  if (typeof overrides.preset === "string" && overrides.preset.trim() !== "") {
    typo.preset = overrides.preset.trim();
  }
  if (overrides.typography && typeof overrides.typography === "object" && !Array.isArray(overrides.typography)) {
    for (const [tk, tv] of Object.entries(overrides.typography)) {
      if (tv !== null && tv !== undefined) {
        typo[tk] = tv;
      }
    }
  }

  out.typography = typo;
  return out;
}

function parseAttributeParts(cfg) {
  const hasSplit = Object.prototype.hasOwnProperty.call(cfg, "attributeBadge") || Object.prototype.hasOwnProperty.call(cfg, "attributeLabel");
  if (hasSplit) {
    let rawB = String(cfg.attributeBadge ?? "").trim();
    let rawL = String(cfg.attributeLabel ?? "").trim();
    if (rawB === "__EMPTY__" || rawB.toLowerCase() === "none") rawB = "";
    if (rawL === "__EMPTY__" || rawL.toLowerCase() === "none") rawL = "";
    const b = Array.from(rawB)[0] || "";
    const l = rawL;
    if (!b && !l) return "";
    return b && l ? `${b} / ${l}` : l || b;
  }

  const clean = String(cfg.attribute ?? "").trim();
  if (!clean || clean === "__EMPTY__" || clean.toLowerCase() === "none") return "";
  const parts = clean.replace(/／/g, "/").split("/").map((p) => p.trim()).filter(Boolean);
  if (parts.length >= 2) {
    const stripped = parts[0].replace(/属性/g, "").trim();
    const b = Array.from(stripped || parts[0])[0] || Array.from(parts[0])[0] || "";
    return b ? `${b} / ${parts[1]}` : parts[1];
  }
  const stripped = clean.replace(/属性/g, "").trim();
  const b = Array.from(stripped || clean)[0] || Array.from(clean)[0] || "";
  return b ? `${b} / ${clean}` : clean;
}

function resolvePhotoPath(photoRel) {
  const raw = String(photoRel || "assets/photo.jpg").trim();
  if (path.isAbsolute(raw)) return raw;
  return path.join(PROJECT_ROOT, raw.replace(/^[./\\]+/, ""));
}

function buildExpectedSource(cfg) {
  const typo = cfg.typography && typeof cfg.typography === "object" ? cfg.typography : {};
  let presetName = typeof typo.preset === "string" && typo.preset.trim() ? typo.preset.trim() : "royal-foil";
  if (!VALID_PRESETS.has(presetName)) presetName = "royal-foil";

  const wobbleVal = typo.wobble !== undefined && typo.wobble !== null ? Number(typo.wobble) : 28;
  const foilGlitter = typo.foilGlitter !== undefined && typo.foilGlitter !== null ? Number(typo.foilGlitter) : 0.42;
  const paperGrain = typo.paperGrain !== undefined && typo.paperGrain !== null ? Number(typo.paperGrain) : 0.35;
  const seed = typo.seed !== undefined && typo.seed !== null
    ? Number.parseInt(String(typo.seed), 10)
    : cfg.seed !== undefined && cfg.seed !== null
      ? Number.parseInt(String(cfg.seed), 10)
      : 20261120;

  const photoRel = String(cfg.photo ?? "assets/photo.jpg").trim().replace(/\\/g, "/") || "assets/photo.jpg";
  const photoAbs = resolvePhotoPath(photoRel);
  let photoSize = -1;
  let photoMtimeSec = -1;
  if (fs.existsSync(photoAbs)) {
    try {
      const st = fs.statSync(photoAbs);
      if (st.isFile()) {
        photoSize = Number(st.size);
        photoMtimeSec = Math.floor(st.mtimeMs / 1000);
      }
    } catch {
      // keep -1
    }
  }

  const rawZoom = cfg.photoZoom !== undefined && cfg.photoZoom !== null ? Number(cfg.photoZoom) : 1.05;
  const zoomVal = Number.isFinite(rawZoom) ? roundTo(rawZoom, 4) : 1.05;

  const orientationRaw = String(cfg.orientation ?? "portrait").trim().toLowerCase() || "portrait";

  return {
    orientationRaw,
    preset: presetName,
    seed,
    texts: {
      ssr: String(cfg.rarity ?? "SSR").trim(),
      attribute: parseAttributeParts(cfg).trim(),
      subtitle: String(cfg.subtitle ?? "").trim(),
      title: String(cfg.title ?? "").trim(),
      flavor: String(cfg.flavor ?? "").trim(),
      cardNo: String(cfg.cardNo ?? "").trim(),
    },
    typography: {
      layout: typo.layout ?? null,
      palette: typo.palette ?? null,
      font: typo.font ?? null,
      style: typo.style ?? null,
      wobble: roundTo(wobbleVal, 3),
      foilGlitter: roundTo(foilGlitter, 3),
      paperGrain: roundTo(paperGrain, 3),
    },
    photo: {
      path: photoRel,
      size: photoSize,
      mtimeSec: photoMtimeSec,
      fit: String(cfg.photoFit ?? "cover").trim() || "cover",
      position: String(cfg.photoPosition ?? "50% 35%").trim() || "50% 35%",
      zoom: zoomVal,
    },
  };
}

function readIndexHtmlResolution() {
  const indexPath = path.join(PROJECT_ROOT, "index.html");
  if (!fs.existsSync(indexPath)) return "portrait";
  const m = fs.readFileSync(indexPath, "utf8").match(/data-(?:orientation|resolution)="(portrait|landscape)"/);
  return m ? m[1] : "portrait";
}

function checkTypoSyncStatus(expectedSource, manifest) {
  const reasons = [];
  let needsLayoutRebuild = false;

  if (!manifest) {
    reasons.push("manifest-missing");
    return { needsSync: true, needsLayoutRebuild: true, reasons };
  }
  if (manifest.schemaVersion !== 2 || !manifest.source) {
    reasons.push("manifest-schema-outdated");
    return { needsSync: true, needsLayoutRebuild: true, reasons };
  }

  const actual = manifest.source;
  const manifestOri = manifest.dimensions?.orientation || "portrait";
  const htmlOri = readIndexHtmlResolution();

  if (expectedSource.orientationRaw !== (actual.orientationRaw ?? "portrait")) {
    reasons.push(`orientation(${actual.orientationRaw ?? "portrait"}->${expectedSource.orientationRaw})`);
    needsLayoutRebuild = true;
  }
  if (expectedSource.orientationRaw === "auto" && !deepEqual(expectedSource.photo, actual.photo)) {
    reasons.push("auto-orientation-photo-changed");
    needsLayoutRebuild = true;
  }
  if (htmlOri !== manifestOri) {
    reasons.push(`html-resolution-mismatch(${htmlOri}!=${manifestOri})`);
    needsLayoutRebuild = true;
  }
  if (expectedSource.preset !== actual.preset) reasons.push(`preset(${actual.preset}->${expectedSource.preset})`);
  if (expectedSource.seed !== actual.seed) reasons.push("seed");

  for (const k of Object.keys(expectedSource.texts)) {
    if (expectedSource.texts[k] !== (actual.texts?.[k] ?? "")) {
      reasons.push(`texts.${k}`);
    }
  }
  if (!deepEqual(expectedSource.typography, actual.typography)) {
    reasons.push("typography");
  }
  if (!deepEqual(expectedSource.photo, actual.photo)) {
    reasons.push("photo");
  }

  const items = manifest.items && typeof manifest.items === "object" ? manifest.items : {};
  for (const [k, entry] of Object.entries(items)) {
    if (entry?.src) {
      const abs = path.join(PROJECT_ROOT, String(entry.src));
      if (!fs.existsSync(abs)) {
        reasons.push(`missing-png:${k}`);
      }
    }
  }

  return { needsSync: reasons.length > 0, needsLayoutRebuild, reasons };
}

function formatLocalDate(now = new Date()) {
  const y = String(now.getFullYear());
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}${m}${d}`;
}

function resolveOutputPath(preset) {
  fs.mkdirSync(RENDERS_DIR, { recursive: true });
  const safePreset = preset.replace(/[^a-zA-Z0-9_-]/g, "_");
  const dateStr = formatLocalDate();
  const base = `SSR_${safePreset}_${dateStr}`;
  let candidate = path.join(RENDERS_DIR, `${base}.mp4`);
  let seq = 2;
  while (fs.existsSync(candidate)) {
    candidate = path.join(RENDERS_DIR, `${base}_${seq}.mp4`);
    seq += 1;
  }
  return path.relative(PROJECT_ROOT, candidate).replace(/\\/g, "/");
}

const { cliVars, dryRun, forceTypo, noAutoTypo, noFastAudio, explicitOutput, passthroughArgs } = parseCliArgs(process.argv.slice(2));
const hasExplicitOutput = Boolean(explicitOutput);
const baseCfg = loadCardConfig();
const effectiveCfg = applyCliOverrides(baseCfg, cliVars);
const expectedSource = buildExpectedSource(effectiveCfg);
const manifest = loadTypoManifest();
const syncStatus = checkTypoSyncStatus(expectedSource, manifest);

function encodeVariablesForHyperFrames(vars) {
  if (!vars || typeof vars !== "object") return {};
  const out = {};
  for (const [k, v] of Object.entries(vars)) {
    if (typeof v === "string" && v.trim() === "") {
      out[k] = "__EMPTY__";
    } else {
      out[k] = v;
    }
  }
  return out;
}

const preset = expectedSource.preset;
const autoOutput = resolveOutputPath(preset);
const finalOutput = explicitOutput || autoOutput;
const preMixedAudioPath = path.join(PROJECT_ROOT, "assets", "se_mix_16s.wav");
const useFastAudio = !noFastAudio && process.env.SSR_FAST_AUDIO !== "0" && fs.existsSync(preMixedAudioPath);

const liteFps = process.env.SSR_LITE_FPS || "24";
const liteCrf = process.env.SSR_LITE_CRF || "20";
const liteQuality = process.env.SSR_LITE_QUALITY || "standard";
const liteWorkers = process.env.SSR_LITE_WORKERS || "3";

const cmdArgs = [
  "--yes",
  "hyperframes@0.9.72",
  "render",
  "-f",
  String(liteFps),
  "-q",
  String(liteQuality),
  "--crf",
  String(liteCrf),
  "--no-low-memory-mode",
  "-w",
  String(liteWorkers),
];
if (!useFastAudio || dryRun) {
  cmdArgs.push("-o", finalOutput);
}
const hasCliVars = Object.keys(cliVars).length > 0;
const encodedVars = hasCliVars ? encodeVariablesForHyperFrames(cliVars) : null;
if (hasCliVars && dryRun) {
  cmdArgs.push("--variables", JSON.stringify(encodedVars));
}
cmdArgs.push(...passthroughArgs);

const shouldSyncTypo = !noAutoTypo && (forceTypo || syncStatus.needsSync);
const syncReasonText = forceTypo ? ["forced", ...syncStatus.reasons] : syncStatus.reasons;

if (dryRun) {
  console.log(`[dry-run] preset=${preset}`);
  console.log(`[dry-run] output=${finalOutput}`);
  console.log(`[dry-run] fastAudio=${useFastAudio ? "enabled (assets/se_mix_16s.wav + ffmpeg mux)" : "disabled"}`);
  console.log(
    `[dry-run] typoSync=${shouldSyncTypo ? `needs-sync (${syncReasonText.join(", ")})` : noAutoTypo ? "skipped (--no-auto-typo)" : "up-to-date"}`
  );
  if (shouldSyncTypo) {
    console.log(`[dry-run] preflight: python scripts/render_typography.py --overrides-stdin`);
    if (forceTypo || syncStatus.needsLayoutRebuild) {
      console.log(`[dry-run] layout-sync: python scripts/render_material.py && python scripts/render_optics.py (if orientation changed)`);
    }
  }
  console.log(`[dry-run] command: npx ${cmdArgs.join(" ")}`);
  process.exit(0);
}

if (shouldSyncTypo) {
  const envWithOverrides = {
    ...process.env,
    SSR_CARD_CONFIG_OVERRIDES: JSON.stringify(cliVars),
    SSR_RESOLVED_CONFIG_JSON: JSON.stringify(effectiveCfg),
  };

  const pythonBin = process.env.SSR_PYTHON || "python";
  console.log(`[typo-sync] Regenerating typography (${syncReasonText.join(", ")})...`);
  const pyRes = spawnSync(pythonBin, ["scripts/render_typography.py", "--overrides-stdin"], {
    cwd: PROJECT_ROOT,
    input: JSON.stringify(cliVars),
    env: envWithOverrides,
    encoding: "utf8",
    stdio: ["pipe", "inherit", "inherit"],
    shell: false,
  });
  if (pyRes.error) {
    console.error(`[typo-sync] Failed to spawn python: ${pyRes.error.message}`);
    process.exit(1);
  }
  if ((pyRes.status ?? 1) !== 0) {
    console.error(`[typo-sync] render_typography.py exited with status ${pyRes.status}`);
    process.exit(pyRes.status ?? 1);
  }

  const updatedManifest = loadTypoManifest();
  const prevOri = manifest?.dimensions?.orientation || "portrait";
  const nextOri = updatedManifest?.dimensions?.orientation || "portrait";
  if (forceTypo || syncStatus.needsLayoutRebuild || prevOri !== nextOri) {
    console.log(`[layout-sync] Ensuring material & optics assets for orientation=${nextOri}...`);
    const layoutScripts = [
      ["scripts/render_material.py"],
      ["scripts/render_optics.py", "--cutin-only"],
    ];
    for (const [script, ...args] of layoutScripts) {
      const r = spawnSync(pythonBin, [script, ...args], {
        cwd: PROJECT_ROOT,
        env: envWithOverrides,
        stdio: "inherit",
        shell: false,
      });
      if (r.error) {
        console.error(`[layout-sync] Failed to spawn python (${script}): ${r.error.message}`);
        process.exit(1);
      }
      if ((r.status ?? 1) !== 0) {
        console.error(`[layout-sync] ${script} exited with status ${r.status}`);
        process.exit(r.status ?? 1);
      }
    }
  }
} else {
  console.log(`[typo-sync] up-to-date (${preset})`);
}

console.log(`[render] preset=${preset} -> ${hasExplicitOutput ? "(custom -o)" : autoOutput}`);

const isWin = process.platform === "win32";

// Muse VM 等でのプライベート HOME 権限 700 再適用 ＆ 大容量 TMPDIR 自動確保 (§7)
const childEnv = { ...process.env };
if (!isWin) {
  let hfHomeDir = process.env.SSR_HF_HOME;
  if (!hfHomeDir) {
    // HF HOME の選択方針は agent/ssr_agent.py の _resolve_hf_home と同一:
    // HyperFrames は「配置先自身と全ての親がグループ/他者書込不可 (sticky な /tmp 等は可)」と
    // Chrome ダウンロード用の空き容量 (約 512 MB 以上) を要求するため、候補を優先順に
    // プライベート性と空き容量 (1 GiB 以上、キャッシュ済みは除く) で検証して選ぶ。
    const HF_MIN_FREE_BYTES = 1024 ** 3;
    const hfChainIsPrivate = (p) => {
      let cur = p;
      while (true) {
        try {
          const mode = fs.statSync(cur).mode;
          if ((mode & 0o022) !== 0 && (mode & 0o1000) === 0) return false;
        } catch {
          // 未作成の途中ディレクトリは mkdir 時に標準権限で作られるため検査対象外
        }
        const parent = path.dirname(cur);
        if (parent === cur) return true;
        cur = parent;
      }
    };
    const hfFreeSpaceOk = (p) => {
      if (fs.existsSync(path.join(p, ".cache", "hyperframes"))) return true;
      let probe = p;
      while (!fs.existsSync(probe)) {
        const parent = path.dirname(probe);
        if (parent === probe) return false;
        probe = parent;
      }
      try {
        const st = fs.statfsSync(probe);
        return st.bavail * st.bsize >= HF_MIN_FREE_BYTES;
      } catch {
        return false;
      }
    };
    const uid = typeof process.getuid === "function" ? process.getuid() : "user";
    const hfCandidates = [path.join(PROJECT_ROOT, ".hf_home")];
    const cacheBases = [];
    if (process.env.XDG_CACHE_HOME) cacheBases.push(process.env.XDG_CACHE_HOME);
    if (process.env.HOME) cacheBases.push(path.join(process.env.HOME, ".cache"));
    try {
      // $HOME が共有ツリーを指す環境でも passwd 上の本来のホームは候補に加える
      cacheBases.push(path.join(os.userInfo().homedir, ".cache"));
    } catch {
      // ignore userInfo errors
    }
    for (const base of cacheBases) {
      const cand = path.join(base, "ssr-generate-lite", "hf_home");
      if (!hfCandidates.includes(cand)) hfCandidates.push(cand);
    }
    if (fs.existsSync("/var/tmp")) {
      const cand = path.join("/var/tmp", `ssr_hf_home_${uid}`);
      if (!hfCandidates.includes(cand)) hfCandidates.push(cand);
    }
    const tmpCand = path.join(os.tmpdir(), `ssr_hf_home_${uid}`);
    if (!hfCandidates.includes(tmpCand)) hfCandidates.push(tmpCand);

    const skipped = [];
    for (const cand of hfCandidates) {
      if (!hfChainIsPrivate(cand)) {
        skipped.push(`${cand}（親ディレクトリがグループ/他者書込可能）`);
        continue;
      }
      if (!hfFreeSpaceOk(cand)) {
        skipped.push(`${cand}（空き容量が 1 GiB 未満）`);
        continue;
      }
      hfHomeDir = cand;
      if (skipped.length > 0) {
        console.log(`[env] HF HOME: ${cand}（skipped: ${skipped.join("; ")}）`);
      }
      break;
    }
    if (!hfHomeDir) {
      console.error(
        "HyperFrames 用のプライベート HOME を確保できませんでした。" +
          `候補と却下理由: ${skipped.join("; ")}。` +
          "環境変数 SSR_HF_HOME に「親ディレクトリまで含めてグループ/他者書込不可で、空き容量 1 GiB 以上」のディレクトリを指定してください。"
      );
      process.exit(1);
    }
  }
  try {
    // mkdir 前に存在しなかった途中ディレクトリは作成後に 700 へ寄せる
    // (umask が緩い環境では mkdir がグループ書込可能な中間ディレクトリを作り、
    //  HyperFrames のプライベート性チェックに落ちるため。ssr_agent.py と同じ対処)
    const missingDirs = [];
    let probeDir = hfHomeDir;
    while (!fs.existsSync(probeDir)) {
      missingDirs.push(probeDir);
      const parent = path.dirname(probeDir);
      if (parent === probeDir) break;
      probeDir = parent;
    }
    fs.mkdirSync(hfHomeDir, { recursive: true });
    for (const created of missingDirs) {
      try {
        fs.chmodSync(created, 0o700);
      } catch {
        // ignore chmod errors
      }
    }
    fs.chmodSync(hfHomeDir, 0o700);
    childEnv.SSR_HF_HOME = hfHomeDir;
    childEnv.HOME = hfHomeDir;
  } catch {
    // ignore mkdir/chmod errors
  }
  const customTmpDir = process.env.SSR_TMPDIR || path.join(PROJECT_ROOT, ".tmp");
  try {
    fs.mkdirSync(customTmpDir, { recursive: true });
    childEnv.TMPDIR = customTmpDir;
  } catch {
    // fallback to system tmpdir
  }
}

const tmpBase = childEnv.TMPDIR && fs.existsSync(childEnv.TMPDIR) ? childEnv.TMPDIR : os.tmpdir();
let tmpVarsPath = null;
if (hasCliVars) {
  tmpVarsPath = path.join(tmpBase, `ssr-hf-vars-${process.pid}-${Date.now()}.json`);
  fs.writeFileSync(tmpVarsPath, JSON.stringify(encodedVars), "utf8");
  cmdArgs.push("--variables", tmpVarsPath);
}

let tmpNoAudioHtmlName = null;
let tmpNoAudioHtmlPath = null;
let tmpVideoPath = null;
if (useFastAudio) {
  const indexHtmlPath = path.join(PROJECT_ROOT, "index.html");
  const indexHtmlText = fs.readFileSync(indexHtmlPath, "utf8");
  const strippedHtmlText = indexHtmlText.replace(/<audio\b[^>]*>[\s\S]*?<\/audio>/gi, "");
  tmpNoAudioHtmlName = `hf_noaudio_${process.pid}_${Date.now()}.html`;
  tmpNoAudioHtmlPath = path.join(PROJECT_ROOT, tmpNoAudioHtmlName);
  fs.writeFileSync(tmpNoAudioHtmlPath, strippedHtmlText, "utf8");

  tmpVideoPath = path.join(tmpBase, `ssr-hf-video-${process.pid}-${Date.now()}.mp4`);
  cmdArgs.push("--composition", tmpNoAudioHtmlName, "-o", tmpVideoPath);
  console.log(`[audio-fast] Bypassing HyperFrames audio mix -> muxing pre-mixed assets/se_mix_16s.wav via ffmpeg`);
}

let res;
let finalStatus = 1;
try {
  res = spawnSync(isWin ? "npx.cmd" : "npx", cmdArgs, {
    cwd: PROJECT_ROOT,
    env: childEnv,
    stdio: "inherit",
    shell: isWin,
  });
  finalStatus = res.status ?? 1;

  if (finalStatus === 0 && useFastAudio) {
    const finalAbsOutput = path.isAbsolute(finalOutput) ? finalOutput : path.resolve(PROJECT_ROOT, finalOutput);
    fs.mkdirSync(path.dirname(finalAbsOutput), { recursive: true });
    const muxRes = spawnSync(
      "ffmpeg",
      [
        "-y",
        "-i",
        tmpVideoPath,
        "-i",
        preMixedAudioPath,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-loglevel",
        "warning",
        finalAbsOutput,
      ],
      {
        cwd: PROJECT_ROOT,
        env: childEnv,
        stdio: "inherit",
        shell: false,
      }
    );
    if (muxRes.error) {
      console.error(`[audio-fast] Failed to spawn ffmpeg: ${muxRes.error.message}`);
      finalStatus = 1;
    } else {
      finalStatus = muxRes.status ?? 1;
      if (finalStatus === 0) {
        console.log(`[audio-fast] Muxed complete -> ${finalOutput}`);
      }
    }
  }
} finally {
  for (const p of [tmpVarsPath, tmpNoAudioHtmlPath, tmpVideoPath]) {
    if (p && fs.existsSync(p)) {
      try {
        fs.unlinkSync(p);
      } catch {
        // ignore cleanup error
      }
    }
  }
}

process.exit(finalStatus);
