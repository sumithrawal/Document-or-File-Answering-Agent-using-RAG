from typing import TypedDict, Annotated, List, Union
import operator
from pathlib import Path

import pandas as pd
import uuid
import chromadb
from chromadb.utils import embedding_functions
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph
from chromadb.config import Settings

chromaClient = chromadb.PersistentClient(
    path="./chroma_db",
    settings=Settings(anonymized_telemetry=False)
)
sentenceTransformer = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="paraphrase-multilingual-MiniLM-L12-v2")
collection = chromaClient.get_or_create_collection(name="conversationHistory", embedding_function=sentenceTransformer)

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    dataPath: str
    extractedData: Union[str, pd.DataFrame, None]
    queryAttempt: int
    isValidated: bool
    validationFeedback: str
    threadId: str
    conversationContext: str


llm = ChatOpenAI(model="gpt-4o", temperature=0)

def queryAgent(state: AgentState):
    userInput = state["messages"][-1].content
    filePath = state["dataPath"]
    fileSuffix = Path(filePath).suffix.lower()
    isExcel = fileSuffix in [".xlsx", ".xls"]
    feedback = state.get("validationFeedback", "")
    attempt = state.get("queryAttempt", 0)

    context = state.get("conversationContext", "No previous context.")

    isSummary = userInput == "__GENERATE_DEFAULT_SUMMARY__"
    taskDescription = "Generate a concise summary of the dataset." if isSummary else userInput

    try:
        if isExcel:
            dfTemp = pd.read_excel(filePath, nrows=2)
        else:
            dfTemp = pd.read_csv(filePath, nrows=2)
        columns = dfTemp.columns.tolist()
        sampleData = dfTemp.to_string()
    except Exception as e:
        return {"extractedData": f"Error reading file: {e}", "queryAttempt": attempt + 1}
    
    loadInstruction = (
        f"Load the data using `df = pd.read_excel('{filePath}')`."
        if isExcel
        else f"Load the data using `df = pd.read_csv('{filePath}')`."
    )

    systemPrompt = f"""
    You are a Retail Data Analyst. Write Python Pandas code to answer the user's question.
    
    History Context: {context}
    FILE PATH: {filePath}
    COLUMNS: {columns}
    SAMPLE DATA:{sampleData}

    RULES:
    1. {loadInstruction}
    2. Perform the required analysis (filtering, grouping, etc.).
    3. The final answer MUST be stored in a variable named `result`.
    4. Provide only the raw Python code. No markdown formatting or '```python' blocks.
    5. Previous Errors/Feedback: {feedback}
    """
    
    print(f"--- Query Agent: Generating code (Attempt {attempt + 1}) ---")
    
    try:
        messages = [
            SystemMessage(content=systemPrompt),
            HumanMessage(content=userInput)
        ]
        llmResponse = llm.invoke(messages)
        generatedCode = llmResponse.content.strip().replace("```python", "").replace("```", "")

        executionScope = {"pd": pd}
        exec(generatedCode, {}, executionScope)
        resultValue = executionScope.get("result", "Result variable missing.")            
    except Exception as e:
        return {"extractedData": f"LLM Error: {e}", "queryAttempt": attempt + 1}

    return {"extractedData": resultValue, "queryAttempt": attempt + 1}

def humanizeAgent(state: AgentState):
    rawData = state["extractedData"]
    history = state["messages"]
    
    prompt = f"""Convert this raw data into a concise, professional insight: {rawData}.Maintain the context of the conversation: {history}"""    
    response = llm.invoke(prompt)

    collection.add(
        ids=[str(uuid.uuid4())],
        documents=[f"User: {state['messages'][-1].content} | AI: {response.content}"],
        metadatas=[{"threadId": state["threadId"]}]
    )
    
    print("--- Humanize Agent: Insight Generated & Saved ---")
    return {"messages": [AIMessage(content=response.content)]}

def validationAgent(state: AgentState):
    userQuery = state["messages"][-2].content if len(state["messages"]) > 1 else "Initial Summary"
    aiResponse = state["messages"][-1].content
    
    prompt = f"""Compare the User Question: '{userQuery}' with the AI Answer: '{aiResponse}'.
    Does the answer accurately and fully address the question based on the provided data?
    Respond with 'VALID' or 'INVALID' followed by specific feedback."""
    
    check = llm.invoke(prompt).content
    isValid = "VALID" in check.upper()
    
    print(f"--- Validation Agent: {'Passed' if isValid else 'Failed'} ---")
    
    return {
        "isValidated": isValid,
        "validationFeedback": "" if isValid else check
    }

def contextAgent(state: AgentState):
    threadId = state["threadId"]
    lastMessage = state["messages"][-1].content if state["messages"] else ""    
    results = collection.query(
        query_texts=[lastMessage],
        where={"threadId": threadId},
        n_results=3
    )
    
    pastHistory = ""
    if results.get('documents') and len(results['documents']) > 0:
        pastHistory = "\n".join(results['documents'][0])
    else:
        pastHistory = "No previous context."
        
    print(f"--- Context Agent: Memory retrieved for {threadId} ---")
    return {"conversationContext": pastHistory}

def shouldContinue(state: AgentState):
    if state["isValidated"] or state["queryAttempt"] >= 3:
        return "end"
    else:
        return "retry"

workflow = StateGraph(AgentState)

workflow.add_node("contextAgent", contextAgent)
workflow.add_node("queryAgent", queryAgent)
workflow.add_node("humanizeAgent", humanizeAgent)
workflow.add_node("validationAgent", validationAgent)

workflow.set_entry_point("contextAgent")

workflow.add_edge("contextAgent", "queryAgent")
workflow.add_edge("queryAgent", "humanizeAgent")
workflow.add_edge("humanizeAgent", "validationAgent")

workflow.add_conditional_edges(
    "validationAgent",
    shouldContinue,
    {
        "retry": "queryAgent",
        "end": "__end__"
    }
)

app = workflow.compile()