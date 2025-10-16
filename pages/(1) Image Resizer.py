import io
import zipfile
from datetime import datetime
from typing import List, Tuple

import streamlit as st
from PIL import Image

st.set_page_config(page_title="page1 – Image Resizer", page_icon="📐", layout="centered")

st.title("📐 Image Resizer")
st.write("Upload one or more images, choose a percentage, then download a ZIP of resized copies.")

# Percentage selector: 10%..90%
pct = st.select_slider(
    "Resize to (%) of original",
    options=[10, 20, 30, 40, 50, 60, 70, 80, 90],
    value=50,
    help="All images will be scaled by this percentage while preserving aspect ratio.")

uploaded_files = st.file_uploader(
    "Drag & drop images here (or click to browse)",
    type=["png", "jpg", "jpeg", "webp", "bmp", "tiff"],
    accept_multiple_files=True)

def _safe_name(name: str) -> str:
    # Keep it simple and filesystem-safe
    return name.replace("/", "_").replace("\\", "_").strip()

def _resize_image(img: Image.Image, pct: int) -> Image.Image:
    w, h = img.size
    new_size: Tuple[int, int] = (max(1, w * pct // 100), max(1, h * pct // 100))
    return img.resize(new_size, Image.Resampling.LANCZOS)

def _infer_format_from_name(name: str) -> str:
    # Map common extensions to PIL save formats; default to PNG
    ext = name.split(".")[-1].lower() if "." in name else ""
    return {
        "jpg": "JPEG",
        "jpeg": "JPEG",
        "png": "PNG",
        "webp": "WEBP",
        "bmp": "BMP",
        "tif": "TIFF",
        "tiff": "TIFF",
    }.get(ext, "PNG")

# Preview thumbnails (optional)
if uploaded_files:
    st.subheader("Preview")
    cols = st.columns(min(3, len(uploaded_files)))
    for i, f in enumerate(uploaded_files):
        with cols[i % len(cols)]:
            try:
                img = Image.open(f)
                img.thumbnail((240, 240))
                st.image(img, caption=_safe_name(f.name), width='content')
            except Exception as e:
                st.error(f"Could not preview {f.name}: {e}")

process = st.button("⚙️ Process & prepare ZIP")

zip_bytes = None
error_count = 0

if process:
    if not uploaded_files:
        st.warning("Please upload at least one image.")
    else:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in uploaded_files:
                try:
                    f.seek(0)
                    img = Image.open(f)
                    # Convert paletted/with alpha handling for JPEG if needed
                    fmt = _infer_format_from_name(f.name)
                    resized = _resize_image(img, pct)

                    out_bytes = io.BytesIO()
                    save_kwargs = {}
                    if fmt == "JPEG":
                        # Ensure RGB for JPEG (no alpha)
                        if resized.mode in ("RGBA", "LA", "P"):
                            resized = resized.convert("RGB")
                        save_kwargs.update({"quality": 90, "optimize": True})
                    resized.save(out_bytes, format=fmt, **save_kwargs)
                    out_bytes.seek(0)

                    base = _safe_name(f.name.rsplit(".", 1)[0]) if "." in f.name else _safe_name(f.name)
                    ext = (fmt.lower() if fmt != "JPEG" else "jpg")
                    arcname = f"{base}_{pct}pct.{ext}"
                    zf.writestr(arcname, out_bytes.read())
                except Exception as e:
                    error_count += 1
                    st.error(f"Failed to process {f.name}: {e}")
        buffer.seek(0)
        zip_bytes = buffer.read()

if zip_bytes:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"resized_{pct}pct_{timestamp}.zip"
    st.success(f"Done! {len(uploaded_files) - error_count} file(s) processed.")
    st.download_button(
        "⬇️ Download ZIP",
        data=zip_bytes,
        file_name=filename,
        mime="application/zip",
        use_container_width=True,
    )
