import time
import uuid
import shutil
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from graph import app as agentGraph, chromaClient, sentenceTransformer
from dotenv import load_dotenv
from utils import calculateMetrics, extractTextForChromadb


load_dotenv()

app = FastAPI(title="Retail Insights Assistant API")

UPLOAD_DIR = Path("uploaded_data")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

documentCollection = chromaClient.get_or_create_collection(
    name="uploadedDocuments",
    embedding_function=sentenceTransformer,
)


class ChatRequest(BaseModel):
    userMessage: str
    threadId: str
    dataPath: str
    userId: str


class ChatResponse(BaseModel):
    aiResponse: str
    latencySec: float
    estimatedCostUsd: float
    userId: str


class UploadResponse(BaseModel):
    storageType: str
    dataPath: Optional[str] = None
    documentId: Optional[str] = None
    userId: str


class CreateUser(BaseModel):
    userId: str


class UserFile(BaseModel):
    documentId: str
    filename: str
    storedPath: Optional[str] = None
    storageType: str


@app.post("/register", response_model=CreateUser)
def registerUser():
    useruuid = str(uuid.uuid4())
    return CreateUser(userId=useruuid)


@app.post("/upload", response_model=UploadResponse)
async def uploadDocument(
    file: UploadFile = File(...),
    userId: str = Form(...),
):
    suffix = Path(file.filename).suffix.lower()
    unique_name = f"{uuid.uuid4()}{suffix}"
    destination = UPLOAD_DIR / unique_name

    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    if suffix in [".csv", ".xlsx"]:
        documentid = str(uuid.uuid4())
        documentCollection.add(
            ids=[documentid],
            documents=[f"Tabular file stored at {destination}"],
            metadatas=[
                {
                    "filename": file.filename,
                    "stored_path": str(destination),
                    "storageType": "file",
                    "userId": userId,
                }
            ],
        )
        return UploadResponse(
            storageType="file",
            dataPath=str(destination),
            documentId=documentid,
            userId=userId,
        )
    if suffix in [".pdf", ".docx", ".txt", ".doc"]:
        if suffix == ".doc":
            raise HTTPException(
                status_code=400,
                detail="Legacy .doc files are not supported; please convert to .docx before uploading.",
            )

        textContent = extractTextForChromadb(destination, suffix)
        if not textContent:
            raise HTTPException(
                status_code=400,
                detail="No text could be extracted from the uploaded document.",
            )

        documentid = str(uuid.uuid4())
        documentCollection.add(
            ids=[documentid],
            documents=[textContent],
            metadatas=[
                {
                    "filename": file.filename,
                    "stored_path": str(destination),
                    "storageType": "chroma",
                    "userId": userId,
                }
            ],
        )

        return UploadResponse(
            storageType="chroma",
            documentId=documentid,
            userId=userId,
        )

    destination.unlink(missing_ok=True)
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type: {suffix}",
    )


@app.get("/files", response_model=List[UserFile])
def listUserFiles(userId: str = Query(...)):
    results = documentCollection.get(
        where={"userId": userId},
        include=["metadatas", "ids"],
    )

    files: List[UserFile] = []
    ids = results.get("ids") or []
    metadatas = results.get("metadatas") or []

    for docId, metadata in zip(ids, metadatas):
        files.append(
            UserFile(
                documentId=docId,
                filename=metadata.get("filename", ""),
                storedPath=metadata.get("stored_path"),
                storageType=metadata.get("storageType", ""),
            )
        )
    

    return files


@app.post("/chat", response_model=ChatResponse)
async def chatEndpoint(request: ChatRequest):
    startTime = time.time()
    try:
        initialState = {
            "messages": [HumanMessage(content=request.userMessage)],
            "dataPath": request.dataPath,
            "queryAttempt": 0,
            "isValidated": False,
            "threadId": request.threadId,
            "userId": request.userId,
        }
        config = {"configurable": {"threadId": request.threadId}}
        resultState = agentGraph.invoke(initialState, config=config)
        finalMessage = resultState["messages"][-1].content
        latency, cost = calculateMetrics(startTime, finalMessage)
        return ChatResponse(
            aiResponse=finalMessage,
            latencySec=latency,
            estimatedCostUsd=cost,
            userId=request.userId,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)