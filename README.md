# CMS Insights v4 - Strategic Healthcare Intelligence Platform

A comprehensive healthcare policy analysis platform that scrapes CMS announcements, performs AI-powered impact analysis, and generates strategic reports for pharmaceutical companies like Amgen.

## 🚀 Features

### Core Functionality
- **CMS Article Scraping**: Automated extraction of articles from CMS newsroom
- **AI-Powered Analysis**: Sentiment analysis and comprehensive impact scoring
- **Strategic Reporting**: Generate detailed business impact reports with PDF export
- **Interactive Chat**: Chat with articles and strategic reports using AI
- **Deep Search**: Multi-source search across credible healthcare publications

### Advanced Capabilities
- **Regulatory Change Classification**: Identify regulation, guidance, standards, or policy changes
- **Cross-Functional Impact Assessment**: Analyze effects across business functions
- **Scope Determination**: Assess product vs. process impact
- **Remediation Lifecycle Management**: Complete implementation planning
- **Competitive Analysis**: Strategic positioning and market implications

## 🏗️ Architecture

### Backend (Flask)
- **Web Scraping**: BeautifulSoup4 for content extraction
- **AI Integration**: Google Gemini for analysis and chat
- **Search Engines**: DuckDuckGo and Tavily for expanded search
- **PDF Generation**: ReportLab for professional reports

### Frontend (React + TypeScript)
- **Modern UI**: Responsive design with Tailwind CSS
- **Real-time Updates**: Live progress tracking for long operations
- **Interactive Components**: Expandable panels, chat interface
- **Professional Branding**: Amgen-focused color scheme (#000048)

## 📋 Prerequisites

- Python 3.8+
- Node.js 16+
- API Keys:
  - Google Gemini API
  - Tavily Search API (optional)

## 🛠️ Installation

### 1. Backend Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env
```

### 2. Configure Environment Variables
Edit `.env` file:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
LANGCHAIN_API_KEY=your_langchain_key_here
LANGCHAIN_PROJECT=CMSInsights
LANGCHAIN_TRACING_V2=true
```

### 3. Frontend Setup (Optional - for separate React development)
```bash
# Install Node.js dependencies (if using separate React dev server)
npm install

# For development with hot reload
npm start

# For production build
npm run build
```

**Note**: The Flask app serves the built React application by default. Separate React development server is only needed for frontend development with hot reload.

## 🚀 Usage

### Start the Application

#### Method 1: Backend Only (Recommended for Development)
```bash
# Start Flask backend
python app.py

# The application runs on http://localhost:5001
# Open your browser and go to http://localhost:5001
```

#### Method 2: Full Stack Development
```bash
# Terminal 1: Start Flask backend
python app.py

# Terminal 2: Start React development server (if using separate frontend)
npm start
# React dev server runs on http://localhost:3000
```

#### Method 3: Production Build
```bash
# Build React frontend
npm run build

# Start Flask backend (serves built React app)
python app.py

# Access application at http://localhost:5001
```

### Quick Start Commands
```bash
# Setup and start
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start application
python app.py
```

### Core Workflows

#### 1. Article Analysis
1. **Scrape Articles**: Fetch latest CMS announcements
2. **Impact Analysis**: AI-powered scoring (0-10) with comprehensive reasoning
3. **Sentiment Analysis**: Positive/Negative/Neutral classification
4. **Strategic Actions**: Get recommended action plans

#### 2. Deep Search & Context Generation
1. **Deep Search**: Find related articles from credible sources
2. **Select Articles**: Choose relevant articles using checkboxes
3. **Generate Context**: Create summaries and insights for selected articles
4. **Strategic Report**: Comprehensive business impact analysis

#### 3. Interactive Features
- **Chat with Articles**: Ask questions about specific articles
- **Chat with Reports**: Discuss strategic implications
- **Download Options**: PDF and text formats
- **Real-time Progress**: Live updates during processing

## 📊 Impact Scoring System

### Comprehensive Scoring Criteria (0-10)

#### Regulatory Change Classification
- **Regulation Changes** (FDA/CMS binding): +3-4 points
- **Guidance Changes** (FDA interpretive): +2-3 points
- **Standards Changes** (Quality/technical): +1-2 points
- **Policy Changes** (Reimbursement/coverage): +2-3 points

#### Cross-Functional Impact
- **Single Function**: +1 point
- **2-3 Functions**: +2 points
- **4-5 Functions**: +3 points
- **Enterprise-wide**: +4 points

#### Scope Determination
- **Process Only**: Base score
- **Single Product Line**: +1 point
- **Multiple Product Lines**: +2 points
- **Entire Portfolio**: +3 points
- **Industry-wide**: +4 points

#### Remediation Complexity
- **Documentation Only**: +0 points
- **Process Modifications**: +1 point
- **System Changes + Testing**: +2 points
- **Regulatory Submissions**: +3 points
- **Multi-year Implementation**: +4 points

### Impact Categories
- **0-2**: Low Impact
- **3-4**: Moderate Impact
- **5-6**: Significant Impact
- **7-8**: High Impact
- **9**: Very High Impact
- **10**: Extremely High Impact

## 🔧 API Endpoints

### Core APIs
- `GET /api/cms-articles` - Scrape CMS articles
- `GET /api/analyze-article?url=<URL>` - Analyze article impact
- `GET /api/summarize-article?url=<URL>` - Generate article summary
- `GET /api/expanded-search?title=<TITLE>` - Search related articles
- `GET /api/generate-insights?url=<URL>` - Generate key insights
- `POST /api/generate-report` - Create strategic report
- `POST /api/chat-with-article` - Interactive chat functionality
- `GET /api/chat-status` - Chat session status

## 📁 Project Structure

```
CMSInsights-v4/
├── app.py                 # Flask backend application
├── requirements.txt       # Python dependencies
├── .env                  # Environment variables
├── config.json           # Credible sources configuration
├── components/           # React components
│   ├── ArticleCard.tsx   # Article display component
│   ├── LoadingSpinner.tsx # Loading indicators
│   └── ErrorMessage.tsx  # Error handling
├── types.ts              # TypeScript type definitions
├── App.tsx               # Main React application
├── public/               # Static assets
└── README.md            # This file
```

## 🎨 UI Components

### Main Interface
- **Article Grid**: Responsive card layout with pagination
- **Side Panel**: Expandable analysis and chat interface
- **Navigation**: Sidebar with filtering options
- **Professional Branding**: Cognizant/Amgen color scheme

### Interactive Elements
- **Deep Search**: Multi-source article discovery
- **Context Generation**: Progressive article processing
- **Report Generation**: Professional PDF and text export
- **Chat Interface**: Real-time AI conversations

## 🔒 Security & Best Practices

### Environment Security
- API keys stored in `.env` file (not committed)
- Secure API key handling in production
- Rate limiting for external API calls

### Data Handling
- No sensitive data storage
- Session-based chat management
- Automatic cleanup of expired sessions



## 🔄 Version History

### v4.0.0 (Current)
- Comprehensive regulatory impact analysis
- Multi-source search integration
- Professional PDF report generation
- Interactive chat with strategic reports
- Enhanced UI with Amgen branding

### Key Improvements
- Advanced impact scoring system
- Cross-functional impact assessment
- Remediation lifecycle management
- Real-time progress tracking
- Professional report formatting

---

**Built with ❤️ for strategic healthcare intelligence**