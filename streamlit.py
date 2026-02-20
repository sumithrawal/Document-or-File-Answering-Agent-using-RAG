import streamlit as st
import requests
import uuid

API_URL = "http://localhost:8000/chat"
UPLOAD_API_URL = "http://localhost:8000/upload"

st.set_page_config(page_title="Sales Data Agent", layout="wide")
st.title("📊 Sales Data Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "threadId" not in st.session_state:
    st.session_state.threadId = str(uuid.uuid4())
if "dataPath" not in st.session_state:
    st.session_state.dataPath = ""
if "documentId" not in st.session_state:
    st.session_state.documentId = None

with st.sidebar:
    st.header("Upload Data")
    uploadedFile = st.file_uploader(
        "Upload sales data or document",
        type=["csv", "xlsx", "pdf", "docx", "txt"],
    )

    if uploadedFile:
        try:
            files = {
                "file": (
                    uploadedFile.name,
                    uploadedFile.getvalue(),
                    uploadedFile.type or "application/octet-stream",
                )
            }
            response = requests.post(UPLOAD_API_URL, files=files)
            response.raise_for_status()
            uploadData = response.json()
        except Exception as e:
            st.error(f"Upload failed: {e}")
        else:
            storageType = uploadData.get("storageType")

            if storageType == "file":
                dataPath = uploadData.get("dataPath", "")
                if dataPath and st.session_state.get("dataPath") != dataPath:
                    st.session_state.dataPath = dataPath
                    st.session_state.messages = []
                    st.session_state.threadId = str(uuid.uuid4())
                    st.session_state.summaryGenerated = False
                    st.session_state.documentId = None

                st.success(f"Loaded data file: {uploadedFile.name}")

                if not st.session_state.get("summaryGenerated", False):
                    payload = {
                        "userMessage": "__GENERATE_DEFAULT_SUMMARY__",
                        "threadId": st.session_state.threadId,
                        "dataPath": st.session_state.dataPath,
                    }

                    with st.spinner("Generating summary..."):
                        try:
                            summaryResponse = requests.post(API_URL, json=payload)
                            summaryResponse.raise_for_status()
                            data = summaryResponse.json()
                            aiResponse = data["aiResponse"]
                            latency = data["latencySec"]
                            cost = data["estimatedCostUsd"]
                            st.session_state.messages.append(
                                {"role": "assistant", "content": aiResponse}
                            )
                            st.session_state.summaryGenerated = True
                            st.caption(
                                f"Summary latency: {latency}s | Est. cost: ${cost}"
                            )

                        except Exception as e:
                            st.error(f"Summary generation failed: {e}")

            elif storageType == "chroma":
                st.session_state.dataPath = ""
                st.session_state.documentId = uploadData.get("documentId")
                st.session_state.messages = []
                st.session_state.threadId = str(uuid.uuid4())
                st.success(
                    "Document stored in vector database. "
                    "Current chat is optimized for CSV/Excel data files."
                )
            else:
                st.error("Unexpected response from upload API.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if userInput := st.chat_input("Ask about sales performance..."):
    if not st.session_state.dataPath:
        st.error("Please upload a CSV or Excel data file first.")
    else:
        st.session_state.messages.append({"role": "user", "content": userInput})
        with st.chat_message("user"):
            st.markdown(userInput)

        payload = {
            "userMessage": userInput,
            "threadId": st.session_state.threadId,
            "dataPath": st.session_state.dataPath,
        }

        with st.spinner("Agents are checking the data..."):
            try:
                response = requests.post(API_URL, json=payload)
                response.raise_for_status()
                data = response.json()

                aiResponse = data["aiResponse"]
                latency = data["latencySec"]
                cost = data["estimatedCostUsd"]

                with st.chat_message("assistant"):
                    st.markdown(aiResponse)

                    col1, col2 = st.columns(2)
                    col1.metric("Latency", f"{latency}s")
                    col2.metric("Est. Cost", f"${cost}")

                st.session_state.messages.append(
                    {"role": "assistant", "content": aiResponse}
                )

            except Exception as e:
                st.error(f"Something went wrong please try again later: {e}")