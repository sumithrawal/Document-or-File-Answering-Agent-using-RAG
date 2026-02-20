import streamlit as st
import requests
import os
import uuid

API_URL = "http://localhost:8000/chat"

st.set_page_config(page_title="Sales Data Agent", layout="wide")
st.title("📊 Sales Data Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "threadId" not in st.session_state:
    st.session_state.threadId = str(uuid.uuid4())
if "dataPath" not in st.session_state:
    st.session_state.dataPath = ""

with st.sidebar:
    st.header("Upload Data")
    uploadedFile = st.file_uploader("Upload Sales CSV", type="csv")

    if uploadedFile:
        tempPath = os.path.join("temp_data", uploadedFile.name)
        os.makedirs("temp_data", exist_ok=True)
        with open(tempPath, "wb") as f:
            f.write(uploadedFile.getbuffer())
        if st.session_state.get("dataPath") != tempPath:
            st.session_state.dataPath = tempPath
            st.session_state.messages = []
            st.session_state.threadId = str(uuid.uuid4())
            st.session_state.summaryGenerated = False
        st.success(f"Loaded: {uploadedFile.name}")
        if not st.session_state.get("summaryGenerated", False):
            payload = {
                "userMessage": "__GENERATE_DEFAULT_SUMMARY__",
                "threadId": st.session_state.threadId,
                "dataPath": st.session_state.dataPath
            }

            with st.spinner("Generating summary..."):
                try:
                    response = requests.post(API_URL, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    aiResponse = data["aiResponse"]
                    latency = data["latencySec"]
                    cost = data["estimatedCostUsd"]
                    st.session_state.messages.append({"role": "assistant", "content": aiResponse})
                    st.session_state.summaryGenerated = True
                    st.caption(f"Summary latency: {latency}s | Est. cost: ${cost}")

                except Exception as e:
                    st.error(f"Summary generation failed: {e}")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if userInput := st.chat_input("Ask about sales performance..."):
    if not st.session_state.dataPath:
        st.error("Please upload a CSV file")
    else:
        st.session_state.messages.append({"role": "user", "content": userInput})
        with st.chat_message("user"):
            st.markdown(userInput)

        payload = {
            "userMessage": userInput,
            "threadId": st.session_state.threadId,
            "dataPath": st.session_state.dataPath
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

                st.session_state.messages.append({"role": "assistant", "content": aiResponse})
            
            except Exception as e:
                st.error(f"Something went wrong please try again later: {e}")