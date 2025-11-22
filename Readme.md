# LLM Analysis Quiz Solver

Automated quiz solver using Playwright for browser automation and Claude (Anthropic) for question solving.

## Architecture

```
API Request → Flask Server → Quiz Solver → Browser Handler → LLM Handler
                                    ↓
                              Gather Resources
                                    ↓
                              Solve Question
                                    ↓
                              Submit Answer
```

## Setup Instructions

### 1. Local Development

```bash
# Clone the repository
git clone <your-repo-url>
cd llm-quiz-solver

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Configure environment variables
cp .env.example .env
# Edit .env with your credentials

# Run the server
python app.py
```

### 2. Docker Deployment

```bash
# Build the Docker image
docker build -t quiz-solver .

# Run the container
docker run -p 5000:5000 \
  -e QUIZ_EMAIL="your-email@example.com" \
  -e QUIZ_SECRET="your-secret" \
  -e ANTHROPIC_API_KEY="your-api-key" \
  quiz-solver
```

### 3. Cloud Deployment (Render.com)

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Configure:
   - **Environment**: Docker
   - **Build Command**: (automatic from Dockerfile)
   - **Start Command**: (automatic from Dockerfile)
4. Add Environment Variables:
   - `QUIZ_EMAIL`
   - `QUIZ_SECRET`
   - `ANTHROPIC_API_KEY`
5. Deploy!

### 4. Alternative: Railway/Fly.io

Similar steps - connect repo, set environment variables, deploy.

## API Endpoints

### `POST /quiz`
Main endpoint to receive quiz tasks.

**Request:**
```json
{
  "email": "your-email@example.com",
  "secret": "your-secret",
  "url": "https://example.com/quiz-834"
}
```

**Response:**
```json
{
  "status": "accepted",
  "message": "Quiz processing started",
  "url": "https://example.com/quiz-834"
}
```

### `GET /health`
Health check endpoint.

## Testing

Test your endpoint locally:

```bash
curl -X POST http://localhost:5000/quiz \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your-email@example.com",
    "secret": "your-secret",
    "url": "https://tds-llm-analysis.s-anand.net/demo"
  }'
```

## Project Structure

llm-quiz-solver/
├── app.py                    ✅ Main Flask server
├── quiz_solver.py            ✅ Quiz solving logic
├── browser_handler.py        ✅ Playwright automation
├── llm_handler.py           ✅ Claude integration
├── data_analyzer.py         ✅ Data analysis utilities
├── requirements.txt         ✅ Python dependencies
├── Dockerfile              ✅ Docker configuration
├── .gitignore              ✅ Files to ignore
├── LICENSE                 ✅ MIT License
├── README.md               ✅ Documentation
└── .env.example            ✅ Environment template (NO .env!)

## Key Features

✅ **Browser Automation**: Renders JavaScript pages using Playwright  
✅ **PDF Parsing**: Extracts text from PDF files  
✅ **Resource Gathering**: Downloads files, scrapes websites  
✅ **LLM Integration**: Uses Claude for question understanding & solving  
✅ **Chain Solving**: Automatically chains through multiple quizzes  
✅ **Timeout Handling**: Respects 3-minute time limit  
✅ **Error Recovery**: Retries failed attempts  
✅ **Payload Validation**: Checks JSON format and secret  

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `QUIZ_EMAIL` | Your email from Google Form | Yes |
| `QUIZ_SECRET` | Your secret string from Google Form | Yes |
| `ANTHROPIC_API_KEY` | Your Claude API key | Yes |
| `PORT` | Server port (default: 5000) | No |

## Troubleshooting

### Browser not launching
- Ensure Playwright is installed: `playwright install chromium`
- Install system dependencies: `playwright install-deps`

### API Key errors
- Verify your Anthropic API key is valid
- Check you have sufficient credits

### Timeout issues
- The system has a 3-minute limit per quiz chain
- Optimize resource gathering and LLM calls

## License

MIT License - See LICENSE file for details