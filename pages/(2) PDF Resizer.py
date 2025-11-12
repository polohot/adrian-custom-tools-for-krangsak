import streamlit as st
from pylovepdf.ilovepdf import ILovePdf
import tempfile
from pathlib import Path
import os
import shutil
from datetime import datetime

st.set_page_config(page_title="PDF Resizer", page_icon="📄", layout="centered")
st.title("📄 PDF Resizer")
st.caption("Compress & optionally downscale embedded images in a PDF using iLovePDF API.")

st.header("PDF Compressor (Single File)")

# --- Setup temp dirs ---
session_tmp = tempfile.mkdtemp()
in_dir = Path(session_tmp) / "in"
out_dir = Path(session_tmp) / "out"
in_dir.mkdir(parents=True, exist_ok=True)
out_dir.mkdir(parents=True, exist_ok=True)

# --- iLovePDF ---
public_key = os.environ.get('ILOVEAPI_PUBLIC_KEY')
if not public_key:
    st.error("Missing ILOVEAPI_PUBLIC_KEY environment variable.")
else:
    ilovepdf = ILovePdf(public_key, verify_ssl=False)

# --- Uploader (single file) ---
file = st.file_uploader("Upload a PDF file", type="pdf", accept_multiple_files=False)

if file:
    pdf_name = file.name
    temp_file_path = in_dir / pdf_name

    # Save input file
    with open(temp_file_path, "wb") as f:
        shutil.copyfileobj(file, f)

    st.write(f"**{pdf_name}** — Original size: {round(temp_file_path.stat().st_size / (1024*1024), 4)} MB")

    # Compress using iLovePDF
    task = ilovepdf.new_task("compress")
    task.add_file(str(temp_file_path))
    task.set_output_folder(str(out_dir))
    task.execute()
    task.download()
    task.delete_current_task()

    # Locate compressed file
    produced = [p for p in out_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
    if not produced:
        produced = [p for p in out_dir.iterdir() if p.is_file()]

    if produced:
        compressed = produced[0]
        st.write(f"Compressed size: {round(compressed.stat().st_size / (1024*1024), 4)} MB")

        st.download_button(
            label=f"Download Compressed PDF",
            data=open(compressed, "rb").read(),
            file_name=f"Compressed-{pdf_name}",
            mime="application/pdf"
        )
    else:
        st.warning("Could not find compressed output file.")
