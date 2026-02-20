import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from graph import app as agentGraph
from dotenv import load_dotenv
from pathlib import Path


app = FastAPI(title="Retail Insights Assistant API")

class ChatRequest(BaseModel):
    userMessage: str
    threadId: str
    dataPath: str

class ChatResponse(BaseModel):
    aiResponse: str
    latencySec: float
    estimatedCostUsd: float

def calculateMetrics(startTime: float, messageContent: str):
    latency = time.time() - startTime
    tokenEstimate = len(messageContent) / 4
    cost = (tokenEstimate / 1000) * 0.03 
    return round(latency, 3), round(cost, 5)

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