from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a Homebrew cask for Write Less.")
    parser.add_argument("--version", required=True, help="App version.")
    parser.add_argument("--sha256", required=True, help="SHA256 of the ZIP.")
    parser.add_argument("--homepage", required=True, help="Project homepage.")
    parser.add_argument("--output", required=True, help="Output cask path.")
    parser.add_argument("--url", default="", help="Full ZIP download URL (for smoke tests with file:// URLs).")
    return parser.parse_args()


def render_cask(version: str, sha256: str, homepage: str, url: str = "") -> str:
    if url:
        url_line = f'  url "{url}"'
    else:
        url_line = (
            f'  url "{homepage}/releases/download/v#{{version}}/WriteLess-#{{version}}.zip"'
        )
    return f'''cask "writeless" do
  version "{version}"
  sha256 "{sha256}"

{url_line}
  name "Write Less"
  desc "Speech-to-text macOS menubar app powered by Whisper"
  homepage "{homepage}"

  app "Write Less.app"

  zap trash: [
    "~/Library/Application Support/dev.romus.app.writeless",
  ]
end
'''


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_cask(
            version=args.version,
            sha256=args.sha256,
            homepage=args.homepage,
            url=args.url,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
