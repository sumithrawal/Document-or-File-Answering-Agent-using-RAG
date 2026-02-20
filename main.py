import time
import uuid
import shutil
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from graph import app as agentGraph, chromaClient, sentenceTransformer
from dotenv import load_dotenv
from pathlib import Path
from utils import calculateMetrics,extractTextForChromadb


app = FastAPI(title="Retail Insights Assistant API")

UPLOAD_DIR = Path("uploaded_data")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

documentCollection = chromaClient.get_or_create_collection(
    name="uploadedDocuments",
    embedding_function=sentenceTransformer
)
class ChatRequest(BaseModel):
    userMessage: str
    threadId: str
    dataPath: str

class ChatResponse(BaseModel):
    aiResponse: str
    latencySec: float
    estimatedCostUsd: float

class UploadResponse(BaseModel):
    storageType: str
    dataPath: Optional[str] = None
    documentId: Optional[str] = None

@app.post("/upload", response_model=UploadResponse)
async def uploadDocument(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    unique_name = f"{uuid.uuid4()}{suffix}"
    destination = UPLOAD_DIR / unique_name

    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    if suffix in [".csv", ".xlsx"]:
        return UploadResponse(
            storageType="file",
            dataPath=str(destination)
        )

    if suffix in [".pdf", ".docx", ".txt", ".doc"]:
        if suffix == ".doc":
            raise HTTPException(
                status_code=400,
                detail="Legacy .doc files are not supported; please convert to .docx before uploading."
            )

        text_content = extractTextForChromadb(destination, suffix)
        if not text_content:
            raise HTTPException(
                status_code=400,
                detail="No text could be extracted from the uploaded document."
            )

        document_id = str(uuid.uuid4())
        documentCollection.add(
            ids=[document_id],
            documents=[text_content],
            metadatas=[{
                "filename": file.filename,
                "stored_path": str(destination)
            }]
        )

        return UploadResponse(
            storageType="chroma",
            documentId=document_id
        )
    destination.unlink(missing_ok=True)
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type: {suffix}"
    )


@app.post("/chat", response_model=ChatResponse)
async def chatEndpoint(request: ChatRequest):
    startTime = time.time()
    try:
        initialState = {
            "messages": [HumanMessage(content=request.userMessage)],
            "dataPath": request.dataPath,
            "queryAttempt": 0,
            "isValidated": False,
            "threadId": request.threadId
        }
        config = {"configurable": {"threadId": request.threadId}}
        resultState = agentGraph.invoke(initialState, config=config)
        finalMessage = resultState["messages"][-1].content
        latency, cost = calculateMetrics(startTime, finalMessage)        
        return ChatResponse(
            aiResponse=finalMessage,
            latencySec=latency,
            estimatedCostUsd=cost
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)