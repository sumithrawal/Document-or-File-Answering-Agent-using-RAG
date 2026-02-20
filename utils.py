import uuid
import shutil
from typing import Optional
from pathlib import Path
import time
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from graph import app as agentGraph, chromaClient, sentenceTransformer
from graph import app as agentGraph, chromaClient, sentenceTransformer

def calculateMetrics(startTime: float, messageContent: str):
    latency = time.time() - startTime
    tokenEstimate = len(messageContent) / 4
    cost = (tokenEstimate / 1000) * 0.03 
    return round(latency, 3), round(cost, 5)

def extractTextFromPdf(path: Path) -> str:
    try:
        import PyPDF2
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="PDF support is not installed on the server.") from exc

    text_chunks = []
    with path.open("rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text_chunks.append(page_text)
    return "\n".join(text_chunks).strip()


def extractTextFromDocx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="DOCX support is not installed on the server.") from exc

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs).strip()


def extractTextFromTxt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def extractTextForChromadb(path: Path, suffix: str) -> str:
    suffix = suffix.lower()
    if suffix == ".pdf":
        return extractTextFromPdf(path)
    if suffix == ".docx":
        return extractTextFromDocx(path)
    if suffix == ".txt":
        return extractTextFromTxt(path)
    raise HTTPException(status_code=400, detail=f"Unsupported document type for ChromaDB ingestion: {suffix}")