import streamlit as st
from io import BytesIO
from typing import Tuple
from pypdf import PdfWriter
from PIL import Image

st.set_page_config(page_title="PDF Resizer", page_icon="📄", layout="centered")
st.title("📄 PDF Resizer")
st.caption("Compress & optionally downscale embedded images in a PDF using pypdf.")

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

# 👇 allow multiple files
uploaded_files = st.file_uploader("Upload one or more PDFs to compress", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    total_input_kb = sum((f.size or 0) for f in uploaded_files) / 1024
    st.info(f"Selected {len(uploaded_files)} file(s) — total {total_input_kb:.1f} KB")

    run = st.button("Compress PDF(s)")
    if run:
        # Overall progress bar (across files)
        overall = st.progress(0, text="Starting…")
        results = []

        for idx, uploaded in enumerate(uploaded_files, start=1):
            file_container = st.container(border=True)
            file_container.subheader(f"📄 {uploaded.name}")

            try:
                input_bytes = uploaded.read()
                if not input_bytes:
                    file_container.error("The uploaded file is empty.")
                    continue

                in_size_kb = len(input_bytes) / 1024
                writer = PdfWriter(clone_from=BytesIO(input_bytes))

                images_total = 0
                images_replaced = 0
                images_downscaled = 0

                # Per-file page progress bar
                n_pages = len(writer.pages)
                per_file_prog = file_container.progress(0, text=f"Processing pages 0/{n_pages}")

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
                                # Skip images we fail to process; keep the original
                                pass

                    # Update per-file progress by pages
                    per_file_prog.progress(p_i / max(1, n_pages), text=f"Processing pages {p_i}/{n_pages}")

                out_buffer = BytesIO()
                writer.write(out_buffer)
                out_bytes = out_buffer.getvalue()

                out_kb = len(out_bytes) / 1024
                pct = (out_kb / in_size_kb - 1.0) * 100 if in_size_kb else 0

                c1, c2, c3 = file_container.columns(3)
                c1.metric("Images found", images_total)
                c2.metric("Re-encoded", images_replaced)
                c3.metric("Downscaled", images_downscaled)

                c4, c5 = file_container.columns(2)
                c4.metric("Input size", f"{in_size_kb:.1f} KB")
                c5.metric("Output size", f"{out_kb:.1f} KB", delta=f"{pct:+.1f}%")

                if images_total == 0:
                    file_container.warning("No embedded raster images detected. File size may not change much.")

                if out_kb >= in_size_kb:
                    file_container.info("Output is larger. Try lowering quality and/or enabling stronger downscaling.")

                out_name = uploaded.name.rsplit(".", 1)[0] + f"-q{quality}{'-dw' if downscale else ''}.pdf"
                file_container.download_button(
                    label="⬇️ Download compressed PDF",
                    data=out_bytes,
                    file_name=out_name,
                    mime="application/pdf",
                    key=f"dl-{idx}-{uploaded.name}",
                )

                results.append((uploaded.name, in_size_kb, out_kb, images_total, images_replaced, images_downscaled))

            except Exception as e:
                file_container.error(f"Failed to process PDF: {e}")

            # update overall progress
            overall.progress(idx / len(uploaded_files), text=f"Processed {idx}/{len(uploaded_files)} file(s)")

        overall.empty()  # clear when done

        if results:
            st.success("All done.")
else:
    st.caption("Upload one or more PDFs to get started.")
