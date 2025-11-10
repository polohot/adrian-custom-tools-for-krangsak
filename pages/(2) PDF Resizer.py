import os
import tempfile
import streamlit as st
from io import BytesIO
from typing import Tuple, Dict, Any
from pypdf import PdfWriter
from PIL import Image

st.set_page_config(page_title="PDF Resizer", page_icon="📄", layout="centered")
st.title("📄 PDF Resizer")
st.caption("Compress & optionally downscale embedded images in a PDF using pypdf.")

# --- Session state bootstrap ---
if "results" not in st.session_state:
    # results: dict[file_id] -> dict(meta, bytes)
    st.session_state.results: Dict[str, Dict[str, Any]] = {}
if "last_params" not in st.session_state:
    st.session_state.last_params = {}

with st.expander("Why did my file get bigger?", expanded=False):
    st.write(
        """
        A PDF can get *larger* if:
        - The original images were already highly compressed (e.g., JPEG at low quality), and re-encoding at a higher quality inflates them.
        - Images used an efficient codec (e.g., monochrome/JBIG2 or some PNGs) and were converted to a less efficient form.
        - Pages contain mostly vector graphics/text; image recompression contributes little to size.
        To reliably shrink files, **downscaling large images** (reducing pixel dimensions) is often necessary in addition to lowering JPEG quality.
        """
    )

quality = st.slider("JPEG quality", min_value=30, max_value=95, value=70, step=1,
                    help="Lower = smaller file, more artifacts. 60–75 is a good range.")

downscale = st.checkbox("Downscale large images", value=True)
max_side = st.number_input(
    "Max image dimension (px)", min_value=512, max_value=8000, value=2048, step=64,
    help="Images larger than this on their longer side will be resized (Lanczos)."
)

# IMPORTANT: give the uploader a stable key so files persist across reruns
uploaded_files = st.file_uploader(
    "Upload one or more PDFs to compress",
    type=["pdf"],
    accept_multiple_files=True,
    key="uploader"
)

# A simple way to invalidate old results if params change
cur_params = {"quality": quality, "downscale": downscale, "max_side": max_side}
params_changed = cur_params != st.session_state.last_params

if uploaded_files:
    total_input_kb = sum((f.size or 0) for f in uploaded_files) / 1024
    st.info(f"Selected {len(uploaded_files)} file(s) — total {total_input_kb:.1f} KB")

# Process button
run = st.button("Compress PDF(s)")

# If user changed compression parameters after processing, clear old results to avoid confusion
if params_changed and st.session_state.results:
    st.info("Settings changed — clearing previous results.")
    st.session_state.results.clear()

if run and uploaded_files:
    st.session_state.last_params = cur_params
    overall = st.progress(0, text="Starting…")

    for idx, uploaded in enumerate(uploaded_files, start=1):
        # Build a stable per-file id: name + size as a simple heuristic
        file_id = f"{uploaded.name}-{uploaded.size}"

        # Use a temp dir per file (good for platform compatibility)
        with tempfile.TemporaryDirectory() as tdir:
            in_tmp_path = os.path.join(tdir, "input.pdf")
            out_tmp_path = os.path.join(tdir, "output.pdf")

            try:
                input_bytes = uploaded.read()
                if not input_bytes:
                    st.error(f"{uploaded.name}: The uploaded file is empty.")
                    continue
                with open(in_tmp_path, "wb") as f:
                    f.write(input_bytes)

                in_size_kb = len(input_bytes) / 1024
                writer = PdfWriter(clone_from=in_tmp_path)

                images_total = 0
                images_replaced = 0
                images_downscaled = 0

                n_pages = len(writer.pages)
                per_file_prog = st.progress(0, text=f"{uploaded.name}: Processing pages 0/{n_pages}")

                def _downscale_if_needed(im: Image.Image) -> Tuple[Image.Image, bool]:
                    if not downscale:
                        return im, False
                    w, h = im.size
                    long_side = max(w, h)
                    if long_side <= max_side:
                        return im, False
                    scale = max_side / long_side
                    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
                    im2 = im.convert("RGB").resize(new_size, Image.LANCZOS)
                    return im2, True

                for p_i, page in enumerate(writer.pages, start=1):
                    if hasattr(page, "images"):
                        for img in page.images:
                            images_total += 1
                            try:
                                pil = img.image
                                if not isinstance(pil, Image.Image):
                                    pil = Image.open(BytesIO(pil))
                                if pil.mode not in ("RGB", "L"):
                                    pil = pil.convert("RGB")

                                pil2, did_downscale = _downscale_if_needed(pil)
                                if did_downscale:
                                    images_downscaled += 1

                                img.replace(
                                    pil2,
                                    quality=quality,
                                    optimize=True,
                                    progressive=True,
                                    subsampling=2,
                                )
                                images_replaced += 1
                            except Exception:
                                pass

                    per_file_prog.progress(p_i / max(1, n_pages), text=f"{uploaded.name}: Processing pages {p_i}/{n_pages}")

                with open(out_tmp_path, "wb") as f:
                    writer.write(f)
                with open(out_tmp_path, "rb") as f:
                    out_bytes = f.read()

                out_kb = len(out_bytes) / 1024
                pct = (out_kb / in_size_kb - 1.0) * 100 if in_size_kb else 0

                # Persist the result in session state so it survives reruns
                st.session_state.results[file_id] = {
                    "name": uploaded.name,
                    "in_kb": in_size_kb,
                    "out_kb": out_kb,
                    "delta_pct": pct,
                    "images_total": images_total,
                    "images_replaced": images_replaced,
                    "images_downscaled": images_downscaled,
                    # store bytes for download
                    "data": out_bytes,
                    # filename suggestion based on params
                    "download_name": uploaded.name.rsplit(".", 1)[0] + f"-q{quality}{'-dw' if downscale else ''}.pdf",
                }

            except Exception as e:
                st.error(f"{uploaded.name}: Failed to process PDF: {e}")

        overall.progress(idx / len(uploaded_files), text=f"Processed {idx}/{len(uploaded_files)} file(s)")
    overall.empty()
    if st.session_state.results:
        st.success("All done.")

# --- Results area (always rendered from session_state so downloads persist across reruns) ---
if st.session_state.results:
    st.subheader("Results")
    for i, (file_id, r) in enumerate(st.session_state.results.items(), start=1):
        box = st.container(border=True)
        box.subheader(f"📄 {r['name']}")
        c1, c2, c3 = box.columns(3)
        c1.metric("Images found", r["images_total"])
        c2.metric("Re-encoded", r["images_replaced"])
        c3.metric("Downscaled", r["images_downscaled"])

        c4, c5 = box.columns(2)
        c4.metric("Input size", f"{r['in_kb']:.1f} KB")
        c5.metric("Output size", f"{r['out_kb']:.1f} KB", delta=f"{r['delta_pct']:+.1f}%")

        if r["images_total"] == 0:
            box.warning("No embedded raster images detected. File size may not change much.")
        if r["out_kb"] >= r["in_kb"]:
            box.info("Output is larger. Try lowering quality and/or enabling stronger downscaling.")

        # Unique, stable key per file so multiple buttons can be clicked independently
        box.download_button(
            label="⬇️ Download compressed PDF",
            data=r["data"],
            file_name=r["download_name"],
            mime="application/pdf",
            key=f"dl-{file_id}"
        )
else:
    st.caption("Upload one or more PDFs to get started.")
