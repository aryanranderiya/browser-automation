# CrustData Browser Automation

A powerful browser automation platform with a FastAPI backend and Next.js frontend for automating web interactions with natural language commands

## Project Overview

CrustData Browser Automation is a comprehensive tool that allows you to automate browser interactions through an API. It combines a FastAPI backend for robust browser automation with a sleek Next.js frontend for configuration, monitoring, and control.

## Key Features

### Backend Features

- **Natural Language Command Processing**: Convert plain English instructions into browser actions
- **Automated Browser Control**: Navigate, click, search, fill forms and extract data
- **Session Management**: Persistent browser sessions with resumable state
- **Captcha Detection & Handling**: Pause automation for manual captcha resolution
- **Content Extraction**: Extract text, tables, links, and structured data (JSON-LD)
- **Structured API**: Well-documented REST API with Swagger UI
- **Error Handling & Recovery**: Robust error management and fallback mechanisms
- **Asynchronous Operation**: Non-blocking command execution with status reporting
- **Intelligent Command Sequencing**: Chain multiple commands together intelligently

### Frontend Features

- **Intuitive UI**: Clean interface for configuring and monitoring automation tasks
- **Real-time Feedback**: Live updates of browser automation status
- **Task Monitoring**: Track progress of complex automation workflows
- **Custom Command Configuration**: Easily customize automation parameters
- **Form Handling**: Simplified interface for form automation tasks
- **Responsive Design**: Works across desktop and mobile devices
- **Authentication**: Secure access to automation capabilities

## Project Structure

```
.
├── backend/                       # FastAPI backend for browser automation
│   ├── main.py                    # Main application entry point
│   ├── models/                    # Pydantic data models
│   │   └── interaction.py         # Models for browser interactions
│   ├── routes/                    # API routes
│   │   └── routes.py              # API endpoints definitions
│   ├── services/                  # Core business logic
│   │   ├── browser_service.py     # Browser automation implementation
│   │   ├── command_service.py     # Natural language command processing
│   │   └── interaction_service.py # User interaction handling
│   ├── utils/                     # Utility modules
│   │   ├── browser_session.py     # Browser session management
│   │   ├── browser_utils.py       # Browser-related helper functions
│   │   └── logger.py              # Logging configuration
│   └── prompts/                   # LLM prompts for command processing
│       └── system_prompt.py       # System prompts for LLM interactions
│
└── frontend/                      # Next.js frontend application
    ├── public/                    # Static assets
    ├── src/                       # Source code
    │   ├── app/                   # Next.js app directory (pages & layouts)
    │   ├── components/            # Reusable UI components
    │   ├── lib/                   # Utility functions and hooks
    │   └── styles/                # CSS and styling
    ├── next.config.ts             # Next.js configuration
    └── package.json               # Project dependencies
```

## Detailed Installation & Setup Instructions

### Backend Installation

#### Prerequisites

- Python 3.10+ installed
- Chrome or Chromium browser installed for automation tasks

#### Option 1: Using UV (Recommended)

1. Install uv if not already installed:

```bash
pip install uv
```

2. Navigate to the backend directory:

```bash
cd backend
```

3. Create a virtual environment and install project dependencies:

```bash
uv venv
uv pip install -e .
```

4. Create a `.env` file with your API keys:

```bash
echo "OPENAI_API_KEY=your_openai_key" > .env
# OR for alternative providers:
# echo "GROQ_API_KEY=your_groq_key" > .env
# echo "GEMINI_API_KEY=your_gemini_key" > .env
```

#### Option 2: Using pip

1. Navigate to the backend directory:

```bash
cd backend
```

2. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install project dependencies:

```bash
pip install -e .
```

4. Create a `.env` file with your API keys:

```bash
echo "OPENAI_API_KEY=your_openai_key" > .env
# OR for alternative providers:
# echo "GROQ_API_KEY=your_groq_key" > .env
# echo "GEMINI_API_KEY=your_gemini_key" > .env
```

### Running the Backend

1. Ensure your virtual environment is activated:

```bash
# If using uv:
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# If using pip:
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Start the backend server:

```bash
python main.py
```

The API will be available at http://localhost:8000. You can access the Swagger UI documentation at http://localhost:8000/docs.

### Frontend Installation

#### Prerequisites

- Node.js 18+ installed

#### Option 1: Using pnpm (Recommended)

1. Install pnpm if not already installed:

```bash
npm install -g pnpm
```

2. Navigate to the frontend directory:

```bash
cd frontend
```

3. Install dependencies:

```bash
pnpm install
```

4. Create a `.env.local` file with backend API URL:

```bash
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
```

#### Option 2: Using npm

1. Navigate to the frontend directory:

```bash
cd frontend
```

2. Install dependencies:

```bash
npm install
```

3. Create a `.env.local` file with backend API URL:

```bash
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
```

#### Option 3: Using Yarn

1. Install Yarn if not already installed:

```bash
npm install -g yarn
```

2. Navigate to the frontend directory:

```bash
cd frontend
```

3. Install dependencies:

```bash
yarn install
```

4. Create a `.env.local` file with backend API URL:

```bash
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
```

### Running the Frontend

#### Using pnpm (Recommended)

Development mode:

```bash
cd frontend
pnpm dev
```

Production build:

```bash
cd frontend
pnpm build
pnpm start
```

#### Using npm

Development mode:

```bash
cd frontend
npm run dev
```

Production build:

```bash
cd frontend
npm run build
npm run start
```

#### Using Yarn

Development mode:

```bash
cd frontend
yarn dev
```

Production build:

```bash
cd frontend
yarn build
yarn start
```

The frontend will be available at http://localhost:3000.

### Running Both Services Simultaneously

For development, you'll need to run both the backend and frontend in separate terminals:

Terminal 1 (Backend):

```bash
cd backend
source .venv/bin/activate  # or your virtual env activation command
python main.py
```

Terminal 2 (Frontend):

```bash
cd frontend
pnpm dev  # or npm run dev or yarn dev
```
