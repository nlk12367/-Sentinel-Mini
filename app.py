"""Launch with `python app.py`; the runtime uses only the Python standard library."""

import argparse
import json
import threading
import webbrowser
from pathlib import Path

from sentinel.core import audit
from sentinel.demo import make_demo
from sentinel.reporting import markdown
from sentinel.store import Store
from sentinel.web import make_server

ROOT = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    """Define the shared web and CLI entrypoint options."""
    parser = argparse.ArgumentParser(description="Sentinel Mini — Python 網站設定檢查")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--demo-port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--target", help="CLI 模式目標 URL")
    parser.add_argument("--authorized", action="store_true", help="確認擁有目標檢查權限")
    parser.add_argument("--ai", action="store_true", help="CLI 使用模型模式")
    parser.add_argument("--backend", choices=["codex", "compatible"], default="codex")
    parser.add_argument("--goal", default="檢查網站安全標頭、TLS 與 Cookie 設定")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "latest.json")
    return parser


def run_cli(args: argparse.Namespace) -> int:
    """Run one audit, export both report formats, and return its exit code."""
    report = audit(args.target, args.goal, use_ai=args.ai, backend=args.backend)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(report["summary"])
    print(f"Report: {args.out.resolve()}")
    return 0 if report["state"] == "completed" else 1


def run_web(args: argparse.Namespace) -> None:
    """Stop the demo thread before closing the owned server sockets."""
    with make_demo(args.demo_port) as demo:
        demo_url = f"http://127.0.0.1:{demo.server_port}/"
        store = Store(ROOT / "data" / "runs.sqlite3")
        with make_server(args.port, store, demo_url) as server:
            demo_thread = threading.Thread(target=demo.serve_forever, daemon=True)
            demo_thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}"
                print(f"Sentinel Mini: {url}\nDemo target: {demo_url}\nCtrl+C to stop.", flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                server.serve_forever()
            finally:
                demo.shutdown()
                demo_thread.join(timeout=5)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.target:
        if not args.authorized:
            parser.error("CLI 需加上 --authorized 確認目標權限。")
        return run_cli(args)
    try:
        run_web(args)
    except OSError as exc:
        parser.exit(1, f"啟動失敗：{exc}。可用 --port / --demo-port 指定其他埠。\n")
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
