Installation
    1.Create a Virtual Environment:
        python3 -m venv venv

    2.Activate the Environment:
        Windows: venv\Scripts\activate
        macOS/Linux: source venv/bin/activate

    3.Install Dependencies:
        pip install -r requirements.txt

    4. Environment Configuration
        Create a .env file in the root directory.
        Add your OpenAI API key to the file in this format:
            OPENAI_API_KEY=your_actual_key_here
        The application will automatically load this key from the .env file at runtime.

Running the Application
    The system requires two separate terminals to be running simultaneously:
        1. Terminal 1 (Backend): Start the FastAPI server to handle agent orchestration.
            uvicorn main:app --host 0.0.0.0 --port 8000 --reload
        2. Terminal 2 (Frontend): Start the Streamlit UI for the chat interface.
            streamlit run streamlit.py


Assumptions: Data must follow a consistent schema for the Query Agent to write valid Pandas/SQL.
Limitations: The current local prototype is RAM-dependent; the proposed cloud architecture (BigQuery/GCS) resolves this for 100GB+ scales.
Future Improvements: Multi-modal receipt processing and Human-in-the-Loop validation for financial data.