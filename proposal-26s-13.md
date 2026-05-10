# Preliminary Requirement Analysis: Student Productivity Agent

## 1. Functional Requirements
The proposed system is an Autonomous AI Agent designed to assist SUSTech students by integrating multiple data sources and executing complex tasks, such as cleaning up the schedule, organizing files and hunting down campus information. The system features the following distinct, orthogonal functionalities:

1. **Agentic Loop Architecture**
    - **Dynamic Perception-Action Loop:** Implements the core architecture (Perception -> Reasoning -> Tool Use -> Observation). The Agent doesn't follow a hardcoded script but decides actions dynamically based on user goals.
    - **Self-Correction** The Agent reads tool outputs and error logs. If a task fails (e.g., a login timeout), it autonomously reasons a recovery strategy or tries an alternative tool without manual intervention.
2. **Intelligent GUI Design**
   - **Personalized Dashboard:** A customizable chat interface managing user accounts, personal files and historical chat logs.
   - **Thought Trace Panel:** A dedicated UI component that streams the Agent's internal reasoning logic and tool-calling sequence (Observation & Planning) in real-time.
   - **Human-in-the-Loop Interceptor:** A mandatory security prompt that intercepts heavy and high-risk execution requests (e.g., deleting files, modifying schedules) and waits for explicit user authorization before proceeding.
3. **Multi-Source Scheduler**
   - **Web Parsing:** Automatically scrapes and parses scheduling data from the Official SUSTech Calendar and Blackboard deadlines.
   - **Schedule Planning:** Autonomously detects time conflicts with personal TODOs and dynamically suggests an optimized study/event calendar.
4. **Campus Encyclopedia based on RAG Knowledge Retrieval**
   - Acts as an intelligent QA system capable of answering complex campus-related queries (e.g., degree requirements, dormitory policies).
   - Utilizes Retrieval-Augmented Generation (RAG) by searching embedded chunks from official documents (like the SUSTech Student Handbook) stored in a local Vector Database.
5. **Library Discussion Room Query**
   - Queries the availability of discussion rooms in the SUSTech Library based on user-specified criteria including location, desired time slot and room capacity.
   - Returns a list of matching discussion rooms with their availability status, enabling students to quickly find and plan group study sessions.
6. **Study Copilot**
   - Processes user-uploaded or local academic materials, such as lecture PPTs, PDFs, Markdown notes and so on.
   - The Agent reads the extracted text to autonomously extract key concepts, generate concise study summaries and create customized practice quizzes.
7. **System-Level OS Automation**
   - Executes operating system-level automation scripts via natural language commands.
   - Capable of performing file manipulation tasks (e.g., reading, creating, deleting, and batch renaming messy lab files to a specific format).

## 2. Non-functional Requirements
- **Usability:** The GUI must cleanly separate the main chat interface from the Thought Trace panel to prevent information overload. Rich text and generated schedules must be rendered elegantly.
- **Safety & Security** Sensitive user credentials (e.g., Blackboard passwords) must be securely encrypted. The system must strictly adheres to the HITL mechanism to prevent unauthorized local OS modifications.
- **Reliability:** The Agent must feature robust error handling. If a tool fails, the tool must return an error message to the LLM, allowing the Agent to autonomously reason and retry an alternative approach.
- **Performance:** System responses and thought traces should be streamed to minimize perceived latency. Local RAG vector searches should return context within 10 seconds.

## 3. Technical Requirements
- **Operating Environment:** Build and deploy in Windows OS on personal laptops, using Python 3.10.
- **Core Agent Framework:** `PydanticAI` will be used to orchestrate the core Agentic Loop (Perception, Reasoning, Tool Use, Observation.
- **GUI & Frontend Stack:**  Use `PyQt6` / `PySide6` to build the interactive interface, render markdown, and handle local OS permissions seamlessly.
- **Backend & Tooling:** 
  - `BeautifulSoup`/`Selenium` for scraping web data (Blackboard).
  - `PyMuPDF`/`python-pptx` for document parsing.
  - `os`/`shutil` for system-level file automation.
- **Database Layer:** `postgresql` for storing user profiles, credentials, and chat history. `ChromaDB` for the local vector database managing the RAG document embeddings.
- **LLM Engine:** High-performance models such as Claude Code or Deepseek capable of reliable function calling.

## 4. Data Requirements
- **Data Needed:**
  1. User authentication data, preferences, and historical dialogue records.
  2. Official SUSTech documents.
  3. Personal academic files (Lecture PPTs, Markdown notes, lab report and so on).
  4. Real-time scheduling data (Blackboard deadlines, SUSTech Calendar).
- **Data Acquisition Methods:**
  - Web data (Blackboard/Calendar) will be acquired via Python web scrapers/crawlers mimicking user login.
  - Official handbooks and lecture materials will be acquired via local file paths, processed through parsing scripts, and chunked into the Vector DB.
  - User profiles and chat history will be collected through GUI interactions and stored locally.
