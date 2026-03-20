# Project Proposal: SUSTech Student Productivity Agent

## Part I. Preliminary Requirement Analysis

### 1. Functional Requirements
The proposed system is an Autonomous AI Agent designed to assist SUSTech students by integrating multiple data sources and executing complex tasks. Based on the mandatory Agentic Loop architecture, the system features the following 5 distinct, orthogonal functionalities:

1. **Intelligent GUI Mechanism (Interactive Interface & Safety)**
   - **Personalized Dashboard:** A customizable chat interface managing user accounts, academic profiles, and historical chat logs.
   - **Thought Trace Panel:** A dedicated UI component that streams the Agent's internal reasoning logic and tool-calling sequence (Observation & Planning) in real-time.
   - **Human-in-the-Loop (HITL) Interceptor:** A mandatory security prompt that intercepts high-risk execution requests (e.g., deleting files, modifying schedules) and waits for explicit user authorization before proceeding.
2. **Web Parsing & Schedule Planning (Multi-Source Scheduler)**
   - Automatically scrapes and parses scheduling data from the Official University Calendar and Blackboard deadlines.
   - The Agent autonomously detects time conflicts with personal TODOs and dynamically suggests an optimized study/event calendar.
3. **Campus Encyclopedia (RAG Knowledge Retrieval)**
   - Acts as an intelligent QA system capable of answering complex campus-related queries (e.g., degree requirements, dormitory policies).
   - Utilizes Retrieval-Augmented Generation (RAG) by searching embedded chunks from official documents (like the SUSTech Student Handbook) stored in a local Vector Database.
4. **Study Copilot (Academic Document Understanding)**
   - Processes user-uploaded or local academic materials (lecture PPTs, PDFs, Markdown notes).
   - The Agent reads the extracted text to autonomously generate concise study summaries, extract key concepts, and create customized practice quizzes.
5. **System-Level OS Automation (File & Task Execution)**
   - Executes operating system-level automation scripts via natural language commands.
   - Capable of performing file manipulation tasks (e.g., reading, creating, deleting, and batch renaming messy lab files to a specific format like `[Name_ID_Lab1].zip`).

### 2. Non-functional Requirements
- **Usability:** The GUI must cleanly separate the main chat interface from the Thought Trace panel to prevent information overload. Rich text and generated schedules must be rendered elegantly.
- **Safety & Security (Crucial):** Sensitive user credentials (e.g., Blackboard passwords) must be securely encrypted. The system strictly adheres to the HITL mechanism to prevent unauthorized local OS modifications.
- **Reliability & Error Recovery:** The Agent must feature robust error handling. If a tool fails (e.g., web scraping timeout), the tool must return an error message to the LLM, allowing the Agent to autonomously reason and retry an alternative approach.
- **Performance:** System responses and thought traces should be streamed to minimize perceived latency. Local RAG vector searches should return context within 2 seconds.

### 3. Technical Requirements
- **Operating Environment:** Cross-platform support (Windows/macOS) suitable for students' personal laptops. Python 3.10+.
- **Core Agent Framework:** `PydanticAI` (or `LangChain`) will be used to orchestrate the core Agentic Loop (Perception, Reasoning, Tool Use, Observation). *Strictly no Low-Code/No-Code platforms (e.g., n8n, Dify) will be used.*
- **GUI & Frontend Stack:** `PyQt6` / `PySide6` (or modern web frameworks like `Vue3` + `FastAPI` if preferred) to build the interactive interface, render markdown, and handle local OS permissions seamlessly.
- **Backend & Tooling:** 
  - `BeautifulSoup`/`Selenium` for scraping web data (Blackboard).
  - `PyMuPDF`/`python-pptx` for document parsing.
  - `os`/`shutil` for system-level file automation.
- **Database Layer:** `SQLite` for storing user profiles, credentials, and chat history. `ChromaDB` (or `FAISS`) for the local vector database managing the RAG document embeddings.
- **LLM Engine:** High-performance models (e.g., OpenAI GPT-4o-mini, DeepSeek, or Qwen via API) capable of reliable function calling.

### 4. Data Requirements
- **Data Needed:**
  1. User authentication data, preferences, and historical dialogue records.
  2. Official SUSTech documents (e.g., Student Handbooks in PDF format).
  3. Student's personal academic files (Lecture PPTs, Markdown notes, lab reports).
  4. Real-time scheduling data (Blackboard deadlines, University Calendar).
- **Data Acquisition Methods:**
  - Web data (Blackboard/Calendar) will be acquired via Python web scrapers/crawlers mimicking user login.
  - Official handbooks and lecture materials will be acquired via local file paths, processed through parsing scripts, and chunked into the Vector DB.
  - User profiles and chat history will be collected through GUI interactions and stored locally.
