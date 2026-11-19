"""Streamlit chat UI. Run from the repo root: `streamlit run app/streamlit_app.py`."""

from pathlib import Path

import streamlit as st

from pdf_rag.config import get_settings
from pdf_rag.indexing import count_chunks, upsert_records
from pdf_rag.ingest import ingest_files
from pdf_rag.qa import RagPipeline, cite

st.set_page_config(page_title="PDF RAG Assistant", layout="wide")
settings = get_settings()


@st.cache_resource(show_spinner=False)
def get_pipeline() -> RagPipeline:
    return RagPipeline(settings)


try:
    pipeline = get_pipeline()
except Exception as exc:
    st.error(f"Could not open the index or reach Ollama at {settings.ollama_base_url}: {exc}")
    st.stop()

st.title("📚 PDF RAG Assistant")
st.caption(f"Powered by {settings.llm_model} + {settings.embed_model} via Ollama")

# ---- Sidebar: upload + index -------------------------------------------------
with st.sidebar:
    st.header("Documents")
    uploaded = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
    if uploaded and st.button(f"Index {len(uploaded)} PDF(s)", type="primary"):
        settings.raw_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for f in uploaded:
            dest = settings.raw_dir / Path(f.name).name  # strip any path components
            dest.write_bytes(f.getbuffer())
            saved.append(dest)
        try:
            with st.spinner("Extracting text..."):
                records = ingest_files(saved, settings.pages_file, settings.ocr)
            with st.spinner(f"Embedding {len(records)} pages..."):
                n = upsert_records(pipeline.store, records, settings)
            st.success(f"Indexed {n} chunks from {len(saved)} file(s).")
        except Exception as exc:
            st.error(f"Indexing failed: {exc}")

    try:
        st.metric("Chunks in index", count_chunks(pipeline.store))
    except Exception:
        pass
    if st.button("Clear chat"):
        st.session_state.messages = []

# ---- Chat --------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []


def render_sources(sources: list[str]) -> None:
    if sources:
        with st.expander("Sources"):
            for s in sources:
                st.markdown(f"- {s}")


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        render_sources(msg.get("sources", []))

question = st.chat_input("Ask a question about your documents")
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner(f"{settings.llm_model} is thinking..."):
            try:
                answer = pipeline.ask(question)
                text, sources = answer.text, list(dict.fromkeys(cite(d) for d in answer.sources))
            except Exception as exc:
                text, sources = f"⚠️ Error: {exc}", []
        st.markdown(text)
        render_sources(sources)
    st.session_state.messages.append({"role": "assistant", "content": text, "sources": sources})
