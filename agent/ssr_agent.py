#!/usr/bin/env python3
"""
SSRGenerate-Lite — AI エージェント向け統合 CLI (`agent/ssr_agent.py`)

サブコマンド (§10 準拠):
  python agent/ssr_agent.py setup [--skip-check] [--json]
  python agent/ssr_agent.py capabilities [--json]
  python agent/ssr_agent.py render --request request.json [--output renders/out.mp4] [--json]
  python agent/ssr_agent.py omakase --photo photo.jpg [--style cute|cool] [--title ...] [--json]
  python agent/ssr_agent.py qa --file renders/SSR_xxx.mp4 [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
ASSETS_DIR = PROJECT_ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
GENERATED_DIR = ASSETS_DIR / "generated"
RENDERS_DIR = PROJECT_ROOT / "renders"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

UPSTREAM_COMMIT = "0df40bea4138a4390ea4027f1f730dd1d86f69fc"
UPSTREAM_RAW_BASE = f"https://raw.githubusercontent.com/treeturtlefall-arch/SSRGenetate/{UPSTREAM_COMMIT}/assets/fonts"

# 本家固定コミット (0df40be) のフォント一覧と SHA256 ハッシュ (§9.1 初回取得方式)
PINNED_FONTS: Dict[str, Tuple[str, int]] = {
    "Cinzel-VF.ttf": ("f4d83d34d1f6c741193e4acf4b3dff9531e5a67b6aa65228d00a7db72a4e0f34", 125468),
    "JetBrainsMono-VF.ttf": ("48715a42ec242c21e9f02692891e147d022299a52e48d5e413e1a942193ffeda", 187208),
    "Outfit-VF.ttf": ("fc7287273e66929776e2ba54f144fe699080bec29f61bf649d70d871468aeade", 110884),
    "ShipporiMincho-Bold.ttf": ("63bc4eddc74793f671c3ab827c5175e773ffbe569d0bf50ee65375ea9e3bc286", 8563788),
    "ShipporiMincho-ExtraBold.ttf": ("bdb787644b4b347e9a7efdd576f0d16ee4528cc9b5c86d23e06fa1a14ae0444c", 8563208),
    "YujiSyuku-Regular.ttf": ("82728ebafc8c97391e2dab633414a806f344b8e4e2227d307179f07b548fca61", 8430348),
    "ZenMaruGothic-Black.ttf": ("6bd74fe76cd39ee0ec18775c3661d845343fb3f6f8fa09a3076638417baf741f", 3710324),
    "ZenMaruGothic-Bold.ttf": ("fe24426b9c8b5523a0146a8235c8674eccf0493af354a53ec895c3596d9eb745", 3779008),
    "cinecaption.ttf": ("01e1d9620f8084fa58c33d8a0ac11d5ac5a11a29cfef8c623904ffde02e5ef26", 1665824),
}

VALID_PRESETS = ("royal-foil", "cute-pastel")
VALID_ORIENTATIONS = ("auto", "portrait", "landscape")
VALID_RING_MODES = ("rainbow", "cooldown", "gold")
VALID_MODES = ("sheet", "free", "omakase")
VALID_FITS = ("cover", "contain")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_hf_home(env: Dict[str, str]) -> Path:
    """HyperFrames 用のプライベート HOME を決定する（グループ書込可能な VM ワークスペースでは /tmp へ退避）"""
    explicit = env.get("SSR_HF_HOME")
    if explicit:
        return Path(explicit)
    try:
        root_mode = PROJECT_ROOT.stat().st_mode
        if root_mode & (stat.S_IWGRP | stat.S_IWOTH):
            uid = os.getuid() if hasattr(os, "getuid") else "user"
            return Path(tempfile.gettempdir()) / f"ssr_hf_home_{uid}"
    except OSError:
        pass
    return PROJECT_ROOT / ".hf_home"


def _prepare_runtime_env() -> Dict[str, str]:
    """Muse VM 等の制約に合わせて venv PATH・プライベート HOME (700)・大容量 TMPDIR を設定した環境変数を返す (§7)"""
    env = os.environ.copy()
    # resolve() すると Linux venv の python シンボリックリンクが /usr/bin に解決されるため parent のみ参照
    venv_bin = Path(sys.executable).parent
    path_sep = os.pathsep
    env["PATH"] = f"{venv_bin}{path_sep}{env.get('PATH', '')}"
    env["SSR_PYTHON"] = sys.executable

    if os.name != "nt":
        hf_home = _resolve_hf_home(env)
        hf_home.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(hf_home, 0o700)
        except OSError:
            pass
        env["SSR_HF_HOME"] = str(hf_home)
        env["HOME"] = str(hf_home)

        tmp_dir = Path(env.get("SSR_TMPDIR", str(PROJECT_ROOT / ".tmp")))
        tmp_dir.mkdir(parents=True, exist_ok=True)
        env["TMPDIR"] = str(tmp_dir)

    return env


def ensure_fonts(verbose: bool = True) -> List[str]:
    """不足または破損している同梱フォントを本家固定コミットから取得・SHA256 検証する"""
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    fetched: List[str] = []
    for fname, (expected_sha, _) in PINNED_FONTS.items():
        fpath = FONTS_DIR / fname
        if fpath.is_file() and _sha256_file(fpath) == expected_sha:
            continue
        url = f"{UPSTREAM_RAW_BASE}/{fname}"
        if verbose:
            print(f"[setup] Fetching font {fname} from upstream ({UPSTREAM_COMMIT[:7]})...", file=sys.stderr)
        req = urllib.request.Request(url, headers={"User-Agent": "SSRGenerate-Lite-Setup/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != expected_sha:
            raise RuntimeError(f"Font SHA256 mismatch for {fname}: expected {expected_sha}, got {actual_sha}")
        fpath.write_bytes(data)
        fetched.append(fname)
    return fetched


def inspect_photo(photo_path: Path) -> Tuple[int, int]:
    """画像を EXIF 回転補正込みで開いて (width, height) を返す。開けない場合は例外を送出する"""
    from PIL import Image, ImageOps

    with Image.open(photo_path) as im:
        im_t = ImageOps.exif_transpose(im)
        return im_t.size


def compute_deterministic_seed(photo_path: Path, title: str) -> int:
    """写真ファイル内容先頭64KB＋タイトルから再現可能な8桁シード値を算出する (§6)"""
    h = hashlib.sha256()
    with open(photo_path, "rb") as f:
        h.update(f.read(65536))
    h.update(title.encode("utf-8"))
    val = int(h.hexdigest()[:8], 16) % 90000000 + 10000000
    return val


def stage_photo_to_assets(src_path: Path) -> str:
    """入力写真を assets/ 配下に配置（または変換）し、プロジェクト相対パスを返す"""
    from PIL import Image, ImageOps

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        rel = src_path.resolve().relative_to(PROJECT_ROOT.resolve())
        rel_posix = rel.as_posix()
        if rel_posix.startswith("assets/") and src_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            return rel_posix
    except ValueError:
        pass

    digest = _sha256_file(src_path)[:10]
    dst_rel = f"assets/input_{digest}.jpg"
    dst_abs = PROJECT_ROOT / dst_rel
    if not dst_abs.is_file():
        with Image.open(src_path) as im:
            im_t = ImageOps.exif_transpose(im).convert("RGB")
            im_t.save(dst_abs, format="JPEG", quality=95)
    return dst_rel


def validate_and_normalize_request(raw_req: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """
    request.json を §5・§6 の規則で検証・正規化する。
    戻り値: (normalized_request, resolved_meta, warnings)
    """
    if not isinstance(raw_req, dict):
        raise ValueError("request must be a JSON object.")

    warnings: List[str] = []
    notes: List[str] = []
    if raw_req.get("agentNotes"):
        notes.append(str(raw_req["agentNotes"]).strip())

    raw_photo = str(raw_req.get("photo", "")).strip()
    if not raw_photo:
        raise ValueError("`photo` is required and cannot be empty.")
    photo_abs = Path(raw_photo) if Path(raw_photo).is_absolute() else (PROJECT_ROOT / raw_photo)
    if not photo_abs.is_file():
        raise ValueError(f"`photo` file does not exist: {raw_photo}")
    try:
        pw, ph = inspect_photo(photo_abs)
    except Exception as exc:
        raise ValueError(f"`photo` cannot be opened as a valid image ({raw_photo}): {exc}") from exc

    title = str(raw_req.get("title", "")).strip()
    if not title:
        raise ValueError("`title` is required and cannot be empty.")
    if len(title) > 14:
        warnings.append(f"title length ({len(title)} chars) exceeds 14 chars; auto-fit scaling will be applied.")

    mode = str(raw_req.get("mode", "sheet")).strip()
    if mode not in VALID_MODES:
        raise ValueError(f"`mode` must be one of {VALID_MODES}, got '{mode}'.")

    orientation = str(raw_req.get("orientation", "auto") or "auto").strip().lower()
    if orientation not in VALID_ORIENTATIONS:
        raise ValueError(f"`orientation` must be one of {VALID_ORIENTATIONS}, got '{orientation}'.")

    photo_is_landscape = pw > ph
    if orientation == "auto":
        resolved_ori = "landscape" if photo_is_landscape else "portrait"
        notes.append(f"orientation=auto -> resolved to {resolved_ori} (photo {pw}x{ph})")
    else:
        resolved_ori = orientation
        if resolved_ori == "landscape" and not photo_is_landscape:
            warnings.append(f"orientation is 'landscape' but input photo is portrait ({pw}x{ph}); cover crop will trim vertical area.")
        elif resolved_ori == "portrait" and photo_is_landscape:
            warnings.append(f"orientation is 'portrait' but input photo is landscape ({pw}x{ph}); cover crop will trim horizontal area.")

    typo_in = raw_req.get("typography", {})
    if not isinstance(typo_in, dict):
        typo_in = {}
    preset = str(typo_in.get("preset") or raw_req.get("preset") or "cute-pastel").strip()
    if preset not in VALID_PRESETS:
        raise ValueError(f"`typography.preset` must be one of {VALID_PRESETS}, got '{preset}'.")

    stars_raw = raw_req.get("stars", 0)
    try:
        stars = int(stars_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"`stars` must be an integer 0..5, got '{stars_raw}'.") from exc
    if not (0 <= stars <= 5):
        raise ValueError(f"`stars` must be between 0 and 5, got {stars}.")

    ring_mode = str(raw_req.get("resultRingMode", "rainbow") or "rainbow").strip()
    if ring_mode not in VALID_RING_MODES:
        raise ValueError(f"`resultRingMode` must be one of {VALID_RING_MODES}, got '{ring_mode}'.")

    photo_fit = str(raw_req.get("photoFit", "cover") or "cover").strip()
    if photo_fit not in VALID_FITS:
        raise ValueError(f"`photoFit` must be one of {VALID_FITS}, got '{photo_fit}'.")

    default_pos = "45% 42%" if (resolved_ori == "landscape" and preset == "cute-pastel") else "50% 35%"
    photo_pos = str(raw_req.get("photoPosition") or default_pos).strip()

    try:
        photo_zoom = float(raw_req.get("photoZoom", 1.05))
    except (TypeError, ValueError) as exc:
        raise ValueError("`photoZoom` must be a finite number.") from exc
    if not (0.25 <= photo_zoom <= 3.0):
        raise ValueError(f"`photoZoom` must be between 0.25 and 3.0, got {photo_zoom}.")

    if raw_req.get("seed") is not None and str(raw_req.get("seed")).strip() != "":
        seed = int(raw_req["seed"])
    else:
        seed = compute_deterministic_seed(photo_abs, title)
        notes.append(f"seed auto-generated from photo+title: {seed}")

    card_no = str(raw_req.get("cardNo", "")).strip()
    if not card_no:
        card_no = f"NO.{seed % 1000:03d}-SSR"
        notes.append(f"cardNo auto-numbered: {card_no}")

    subtitle = str(raw_req.get("subtitle", "")).strip()
    flavor = str(raw_req.get("flavor", "")).strip()
    rarity = str(raw_req.get("rarity", "SSR") or "SSR").strip()
    attr_badge = str(raw_req.get("attributeBadge", "")).strip()[:1]
    attr_label = str(raw_req.get("attributeLabel", "")).strip()

    staged_photo_rel = stage_photo_to_assets(photo_abs)

    if warnings:
        notes.extend(f"[WARN] {w}" for w in warnings)

    normalized: Dict[str, Any] = {
        "photo": staged_photo_rel,
        "title": title,
        "orientation": orientation,
        "subtitle": subtitle,
        "flavor": flavor,
        "rarity": rarity,
        "stars": stars,
        "attributeBadge": attr_badge,
        "attributeLabel": attr_label,
        "cardNo": cardNo if (cardNo := card_no) else "",
        "typography": {
            "preset": preset,
        },
        "photoFit": photo_fit,
        "photoPosition": photo_pos,
        "photoZoom": round(photo_zoom, 4),
        "resultRingMode": ring_mode,
        "seed": seed,
        "mode": mode,
        "agentNotes": " | ".join(n for n in notes if n),
    }

    output_w, output_h = (1280, 720) if resolved_ori == "landscape" else (720, 1280)
    resolved_meta = {
        "resolvedOrientation": resolved_ori,
        "outputWidth": output_w,
        "outputHeight": output_h,
        "fps": 24,
        "photoWidth": pw,
        "photoHeight": ph,
    }
    return normalized, resolved_meta, warnings


def cmd_setup(args: argparse.Namespace) -> int:
    t0 = time.perf_counter()
    env = _prepare_runtime_env()
    fetched_fonts = ensure_fonts(verbose=not args.json)

    build_res = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "build_all.py")],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=args.json,
        text=True,
        encoding="utf-8",
    )
    if build_res.returncode != 0:
        err_payload = {
            "status": "error",
            "stage": "build_assets",
            "returncode": build_res.returncode,
            "stdout": build_res.stdout if args.json else "",
            "stderr": build_res.stderr if args.json else "",
        }
        if args.json:
            print(json.dumps(err_payload, ensure_ascii=False, indent=2))
        return build_res.returncode

    check_passed = True
    check_skipped_reason: Optional[str] = None
    if not args.skip_check:
        if not (ASSETS_DIR / "photo.jpg").is_file():
            check_passed = False
            check_skipped_reason = "assets/photo.jpg not found; skipped hyperframes check"
        else:
            npx_bin = "npx.cmd" if os.name == "nt" else "npx"
            check_res = subprocess.run(
                [npx_bin, "--yes", "hyperframes@0.9.72", "check"],
                cwd=str(PROJECT_ROOT),
                env=env,
                capture_output=args.json,
                text=True,
                encoding="utf-8",
                shell=(os.name == "nt"),
            )
            check_passed = check_res.returncode == 0
            if not check_passed:
                err_payload = {
                    "status": "error",
                    "stage": "hyperframes_check",
                    "returncode": check_res.returncode,
                    "stdout": check_res.stdout if args.json else "",
                    "stderr": check_res.stderr if args.json else "",
                }
                if args.json:
                    print(json.dumps(err_payload, ensure_ascii=False, indent=2))
                return check_res.returncode

    elapsed = round(time.perf_counter() - t0, 2)
    payload: Dict[str, Any] = {
        "status": "ok",
        "fetchedFonts": fetched_fonts,
        "checkPassed": check_passed,
        "elapsedSec": elapsed,
    }
    if check_skipped_reason:
        payload["checkSkippedReason"] = check_skipped_reason
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[setup] Completed successfully in {elapsed}s (fetched fonts: {len(fetched_fonts)}, check: {check_passed})")
    return 0


def cmd_capabilities(args: argparse.Namespace) -> int:
    fonts_ready = all((FONTS_DIR / f).is_file() for f in PINNED_FONTS)
    manifest_ready = (GENERATED_DIR / "typo-manifest.js").is_file()
    se_ready = all((ASSETS_DIR / f).is_file() for f in ("se_summon.wav", "se_upgrade.wav", "se_fanfare.wav"))

    info = {
        "repository": "SSRGenerate-Lite",
        "upstreamCommit": UPSTREAM_COMMIT,
        "profile": "lite",
        "defaultOutput": {
            "portrait": {"width": 720, "height": 1280},
            "landscape": {"width": 1280, "height": 720},
            "fps": 24,
            "crf": 20,
            "durationSec": 16.0,
            "workers": int(os.environ.get("SSR_LITE_WORKERS", "3")),
        },
        "supportedPresets": list(VALID_PRESETS),
        "supportedOrientations": list(VALID_ORIENTATIONS),
        "supportedRingModes": list(VALID_RING_MODES),
        "supportedModes": list(VALID_MODES),
        "environment": {
            "os": platform.platform(),
            "python": sys.version.split()[0],
            "cpuCount": os.cpu_count() or 1,
            "fontsReady": fonts_ready,
            "generatedAssetsReady": manifest_ready,
            "audioAssetsReady": se_ready,
        },
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def _execute_render_pipeline(
    normalized_req: Dict[str, Any],
    resolved_meta: Dict[str, Any],
    warnings: List[str],
    explicit_output: Optional[str] = None,
    save_request_path: Optional[Path] = None,
    as_json: bool = True,
) -> int:
    t0 = time.perf_counter()
    env = _prepare_runtime_env()

    # 初回フォント・アセット未生成なら自動補完
    ensure_fonts(verbose=not as_json)
    if not (GENERATED_DIR / "opt_result_ring_rainbow.png").is_file() or not (ASSETS_DIR / "se_mix_16s.wav").is_file():
        subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "build_all.py")],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=as_json,
            text=True,
            encoding="utf-8",
            check=True,
        )

    # render_video.mjs へ渡す variables ペイロードを構築
    hf_vars: Dict[str, Any] = {
        "orientation": normalized_req["orientation"],
        "photo": normalized_req["photo"],
        "title": normalized_req["title"],
        "subtitle": normalized_req["subtitle"],
        "flavor": normalized_req["flavor"],
        "rarity": normalized_req["rarity"],
        "stars": normalized_req["stars"],
        "attributeBadge": normalized_req["attributeBadge"],
        "attributeLabel": normalized_req["attributeLabel"],
        "cardNo": normalized_req["cardNo"],
        "preset": normalized_req["typography"]["preset"],
        "photoFit": normalized_req["photoFit"],
        "photoPosition": normalized_req["photoPosition"],
        "photoZoom": normalized_req["photoZoom"],
        "resultRingMode": normalized_req["resultRingMode"],
        "seed": normalized_req["seed"],
    }

    tmp_dir = Path(env.get("TMPDIR", str(PROJECT_ROOT / ".tmp")))
    tmp_dir.mkdir(parents=True, exist_ok=True)
    vars_file = tmp_dir / f"agent_vars_{os.getpid()}_{int(time.time() * 1000)}.json"
    vars_file.write_text(json.dumps(hf_vars, ensure_ascii=False, indent=2), encoding="utf-8")

    RENDERS_DIR.mkdir(parents=True, exist_ok=True)
    before_mp4s = {p.resolve(): p.stat().st_mtime for p in RENDERS_DIR.glob("*.mp4")}

    cmd = ["node", str(SCRIPTS_DIR / "render_video.mjs"), "--variables-file", str(vars_file)]
    if explicit_output:
        cmd.extend(["-o", explicit_output])

    try:
        render_res = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=as_json,
            text=True,
            encoding="utf-8",
        )
    finally:
        if vars_file.is_file():
            try:
                vars_file.unlink()
            except OSError:
                pass

    if render_res.returncode != 0:
        err = {
            "status": "error",
            "stage": "render",
            "returncode": render_res.returncode,
            "request": normalized_req,
            "resolved": resolved_meta,
            "warnings": warnings,
            "stdout": render_res.stdout if as_json else "",
            "stderr": render_res.stderr if as_json else "",
            "elapsedSec": round(time.perf_counter() - t0, 2),
        }
        print(json.dumps(err, ensure_ascii=False, indent=2))
        return render_res.returncode

    # 出力された MP4 を特定
    if explicit_output:
        out_mp4 = Path(explicit_output) if Path(explicit_output).is_absolute() else (PROJECT_ROOT / explicit_output)
    else:
        after_mp4s = list(RENDERS_DIR.glob("*.mp4"))
        new_or_updated = [
            p for p in after_mp4s if p.resolve() not in before_mp4s or p.stat().st_mtime > before_mp4s[p.resolve()]
        ]
        target_list = new_or_updated if new_or_updated else after_mp4s
        target_list.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        out_mp4 = target_list[0]

    out_mp4_rel = out_mp4.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix() if out_mp4.is_file() else str(out_mp4)

    # 正規化済み request.json を保存
    req_out_path = save_request_path or out_mp4.with_name(f"{out_mp4.stem}.request.json")
    req_out_path.write_text(json.dumps(normalized_req, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        req_out_rel = req_out_path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        req_out_rel = str(req_out_path)

    # 定量 QA 実行 (§10 Step 4-5)
    from qa_video import analyze_video

    qa_report = analyze_video(out_mp4, check_audio=True)
    elapsed = round(time.perf_counter() - t0, 2)

    result_payload = {
        "status": "ok" if qa_report["overall_pass"] else "qa_failed",
        "deliverable": qa_report["overall_pass"],
        "outputMp4": out_mp4_rel,
        "requestFile": req_out_rel,
        "resolved": {
            "orientation": resolved_meta["resolvedOrientation"],
            "width": qa_report["stream"]["width"],
            "height": qa_report["stream"]["height"],
            "fps": qa_report["stream"]["fps"],
            "durationSec": qa_report["stream"]["duration"],
        },
        "request": normalized_req,
        "warnings": warnings,
        "qa": {
            "overallPass": qa_report["overall_pass"],
            "streamPass": qa_report["stream"]["pass"],
            "edgePaddingPass": qa_report["edge_padding"]["pass"],
            "grayVeilPass": qa_report["gray_veil"]["pass"],
            "vacuumPausePass": qa_report["vacuum_pause"]["pass"],
            "vacuumRatioPct": qa_report["vacuum_pause"]["ratio_pct"],
            "landingStallPass": qa_report["landing_stall"]["pass"],
            "tailFixedPass": qa_report["tail_result"]["layout_fixed_pass"],
            "tailMaxDiff": qa_report["tail_result"]["max_diff_122_148"],
            "audioPass": qa_report["audio"]["pass"],
            "integratedLufs": (qa_report["audio"]["details"] or {}).get("integrated_lufs"),
            "truePeakDbfs": (qa_report["audio"]["details"] or {}).get("true_peak_dbfs"),
        },
        "elapsedSec": elapsed,
    }
    print(json.dumps(result_payload, ensure_ascii=False, indent=2))
    return 0 if qa_report["overall_pass"] else 2


def cmd_render(args: argparse.Namespace) -> int:
    req_path = Path(args.request) if Path(args.request).is_absolute() else (PROJECT_ROOT / args.request)
    if not req_path.is_file():
        print(json.dumps({"status": "error", "stage": "validate", "message": f"Request file not found: {args.request}"}, ensure_ascii=False))
        return 1
    try:
        raw_req = json.loads(req_path.read_text(encoding="utf-8"))
        normalized_req, resolved_meta, warnings = validate_and_normalize_request(raw_req)
    except Exception as exc:
        print(json.dumps({"status": "error", "stage": "validate", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    return _execute_render_pipeline(
        normalized_req=normalized_req,
        resolved_meta=resolved_meta,
        warnings=warnings,
        explicit_output=args.output,
        as_json=args.json,
    )


def cmd_omakase(args: argparse.Namespace) -> int:
    style = (args.style or "cute").strip().lower()
    preset = "royal-foil" if style in ("cool", "royal", "royal-foil") else "cute-pastel"

    default_title = args.title or ("煌めきの覇者" if preset == "royal-foil" else "えがおの天使")
    default_sub = args.subtitle or ("「覚醒の刻」" if preset == "royal-foil" else "「満開の笑顔」")
    default_badge = args.badge if args.badge is not None else ("光" if preset == "royal-foil" else "愛")
    default_label = args.label if args.label is not None else ("LIGHT" if preset == "royal-foil" else "ANGEL")

    raw_req: Dict[str, Any] = {
        "photo": args.photo,
        "title": default_title,
        "orientation": args.orientation or "auto",
        "subtitle": default_sub,
        "flavor": args.flavor or "",
        "rarity": "SSR",
        "stars": args.stars if args.stars is not None else 0,
        "attributeBadge": default_badge,
        "attributeLabel": default_label,
        "typography": {"preset": preset},
        "mode": "omakase",
        "agentNotes": f"omakase style={style} -> preset={preset}",
    }
    if args.photo_position:
        raw_req["photoPosition"] = args.photo_position
    if args.seed is not None:
        raw_req["seed"] = args.seed

    try:
        normalized_req, resolved_meta, warnings = validate_and_normalize_request(raw_req)
    except Exception as exc:
        print(json.dumps({"status": "error", "stage": "validate", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    return _execute_render_pipeline(
        normalized_req=normalized_req,
        resolved_meta=resolved_meta,
        warnings=warnings,
        explicit_output=args.output,
        as_json=args.json,
    )


def cmd_qa(args: argparse.Namespace) -> int:
    from qa_video import analyze_video, print_report

    target = Path(args.file) if Path(args.file).is_absolute() else (PROJECT_ROOT / args.file)
    if not target.is_file():
        print(json.dumps({"status": "error", "stage": "qa", "message": f"MP4 file not found: {args.file}"}, ensure_ascii=False))
        return 1
    res = analyze_video(target, check_audio=True)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print_report(res)
    return 0 if res["overall_pass"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ssr-agent", description="SSRGenerate-Lite AI Agent CLI")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_setup = sub.add_parser("setup", help="Fetch fonts, build initial assets, and run preflight check")
    p_setup.add_argument("--skip-check", action="store_true", help="Skip hyperframes check after asset generation")
    p_setup.add_argument("--json", action="store_true", help="Output result as JSON")
    p_setup.set_defaults(func=cmd_setup)

    p_cap = sub.add_parser("capabilities", help="Return environment and supported schema capabilities as JSON")
    p_cap.add_argument("--json", action="store_true", default=True, help="Output as JSON")
    p_cap.set_defaults(func=cmd_capabilities)

    p_ren = sub.add_parser("render", help="Validate request.json, render 720p/24fps MP4, and run automated QA")
    p_ren.add_argument("--request", required=True, help="Path to request.json")
    p_ren.add_argument("-o", "--output", default=None, help="Explicit output MP4 path")
    p_ren.add_argument("--json", action="store_true", default=True, help="Output result as JSON")
    p_ren.set_defaults(func=cmd_render)

    p_oma = sub.add_parser("omakase", help="Generate SSR MP4 and filled request.json from photo + cool/cute style")
    p_oma.add_argument("--photo", required=True, help="Path to input photo")
    p_oma.add_argument("--style", default="cute", choices=["cute", "cool", "royal-foil", "cute-pastel"], help="Style choice")
    p_oma.add_argument("--orientation", default="auto", choices=["auto", "portrait", "landscape"])
    p_oma.add_argument("--title", default=None, help="Subject title decided by agent")
    p_oma.add_argument("--subtitle", default=None, help="Subject subtitle decided by agent")
    p_oma.add_argument("--flavor", default=None, help="Optional flavor text")
    p_oma.add_argument("--badge", default=None, help="1-char attribute badge")
    p_oma.add_argument("--label", default=None, help="Attribute label")
    p_oma.add_argument("--stars", type=int, default=0, help="Star count (0..5)")
    p_oma.add_argument("--photo-position", default=None, help="CSS object-position")
    p_oma.add_argument("--seed", type=int, default=None, help="Deterministic seed override")
    p_oma.add_argument("-o", "--output", default=None, help="Explicit output MP4 path")
    p_oma.add_argument("--json", action="store_true", default=True, help="Output result as JSON")
    p_oma.set_defaults(func=cmd_omakase)

    p_qa = sub.add_parser("qa", help="Run automated video & audio QA on an existing MP4")
    p_qa.add_argument("--file", required=True, help="Path to MP4 file")
    p_qa.add_argument("--json", action="store_true", default=True, help="Output result as JSON")
    p_qa.set_defaults(func=cmd_qa)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
