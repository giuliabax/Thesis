# 🚀 Multi-Agent LLM Architecture (TDD-Oriented)

This repository contains a modular **multi-agent LLM system** designed to collaboratively generate **unit tests and implementation code** following a **Test-Driven Development (TDD)** workflow.  
The system uses **LangGraph** to orchestrate multi-step agent interactions, allowing agents to iterate, refine, and cooperate through a structured computational graph.

Each agent operates in its own isolated workspace, producing tests, implementations, and logs during the development cycle.

---

## ✨ Key Features

- **Multi-agent orchestration via LangGraph**  
  Agents communicate through well-defined graph nodes and edges.

- **Automated Test-Driven Development (TDD)**  
  A *Test Agent* generates tests → an *Implementation Agent* writes code → the loop repeats until tests pass.

- **Modular, maintainable architecture**  
  Nodes, edges, and model configurations are cleanly separated into dedicated files.

- **Supports local and cloud LLMs**  
  - Local inference via **Ollama**
  - Cloud models via **Google Gemini**

- **Isolated workspaces per agent**  
  Each agent writes to its own folder under `/workspace`.

---

## 📦 Folder Structure

```
├── edges.py # LangGraph / LangChain edges connecting nodes
├── nodes.py # Definitions for each graph node (agent logic)
├── models.py # LLM provider setup (Ollama or Gemini)
├── main.py # Entry point and graph execution logic
├── requirements.txt # Python dependencies
├── .env.example # Template for environment variables
└── workspace/ # Auto-generated output directory
├── agent_1/
│ ├── tests/
│ └── implementation/
├── agent_2/
└── ...
```


### 🗂️ Workspace Directory

During execution, the orchestrator creates a `workspace/` folder where each agent receives:

- `tests/` — Test files generated during the TDD cycle  
- `implementation/` — Code written by the agent  
- Log/prompts metadata (optional depending on configuration)

This ensures clean isolation and reproducible agent behavior.

---

## ⚙️ Prerequisites

Before running the system, create a `.env` file in the project root.  
Use `.env.example` as your template.

> **⚠️ IMPORTANT:**  
> Never commit your `.env` file to version control.

---

## 🧠 LLM Configuration

The system can run using either **Ollama** or **Gemini**.

---

### 🔹 Option 1: Using Ollama (Local Execution)

Install Ollama and pull your preferred models:

```bash
pip install ollama
ollama pull <model-name>
```

Then set environment variables:
```ini
LLM_PROVIDER=ollama
OLLAMA_NAMES=qwen2.5-coder:3b,gemma2:2b
OLLAMA_TEMPERATURES=0.1,0.1
```

You can substitute any models supported by Ollama.

---

### 🔹 Option 2: Using Google Gemini (Cloud)

If you prefer cloud-based inference, add:

```ini
LLM_PROVIDER=gemini
GOOGLE_API_KEY=<your api key>
GEMINI_MODELS=gemini-2.5-flash-lite,gemini-2.5-flash
GEMINI_TEMPERATURES=0.1,0.1
```

## ▶️ Running the Application

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the orchestrator:
```bash
python main.py
```

This will:

1. Load the LangGraph agent graph defined in `main.py`
2. Initialize all agents
3. Create a workspace for each agent
4. Begin the automated TDD generation loop
5. Produce tests and code inside the `/workspace/...` directory

Each execution creates or updates a dedicated workspace folder for each agent, containing:

- `test.pt` — the final test file generated during the agent execution
- `implementation.py` — the final implementation file generated during the agent execution 
- `history/` — a sub folder containing the history of file changed by the agent during refactoring

---

## 🐞 Bug Reports

To report a bug, please open a GitHub issue and include:

- Clear steps to reproduce the issue  
- Relevant logs or artefacts from the agent’s `workspace/<agent>/` folder  
- Non-sensitive environment configuration details  
  *(never share API keys or secrets)*

Providing sample input and the expected vs. actual output helps speed up investigation.

---

## 🧭 Future Improvements

- New agent roles (Refactor Agent, Critic Agent, Security Agent)
- CI integration to automatically validate generated output
- A visual dashboard for LangGraph execution tracing
- Metrics for code quality, stability, and convergence
- Preset configurations for different TDD workflows
- Optional memory between iterations for long-running agent collaborations