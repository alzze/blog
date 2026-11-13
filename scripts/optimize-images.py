#!/usr/bin/env python3

import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import unquote


MAX_WIDTH = 1000
WEBP_QUALITY = 85
SOURCE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

MARKDOWN_TOKEN = re.compile(
    r"(?P<code>^[ ]{0,3}(?P<fence>(?P<marker>`|~)(?P=marker){2,})[^\r\n]*\r?\n"
    r".*?(?:^[ ]{0,3}(?P=fence)(?P=marker)*[ \t]*(?:\r?\n|$)|\Z)"
    r"|(?P<ticks>`+)(?!`).*?(?<!`)(?P=ticks)(?!`)"
    r"|^(?: {4}|\t)[^\r\n]*(?:\r?\n|$))"
    r"|(?P<link>(?<!\\)\]\([ \t]*)"
    r"(?P<inline><[^>\r\n]+>|(?:\\.|[^()\s\\]|\((?:\\.|[^()\s\\])*\))+)"
    r"|(?P<definition>^[ ]{0,3}\[(?:\\.|[^\]\\\r\n])+\]:[ \t]*)"
    r"(?P<reference><[^>\r\n]+>|[^\s]+)",
    re.MULTILINE | re.DOTALL,
)


def rewrite_markdown(content, replacements):
    def replace(match):
        if match.group("code") is not None:
            return match.group(0)
        group = "inline" if match.group("inline") is not None else "reference"
        destination = match.group(group)
        url = destination[1:-1] if destination.startswith("<") else destination
        path = re.split(r"[?#]", url, maxsplit=1)[0]
        decoded = unquote(re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\]^_`{|}~])", r"\1", path))
        if decoded not in replacements:
            return match.group(0)
        extension = Path(decoded).suffix
        encoded_extension = "".join(
            f"(?:{re.escape(character)}|%{ord(character):02x})"
            for character in extension
        )
        new_path = re.sub(encoded_extension + r"$", ".webp", path, flags=re.IGNORECASE)
        new_destination = destination.replace(path, new_path, 1)
        start = match.start(group) - match.start()
        return match.group(0)[:start] + new_destination

    return MARKDOWN_TOKEN.sub(replace, content)


def convert_image(source, destination):
    from PIL import Image, ImageOps

    with Image.open(source) as original:
        if getattr(original, "is_animated", False):
            raise ValueError(f"Animated images are not supported: {source}")
        image = ImageOps.exif_transpose(original)
        alpha = "A" in image.getbands() or "transparency" in image.info
        image = image.convert("RGBA" if alpha else "RGB")
        if image.width > MAX_WIDTH:
            height = max(1, round(image.height * MAX_WIDTH / image.width))
            image = image.resize((MAX_WIDTH, height), Image.Resampling.LANCZOS)
        image.save(destination, format="WEBP", quality=WEBP_QUALITY, method=6)
        expected_size = image.size

    with Image.open(destination) as result:
        result.load()
        if result.format != "WEBP" or result.size != expected_size:
            raise ValueError(f"Failed to validate the WebP image for {source}")


def temporary_path(directory, suffix):
    descriptor, name = tempfile.mkstemp(prefix=".optimize-images-", suffix=suffix, dir=directory)
    os.close(descriptor)
    return Path(name)


def write_markdown(post, content):
    temporary = temporary_path(post.parent, ".md.tmp")
    try:
        temporary.write_bytes(content.encode("utf-8"))
        temporary.chmod(post.stat().st_mode & 0o777)
        temporary.replace(post)
    finally:
        temporary.unlink(missing_ok=True)


def optimize_post(post, image_dir):
    if not image_dir.is_dir():
        return 0
    sources = sorted(
        path for path in image_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS
    )
    if not sources:
        return 0

    targets = set()
    for source in sources:
        target = source.with_suffix(".webp")
        if source.is_symlink() or not source.resolve().is_relative_to(image_dir.resolve()):
            raise ValueError(f"Symbolic links are not processed: {source}")
        if target.exists() or target.is_symlink() or target in targets:
            raise ValueError(f"Conflicting WebP destination: {target}")
        targets.add(target)

    content = post.read_bytes().decode("utf-8")
    staged = []
    published = []
    replacements = {}
    try:
        for source in sources:
            target = source.with_suffix(".webp")
            temporary = temporary_path(source.parent, ".webp")
            staged.append((temporary, target))
            convert_image(source, temporary)
            temporary.chmod(source.stat().st_mode & 0o777)
            relative = source.relative_to(image_dir).as_posix()
            for prefix in ("/img/posts/", "img/posts/", "/static/img/posts/",
                           "static/img/posts/", "../static/img/posts/"):
                old_url = f"{prefix}{post.stem}/{relative}"
                replacements[old_url] = old_url.rsplit(".", 1)[0] + ".webp"

        updated = rewrite_markdown(content, replacements)
        for temporary, target in staged:
            os.link(temporary, target)
            published.append(target)
        if updated != content:
            write_markdown(post, updated)
    except Exception:
        for target in published:
            target.unlink(missing_ok=True)
        raise
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)

    for source in sources:
        source.unlink()
        print(f"  {source.name} -> {source.with_suffix('.webp').name}")
    return len(sources)


def main():
    try:
        from PIL import features
    except ImportError:
        print("Pillow is missing. Install it with: python3 -m pip install -r scripts/requirements.txt",
              file=sys.stderr)
        return 1
    if not features.check("webp"):
        print("This Pillow installation does not support WebP.", file=sys.stderr)
        return 1

    root = Path(__file__).resolve().parent.parent
    posts_dir = root / "posts"
    if not posts_dir.is_dir():
        print(f"Posts directory does not exist: {posts_dir}", file=sys.stderr)
        return 1
    converted = 0
    errors = 0
    for post in sorted(posts_dir.glob("*.md")):
        try:
            count = optimize_post(post, root / "static" / "img" / "posts" / post.stem)
            converted += count
            if count:
                print(f"{post.name}: {count} image(s) converted.")
        except (OSError, ValueError) as error:
            errors += 1
            print(f"ERROR in {post.name}: {error}", file=sys.stderr)
    print(f"Done: {converted} image(s) converted, {errors} post(s) with errors.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
