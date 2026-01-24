import argparse
import struct
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def _encode_png_bytes(image: QImage, size: int, source: Path) -> bytes:
    if image.isNull():
        raise RuntimeError(f"Failed to load image: {source}")

    if image.width() != size or image.height() != size:
        image = image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    if image.width() != size or image.height() != size:
        target = QImage(size, size, QImage.Format_ARGB32)
        target.fill(0)
        painter = QPainter(target)
        try:
            x_offset = (size - image.width()) // 2
            y_offset = (size - image.height()) // 2
            painter.drawImage(x_offset, y_offset, image)
        finally:
            painter.end()
        image = target

    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.WriteOnly)
    try:
        ok = image.save(buffer, "PNG")
    finally:
        buffer.close()

    if not ok:
        raise RuntimeError(f"Failed to encode PNG at size {size} for {source}")

    return bytes(byte_array)


def _render_svg_to_png_bytes(svg_path: Path, size: int) -> bytes:
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG: {svg_path}")

    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(0)

    painter = QPainter(image)
    try:
        renderer.render(painter, QRectF(0, 0, size, size))
    finally:
        painter.end()

    return _encode_png_bytes(image, size, svg_path)


def _render_png_to_png_bytes(png_path: Path, size: int) -> bytes:
    image = QImage(str(png_path))

    return _encode_png_bytes(image, size, png_path)


def _write_ico(out_path: Path, png_images: list[tuple[int, bytes]]) -> None:
    if len(png_images) == 0:
        raise ValueError("No images provided for ICO.")

    header = struct.pack("<HHH", 0, 1, len(png_images))
    entries = []
    offset = 6 + 16 * len(png_images)
    payload = b""

    for size, png in png_images:
        if size <= 0 or size > 256:
            raise ValueError(f"Invalid icon size: {size}")

        width = 0 if size == 256 else size
        height = 0 if size == 256 else size
        entry = struct.pack(
            "<BBBBHHII",
            width,
            height,
            0,
            0,
            1,
            32,
            len(png),
            offset,
        )
        entries.append(entry)
        payload += png
        offset += len(png)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(header + b"".join(entries) + payload)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a PNG or SVG into a multi-size Windows .ico file."
    )
    parser.add_argument(
        "--svg",
        type=Path,
        default=Path("scripts/release/linux/BlinkTracker.svg"),
        help="Path to source SVG (ignored if --png is set).",
    )
    parser.add_argument(
        "--png",
        type=Path,
        help="Path to source PNG.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("scripts/release/windows/BlinkTracker.ico"),
        help="Path to output .ico.",
    )
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="*",
        default=[16, 24, 32, 48, 64, 128, 256],
        help="Icon sizes to include (max 256).",
    )
    args = parser.parse_args()

    svg_path: Path = args.svg
    png_path: Path | None = args.png
    out_path: Path = args.out
    sizes: list[int] = sorted(set(args.sizes))

    if png_path is not None:
        if not png_path.exists():
            raise FileNotFoundError(f"PNG not found: {png_path}")
    elif not svg_path.exists():
        raise FileNotFoundError(f"SVG not found: {svg_path}")

    app = QGuiApplication.instance()
    if app is None:
        _ = QGuiApplication([])

    images: list[tuple[int, bytes]] = []
    for size in sizes:
        if png_path is not None:
            images.append((size, _render_png_to_png_bytes(png_path, size)))
        else:
            images.append((size, _render_svg_to_png_bytes(svg_path, size)))

    _write_ico(out_path, images)
    print(f"Wrote {out_path} ({len(images)} images)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
