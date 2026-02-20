import streamlit as st
import requests
import uuid

BASE_URL = "http://0.0.0.0:8000"
CHAT_API_URL = f"{BASE_URL}/chat"
UPLOAD_API_URL = f"{BASE_URL}/upload"
REGISTER_API_URL = f"{BASE_URL}/register"
FILES_API_URL = f"{BASE_URL}/files"

st.set_page_config(page_title="File Answering Agent", layout="wide")
st.title("📊 File Answering Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "threadId" not in st.session_state:
    st.session_state.threadId = str(uuid.uuid4())
if "dataPath" not in st.session_state:
    st.session_state.dataPath = ""
if "userId" not in st.session_state:
    st.session_state.userId = ""
if "userFiles" not in st.session_state:
    st.session_state.userFiles = []
if "summaryGenerated" not in st.session_state:
    st.session_state.summaryGenerated = False


def fetch_user_files(user_id: str):
    if not user_id:
        st.session_state.userFiles = []
        return

    try:
        response = requests.get(FILES_API_URL, params={"userId": user_id})
        response.raise_for_status()
        st.session_state.userFiles = response.json()
    except Exception as e:
        st.error(f"Failed to load files for user: {e}")
        st.session_state.userFiles = []


with st.sidebar:
    st.header("User")

    col_reg1, col_reg2 = st.columns([1, 2])
    with col_reg1:
        if st.button("Register"):
            try:
                resp = requests.post(REGISTER_API_URL)
                resp.raise_for_status()
                data = resp.json()
                st.session_state.userId = data.get("userId", "")
                st.success(f"Registered new user: {st.session_state.userId}")
                fetch_user_files(st.session_state.userId)
            except Exception as e:
                st.error(f"Registration failed: {e}")

    with col_reg2:
        manual_user_id = st.text_input(
            "User ID",
            value=st.session_state.userId,
            placeholder="Enter existing user ID",
        )

    if st.button("Load User Files"):
        st.session_state.userId = manual_user_id.strip()
        fetch_user_files(st.session_state.userId)

    st.markdown("---")
    st.header("Your Files")

    if st.session_state.userFiles:
        labels = [
            f"{f.get('filename', 'Unnamed')} ({f.get('storageType', '')})"
            for f in st.session_state.userFiles
        ]
        selected_index = st.radio(
            "Select a file to chat with",
            options=range(len(labels)),
            format_func=lambda i: labels[i],
            key="selected_file_index",
        )

        selected_file = st.session_state.userFiles[selected_index]
        storage_type = selected_file.get("storageType")
        stored_path = selected_file.get("storedPath")

        if storage_type == "file" and stored_path:
            if stored_path != st.session_state.dataPath:
                st.session_state.dataPath = stored_path
                st.session_state.messages = []
                st.session_state.threadId = str(uuid.uuid4())
                st.session_state.summaryGenerated = False
        else:
            st.info("Only CSV/Excel files can be used for chat today.")

    st.markdown("---")
    st.header("Upload Data")

    uploadedFile = st.file_uploader(
        "Upload sales data or document",
        type=["csv", "xlsx", "pdf", "docx", "txt"],
    )

    if uploadedFile:
        if not st.session_state.userId:
            st.error("Please register or enter a User ID before uploading.")
        else:
            try:
                files = {
                    "file": (
                        uploadedFile.name,
                        uploadedFile.getvalue(),
                        uploadedFile.type or "application/octet-stream",
                    )
                }
                data = {"userId": st.session_state.userId}
                response = requests.post(UPLOAD_API_URL, files=files, data=data)
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

                    st.success(f"Loaded data file: {uploadedFile.name}")

                    if not st.session_state.get("summaryGenerated", False):
                        payload = {
                            "userMessage": "__GENERATE_DEFAULT_SUMMARY__",
                            "threadId": st.session_state.threadId,
                            "dataPath": st.session_state.dataPath,
                            "userId": st.session_state.userId,
                        }

                        with st.spinner("Generating summary..."):
                            try:
                                summaryResponse = requests.post(
                                    CHAT_API_URL, json=payload
                                )
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
                    st.success(
                        "Document stored in vector database. "
                        "Current chat is optimized for CSV/Excel data files."
                    )
                else:
                    st.error("Unexpected response from upload API.")

                # Refresh user's file list after any upload
                fetch_user_files(st.session_state.userId)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if userInput := st.chat_input("Ask about sales performance..."):
    if not st.session_state.dataPath:
        st.error("Please select or upload a CSV/Excel data file first.")
    elif not st.session_state.userId:
        st.error("Please register or enter a User ID first.")
    else:
        st.session_state.messages.append({"role": "user", "content": userInput})
        with st.chat_message("user"):
            st.markdown(userInput)

        payload = {
            "userMessage": userInput,
            "threadId": st.session_state.threadId,
            "dataPath": st.session_state.dataPath,
            "userId": st.session_state.userId,
        }

        with st.spinner("Agents are checking the data..."):
            try:
                response = requests.post(CHAT_API_URL, json=payload)
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