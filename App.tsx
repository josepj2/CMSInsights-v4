
import React, { useState, useEffect, useRef } from 'react';
import { PythonArticle, FetchState, AnalysisResult, SummarizeResult } from './types';
import LoadingSpinner from './components/LoadingSpinner';
import ErrorMessage from './components/ErrorMessage';
import ArticleCard from './components/ArticleCard';

const ITEMS_PER_PAGE = 6;

const App: React.FC = () => {
  const [articles, setArticles] = useState<PythonArticle[]>([]);
  const [fetchState, setFetchState] = useState<FetchState>(FetchState.IDLE);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);

  // State for Side Panel
  const [sidePanelOpen, setSidePanelOpen] = useState<boolean>(false);
  const [sidePanelFeature, setSidePanelFeature] = useState<'analysis' | 'summary' | 'chat' | 'deepsearch' | null>(null);
  
  // State for Article Analysis
  const [analysisTargetUrl, setAnalysisTargetUrl] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [analysisFetchState, setAnalysisFetchState] = useState<FetchState>(FetchState.IDLE);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // State for Article Summarization
  const [summaryTargetUrl, setSummaryTargetUrl] = useState<string | null>(null);
  const [summaryResult, setSummaryResult] = useState<SummarizeResult | null>(null);
  const [summaryFetchState, setSummaryFetchState] = useState<FetchState>(FetchState.IDLE);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [showSummaryModal, setShowSummaryModal] = useState<boolean>(false);

  // State for Chat
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [chatStatus, setChatStatus] = useState<'idle' | 'loading' | 'analyzing' | 'ready' | 'error'>('idle');
  const [chatProgressMessage, setChatProgressMessage] = useState<string>('');
  const [chatMessages, setChatMessages] = useState<Array<{role: 'user' | 'assistant', content: string}>>([]);
  const [chatSuggestedQuestions, setChatSuggestedQuestions] = useState<string[]>([]);
  const [chatTargetUrl, setChatTargetUrl] = useState<string | null>(null);
  const [chatMessageLoading, setChatMessageLoading] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  // State for Deep Search
  const [deepSearchResults, setDeepSearchResults] = useState<any[]>([]);
  const [deepSearchLoading, setDeepSearchLoading] = useState<boolean>(false);
  const [deepSearchError, setDeepSearchError] = useState<string | null>(null);
  const [showAllSources, setShowAllSources] = useState<boolean>(false);
  const [currentSearchTitle, setCurrentSearchTitle] = useState<string>('');
  const [selectedArticles, setSelectedArticles] = useState<Set<number>>(new Set());
  const [expandedContext, setExpandedContext] = useState<any[]>([]);
  const [contextGenerating, setContextGenerating] = useState<boolean>(false);
  const [contextProgress, setContextProgress] = useState<string>('');
  const [contextGenerated, setContextGenerated] = useState<boolean>(false);
  const [expandedContextItems, setExpandedContextItems] = useState<Set<number>>(new Set());
  const [reportGenerating, setReportGenerating] = useState<boolean>(false);
  const [reportGenerated, setReportGenerated] = useState<boolean>(false);
  const [reportContent, setReportContent] = useState<string>('');
  const [reportPdfBase64, setReportPdfBase64] = useState<string>('');




  useEffect(() => {
    const loadArticles = async () => {
      setFetchState(FetchState.LOADING);
      setError(null);
      try {
        const response = await fetch('./cms_articles_details.json'); 
        if (!response.ok) {
          throw new Error(`Failed to load articles JSON: ${response.status} ${response.statusText}. Ensure 'cms_articles_details.json' is accessible.`);
        }
        const data: PythonArticle[] = await response.json();
        setArticles(data);
        setFetchState(FetchState.SUCCESS);
      } catch (err) {
        console.error("Error loading articles:", err);
        if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("An unknown error occurred while loading articles.");
        }
        setFetchState(FetchState.ERROR);
      }
    };
    loadArticles();
  }, []);

  const handleAnalyzeArticleClick = async (articleLink: string) => {
    console.log("Frontend: Analyzing article:", articleLink);
    setAnalysisTargetUrl(articleLink);
    setSidePanelOpen(true);
    setSidePanelFeature('analysis');
    setAnalysisFetchState(FetchState.LOADING);
    setAnalysisResult(null);
    setAnalysisError(null);
    try {
      const response = await fetch(`http://localhost:5001/api/analyze-article?url=${encodeURIComponent(articleLink)}`);
      if (!response.ok) {
        let errorMsg = `HTTP error ${response.status} - ${response.statusText}`;
        try { const errorData = await response.json(); errorMsg = errorData.error || errorMsg; } catch (e) { /* ignore */ }
        throw new Error(errorMsg);
      }
      const data: AnalysisResult = await response.json();
      setAnalysisResult(data);
      setAnalysisFetchState(FetchState.SUCCESS);
    } catch (err) {
      console.error("Frontend: Error fetching analysis:", err);
      if (err instanceof Error) { setAnalysisError(err.message); } else { setAnalysisError("An unknown error occurred while fetching analysis."); }
      setAnalysisFetchState(FetchState.ERROR);
    }
  };

  const handleCloseSidePanel = () => {
    setSidePanelOpen(false);
    setSidePanelFeature(null);
    setAnalysisTargetUrl(null);
    setAnalysisResult(null);
    setAnalysisFetchState(FetchState.IDLE);
    setAnalysisError(null);
    setSummaryTargetUrl(null);
    setSummaryResult(null);
    setSummaryFetchState(FetchState.IDLE);
    setSummaryError(null);
    // Clean up chat state
    if (chatSessionId) {
      fetch('http://localhost:5001/api/chat-with-article', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'close', session_id: chatSessionId })
      }).catch(console.error);
    }
    setChatSessionId(null);
    setChatStatus('idle');
    setChatProgressMessage('');
    setChatMessages([]);
    setChatSuggestedQuestions([]);
    setChatTargetUrl(null);
    setChatMessageLoading(false);
  };

  const handleSummarizeArticleClick = async (articleLink: string) => {
    console.log("Frontend: Summarizing article:", articleLink);
    setSummaryTargetUrl(articleLink);
    setSidePanelOpen(true);
    setSidePanelFeature('summary');
    setSummaryFetchState(FetchState.LOADING);
    setSummaryResult(null);
    setSummaryError(null);
    try {
      const response = await fetch(`http://localhost:5001/api/summarize-article?url=${encodeURIComponent(articleLink)}`);
      if (!response.ok) {
        let errorMsg = `HTTP error ${response.status} - ${response.statusText}`;
        try { const errorData = await response.json(); errorMsg = errorData.error || errorMsg; } catch (e) { /* ignore */ }
        throw new Error(errorMsg);
      }
      const data: SummarizeResult = await response.json();
      setSummaryResult(data);
      setSummaryFetchState(FetchState.SUCCESS);
    } catch (err) {
      console.error("Frontend: Error fetching summary:", err);
      if (err instanceof Error) { setSummaryError(err.message); } else { setSummaryError("An unknown error occurred while fetching summary."); }
      setSummaryFetchState(FetchState.ERROR);
    }
  };

  const handleCloseSummaryModal = () => {
    setShowSummaryModal(false);
    setSummaryTargetUrl(null);
    setSummaryResult(null);
    setSummaryFetchState(FetchState.IDLE);
    setSummaryError(null);
  };

  // Chat status polling effect
  useEffect(() => {
    if (!chatSessionId || chatStatus === 'ready' || chatStatus === 'error') return;
    
    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(`http://localhost:5001/api/chat-status?session_id=${chatSessionId}`);
        if (!response.ok) throw new Error('Failed to fetch status');
        
        const data = await response.json();
        console.log('Chat status update:', data); // Debug log
        
        setChatStatus(data.status);
        setChatProgressMessage(data.progress_message || '');
        
        if (data.status === 'ready' && data.message) {
          setChatMessages([{ role: 'assistant', content: data.message }]);
          setChatSuggestedQuestions(data.suggested_questions || []);
          clearInterval(pollInterval);
        } else if (data.status === 'error') {
          clearInterval(pollInterval);
        }
      } catch (error) {
        console.error('Error polling chat status:', error);
        setChatStatus('error');
        setChatProgressMessage('Failed to load chat');
        clearInterval(pollInterval);
      }
    }, 1500);
    
    return () => clearInterval(pollInterval);
  }, [chatSessionId, chatStatus]);

  const handleDeepSearchClick = async (articleTitle: string) => {
    console.log("Frontend: Deep search for article:", articleTitle);
    setSidePanelOpen(true);
    setSidePanelFeature('deepsearch');
    setDeepSearchLoading(true);
    setDeepSearchResults([]);
    setDeepSearchError(null);
    setShowAllSources(false);
    setCurrentSearchTitle(articleTitle);
    
    try {
      const response = await fetch(`http://localhost:5001/api/expanded-search?title=${encodeURIComponent(articleTitle)}&max_results=5`);
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }
      const data = await response.json();
      setDeepSearchResults(data.results || []);
      setDeepSearchLoading(false);
    } catch (err) {
      console.error("Frontend: Error in deep search:", err);
      setDeepSearchError(err instanceof Error ? err.message : "Deep search failed");
      setDeepSearchLoading(false);
    }
  };

  const handleShowAllSources = async (articleTitle: string) => {
    setDeepSearchLoading(true);
    setShowAllSources(true);
    
    try {
      const response = await fetch(`http://localhost:5001/api/expanded-search?title=${encodeURIComponent(articleTitle)}&max_results=15`);
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }
      const data = await response.json();
      setDeepSearchResults(data.results || []);
      setDeepSearchLoading(false);
    } catch (err) {
      console.error("Frontend: Error in expanded search:", err);
      setDeepSearchError(err instanceof Error ? err.message : "Expanded search failed");
      setDeepSearchLoading(false);
    }
  };

  const handleGenerateExpandedContext = async () => {
    setContextGenerating(true);
    setExpandedContext([]);
    setContextProgress('');
    
    const selectedResults = Array.from(selectedArticles).map(index => deepSearchResults[index]);
    
    for (let i = 0; i < selectedResults.length; i++) {
      const result = selectedResults[i];
      setContextProgress(`Processing article ${i + 1} of ${selectedResults.length}: ${result.title}`);
      
      try {
        // Get summary
        const summaryResponse = await fetch(`http://localhost:5001/api/summarize-article?url=${encodeURIComponent(result.url)}`);
        const summaryData = summaryResponse.ok ? await summaryResponse.json() : null;
        
        // Get insights
        setContextProgress(`Generating insights for article ${i + 1} of ${selectedResults.length}: ${result.title}`);
        const insightsResponse = await fetch(`http://localhost:5001/api/generate-insights?url=${encodeURIComponent(result.url)}`);
        const insightsData = insightsResponse.ok ? await insightsResponse.json() : null;
        
        setExpandedContext(prev => [...prev, {
          title: result.title,
          url: result.url,
          source: result.source,
          date: result.date,
          summary: summaryData?.summary || 'Summary not available',
          insights: insightsData?.insights || 'Insights not available'
        }]);
      } catch (error) {
        console.error('Error processing article:', error);
        setExpandedContext(prev => [...prev, {
          title: result.title,
          url: result.url,
          source: result.source,
          date: result.date,
          summary: 'Error processing article',
          insights: 'Insights not available'
        }]);
      }
      
      if (i < selectedResults.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }
    
    setContextGenerating(false);
    setContextGenerated(true);
    setContextProgress('Context generation completed!');
  };

  const handlePrepareReport = async () => {
    console.log('Preparing report with expanded context:', expandedContext);
    
    setReportGenerating(true);
    setContextProgress('Preparing comprehensive strategic report...');
    
    // Get original article data for context
    const originalArticle = {
      title: currentSearchTitle,
      impact: articles[0]?.Impact || 'Moderate',
      impact_score: articles[0]?.Impact_score || 5,
      impact_reason: articles[0]?.Impact_score_reason || 'No analysis available',
      sentiment: articles[0]?.Sentiment || 'Neutral'
    };
    
    try {
      setContextProgress('Analyzing business impact and competitive landscape...');
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      setContextProgress('Generating strategic recommendations and action plans...');
      await new Promise(resolve => setTimeout(resolve, 500));
      
      setContextProgress('Finalizing executive summary and risk assessment...');
      
      const response = await fetch('http://localhost:5001/api/generate-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expanded_context: expandedContext,
          original_article: originalArticle
        })
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }
      
      const data = await response.json();
      
      setContextProgress('Strategic report generated successfully!');
      setReportContent(data.report);
      setReportPdfBase64(data.pdf_base64 || '');
      setReportGenerated(true);
      setReportGenerating(false);
      
    } catch (error) {
      console.error('Error generating report:', error);
      setContextProgress('Report generation failed. Please try again.');
      setReportGenerating(false);
      setReportGenerated(false);
      alert('Failed to generate report. Please try again.');
    }
  };

  const handleDownloadPDF = () => {
    if (reportPdfBase64) {
      try {
        const byteCharacters = atob(reportPdfBase64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: 'application/pdf' });
        
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Amgen_Strategic_Report_${new Date().toISOString().split('T')[0]}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } catch (error) {
        console.error('Error downloading PDF:', error);
        alert('Error downloading PDF. Please try again.');
      }
    } else {
      alert('PDF not available. Please regenerate the report.');
    }
  };

  const handleChatWithReport = async () => {
    console.log('Frontend: Starting chat with report context');
    setChatTargetUrl('Strategic Report');
    setSidePanelFeature('chat');
    setChatMessages([]);
    setChatSuggestedQuestions([]);
    
    try {
      const response = await fetch('http://localhost:5001/api/chat-with-article', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          action: 'start', 
          url: articles[0]?.['Article Link'] || '',
          additional_context: reportContent,
          context_type: 'strategic_report'
        })
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }
      
      const data = await response.json();
      console.log('Chat with report start response:', data);
      
      setChatSessionId(data.session_id);
      setChatStatus(data.status);
      setChatProgressMessage(data.progress_message || '');
      
      if (data.status === 'error') {
        setChatMessages([{ role: 'assistant', content: data.message }]);
      }
    } catch (error) {
      console.error('Error starting chat with report:', error);
      setChatStatus('error');
      setChatProgressMessage('Failed to start chat');
    }
  };

  const handleChatArticleClick = async (articleLink: string) => {
    console.log("Frontend: Starting chat for article:", articleLink);
    setChatTargetUrl(articleLink);
    setSidePanelOpen(true);
    setSidePanelFeature('chat');
    setChatMessages([]);
    setChatSuggestedQuestions([]);
    
    try {
      const response = await fetch('http://localhost:5001/api/chat-with-article', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start', url: articleLink })
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }
      
      const data = await response.json();
      console.log('Chat start response:', data); // Debug log
      
      setChatSessionId(data.session_id);
      setChatStatus(data.status);
      setChatProgressMessage(data.progress_message || '');
      
      if (data.status === 'error') {
        setChatMessages([{ role: 'assistant', content: data.message }]);
      }
    } catch (error) {
      console.error('Error starting chat:', error);
      setChatStatus('error');
      setChatProgressMessage('Failed to start chat');
    }
  };

  const handleSendChatMessage = async (message: string) => {
    if (!chatSessionId || !message.trim() || chatMessageLoading) return;
    
    // Add user message to chat and show loading
    setChatMessages(prev => [...prev, { role: 'user', content: message }]);
    setTimeout(() => {
      if (chatContainerRef.current) {
        chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
      }
    }, 100);
    setChatMessageLoading(true);
    
    try {
      const response = await fetch('http://localhost:5001/api/chat-with-article', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          action: 'message', 
          session_id: chatSessionId, 
          message 
        })
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }
      
      const data = await response.json();
      setChatMessages(prev => [...prev, { role: 'assistant', content: data.message }]);
      setChatSuggestedQuestions(data.suggested_questions || []);
      setTimeout(() => {
        if (chatContainerRef.current) {
          chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
        }
      }, 100);
    } catch (error) {
      console.error('Error sending chat message:', error);
      setChatMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' }]);
    } finally {
      setChatMessageLoading(false);
    }
  };


  // Pagination logic
  const totalPages = Math.ceil(articles.length / ITEMS_PER_PAGE);
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const endIndex = startIndex + ITEMS_PER_PAGE;
  const currentArticles = articles.slice(startIndex, endIndex);
  const handleNextPage = () => setCurrentPage((prevPage: number) => Math.min(prevPage + 1, totalPages));
  const handlePreviousPage = () => setCurrentPage((prevPage: number) => Math.max(prevPage - 1, 1));

  const PaginationControls: React.FC = () => {
    if (totalPages <= 1) return null;
    return (
      <div className="flex justify-center items-center space-x-2 sm:space-x-4 my-4 sm:my-8">
        <button onClick={handlePreviousPage} disabled={currentPage === 1} className="px-2 py-1.5 bg-[#000048] text-white font-medium rounded text-xs hover:bg-[#000066] disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors duration-200">Previous</button>
        <span className="text-slate-700 text-xs px-2">Page {currentPage} of {totalPages}</span>
        <button onClick={handleNextPage} disabled={currentPage === totalPages} className="px-2 py-1.5 bg-[#000048] text-white font-medium rounded text-xs hover:bg-[#000066] disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors duration-200">Next</button>
      </div>
    );
  };



  const SummaryDisplay: React.FC = () => {
    if (!showSummaryModal) return null; 
    return (
      <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center p-2 sm:p-4 z-50 transition-opacity duration-300">
        <div className="bg-white p-4 sm:p-6 md:p-8 rounded-lg shadow-2xl max-w-sm sm:max-w-lg md:max-w-xl lg:max-w-2xl w-full max-h-[80vh] overflow-y-auto transform transition-all duration-300 scale-100">
          <div className="flex justify-between items-start mb-4">
            <h2 className="text-lg sm:text-xl md:text-2xl font-semibold text-slate-800">Article Summary</h2>
            <button onClick={handleCloseSummaryModal} className="text-slate-400 hover:text-slate-600 text-2xl sm:text-3xl leading-none font-bold" aria-label="Close summary">&times;</button>
          </div>
          {summaryTargetUrl && <p className="text-xs text-slate-500 mb-3 break-all">Summary for: <a href={summaryTargetUrl} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">{summaryTargetUrl}</a></p>}
          {summaryFetchState === FetchState.LOADING && <div className="py-8"><LoadingSpinner /></div>}
          {summaryFetchState === FetchState.ERROR && summaryError && <ErrorMessage message={summaryError} />}
          {summaryFetchState === FetchState.SUCCESS && summaryResult && (
            <div className="space-y-3 text-sm sm:text-base">
              <p className="text-slate-700 whitespace-pre-wrap bg-slate-50 p-4 rounded">{summaryResult.summary || "No summary content available."}</p>
            </div>
          )}
           <button onClick={handleCloseSummaryModal} className="mt-8 w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-2.5 px-4 rounded-md transition-colors duration-300">Close Summary</button>
        </div>
      </div>
    );
  };

  return (
    <div className="h-screen bg-white flex flex-col">
      <header className="w-full bg-[#000048] py-2 px-4 sm:py-2 sm:px-6 md:py-3 md:px-8">
        <div className="flex items-center justify-between">
          <img 
            src="/cognizant-logo.jpg" 
            alt="Cognizant Logo" 
            className="h-11 w-44 sm:h-12 sm:w-50 md:h-14 md:w-56 object-contain"
          />
          <h1 className="text-sm sm:text-lg md:text-xl lg:text-2xl font-bold text-white flex-1 text-center">CMS Announcements and Insights</h1>
          <div className="w-6 sm:w-7 md:w-8"></div>
        </div>
      </header>
      
      <div className="flex flex-col md:flex-row h-[85%]">
        {/* Sidebar Navigation */}
        <aside className={`${sidePanelOpen ? 'w-16' : 'w-full sm:w-1/5 md:w-1/6 lg:w-1/8'} bg-[#000048] text-white flex flex-col border border-gray-300 rounded-lg h-full transition-all duration-300`}>
          <div className="flex flex-col h-full justify-between">
              {/* Navigation Buttons */}
              <div className="flex-1 flex flex-col justify-center p-2 sm:p-3">
                <nav>
                  <ul className="space-y-3 sm:space-y-4">
                    <li>
                      <button className="w-full flex items-center justify-start py-3 px-2 sm:py-4 sm:px-3 rounded-xl text-slate-300 bg-white/10 hover:bg-slate-700 hover:text-white transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-xs sm:text-sm shadow-sm hover:shadow-md" title="Critical Actions">
                        {sidePanelOpen ? '⚠️' : '⚠️ Critical Actions'}
                      </button>
                    </li>
                    <li>
                      <button className="w-full flex items-center justify-start py-3 px-2 sm:py-4 sm:px-3 rounded-xl text-slate-300 bg-white/10 hover:bg-slate-700 hover:text-white transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-xs sm:text-sm shadow-sm hover:shadow-md" title="Negative News">
                        {sidePanelOpen ? '📉' : '📉 Negative News'}
                      </button>
                    </li>
                    <li>
                      <button className="w-full flex items-center justify-start py-3 px-2 sm:py-4 sm:px-3 rounded-xl text-slate-300 bg-white/10 hover:bg-slate-700 hover:text-white transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-xs sm:text-sm shadow-sm hover:shadow-md" title="Positive News">
                        {sidePanelOpen ? '📈' : '📈 Positive News'}
                      </button>
                    </li>
                    <li>
                      <button className="w-full flex items-center justify-start py-3 px-2 sm:py-4 sm:px-3 rounded-xl text-slate-300 bg-white/10 hover:bg-slate-700 hover:text-white transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-xs sm:text-sm shadow-sm hover:shadow-md" title="Neutral News">
                        {sidePanelOpen ? '➖' : '➖ Neutral News'}
                      </button>
                    </li>
                    <li>
                      <button className="w-full flex items-center justify-start py-3 px-2 sm:py-4 sm:px-3 rounded-xl text-slate-300 bg-white/10 hover:bg-slate-700 hover:text-white transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-xs sm:text-sm shadow-sm hover:shadow-md" title="Bookmarks">
                        {sidePanelOpen ? '🔖' : '🔖 Bookmarks'}
                      </button>
                    </li>
                    <li>
                      <button className="w-full flex items-center justify-start py-3 px-2 sm:py-4 sm:px-3 rounded-xl text-slate-300 bg-white/10 hover:bg-slate-700 hover:text-white transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-xs sm:text-sm shadow-sm hover:shadow-md" title="Help">
                        {sidePanelOpen ? '❓' : '❓ Help'}
                      </button>
                    </li>
                  </ul>
                </nav>
              </div>

              {/* Bottom Section: Profile */}
              <div className="p-2 sm:p-3 border-t border-gray-700/50 mt-auto">
                <div className="bg-white/10 p-1.5 sm:p-2 rounded-lg flex items-center justify-between">
                  <div className="flex items-center space-x-1 sm:space-x-2">
                    <img className="h-6 w-6 sm:h-8 sm:w-8 rounded-full object-cover" src="https://images.unsplash.com/photo-1438761681033-6461ffad8d80?q=80&w=2070&auto=format&fit=crop" alt="User Avatar" />
                    {!sidePanelOpen && (
                      <div className="hidden sm:block">
                        <p className="font-semibold text-xs text-white">Jane Doe</p>
                        <p className="text-xs bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded-full inline-block">Admin</p>
                      </div>
                    )}
                  </div>
                  <button className="p-1 sm:p-1.5 rounded-md hover:bg-white/20 transition-colors" aria-label="Logout">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 sm:h-4 sm:w-4 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                    </svg>
                  </button>
                </div>
              </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <div className="w-full sm:w-4/5 md:w-5/6 lg:w-7/8 bg-slate-50 flex flex-1 overflow-hidden">
          {/* Articles Section */}
          <main className={`flex-1 p-2 sm:p-4 container mx-auto overflow-y-auto transition-all duration-300 ${sidePanelOpen ? 'w-[60%]' : 'w-full'}`}>
            {fetchState === FetchState.LOADING && <LoadingSpinner />}
            {fetchState === FetchState.ERROR && error && <ErrorMessage message={error} />}
            
            {fetchState === FetchState.SUCCESS && (
              <div>
                {articles.length === 0 ? (
                  <div className="text-center text-gray-500 py-10 bg-white shadow-md rounded-lg">
                    <p className="text-2xl mb-2">📄</p><p className="text-xl">No articles found.</p><p>Ensure 'cms_articles_details.json' is in public folder for Vite.</p>
                  </div>
                ) : (
                  <>
                    <div className={`grid gap-2 sm:gap-4 transition-all duration-300 ${sidePanelOpen ? 'grid-cols-3 lg:grid-cols-2' : 'grid-cols-3'}`}>
                      {currentArticles.map((article, index) => (
                        <ArticleCard 
                          key={`${article["Article Link"]}-${startIndex + index}`} 
                          article={article}
                          onAnalyzeClick={handleAnalyzeArticleClick}
                          onSummarizeClick={handleSummarizeArticleClick}
                          onChatClick={handleChatArticleClick}
                          onDeepSearchClick={handleDeepSearchClick}
                        />
                      ))}
                    </div>
                    <PaginationControls />
                  </>
                )}
              </div>
            )}
          </main>
          
          {/* Side Panel */}
          {sidePanelOpen && (
            <div className="w-full sm:w-[40%] bg-white border border-slate-200 rounded-lg shadow-md flex flex-col animate-slide-in h-[calc(100vh-8rem)] m-2 overflow-hidden">
              <div className="flex justify-between items-center p-2 sm:p-3 md:p-4 bg-[#000048] border-b border-slate-200">
                <h2 className="text-sm sm:text-base md:text-lg font-semibold text-white text-center flex-1">
                  {sidePanelFeature === 'summary' ? 'Article Summary' : 
                   sidePanelFeature === 'chat' ? 'Article Chat' : 
                   sidePanelFeature === 'deepsearch' ? 'Deep Search Results' : 'Impact Analysis'}
                </h2>
                <button 
                  onClick={handleCloseSidePanel}
                  className="text-white hover:text-gray-200 text-xl sm:text-2xl leading-none font-bold"
                  aria-label="Close panel"
                >
                  &times;
                </button>
              </div>
              <div className="flex-1 p-2 sm:p-3 md:p-4 overflow-y-auto min-h-0 max-h-full">
                {sidePanelFeature === 'analysis' && (
                  <>
                    {analysisTargetUrl && (
                      <p className="text-xs text-slate-500 mb-2 break-all">
                        Analyzing: <a href={analysisTargetUrl} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">{analysisTargetUrl}</a>
                      </p>
                    )}
                    {analysisFetchState === FetchState.LOADING && (
                      <div className="flex items-center space-x-2 p-3">
                        <LoadingSpinner size="small" message="" />
                        <span className="text-sm text-slate-600">Performing impact analysis...</span>
                      </div>
                    )}
                    {analysisFetchState === FetchState.ERROR && analysisError && <ErrorMessage message={analysisError} />}
                    {analysisFetchState === FetchState.SUCCESS && analysisResult && (
                      <div className="space-y-4 text-xs">
                        <div>
                          <h4 className="font-semibold text-slate-700 text-xs mb-1">Sentiment:</h4>
                          <p className="font-medium text-xs text-white bg-[#000048] p-2 rounded border border-[#000048]">
                            {analysisResult.sentiment || "Not available"}
                          </p>
                        </div>
                        <div>
                          <h4 className="font-semibold text-slate-700 text-xs mb-1">Sentiment Justification:</h4>
                          <div className="text-slate-600 bg-slate-50 p-3 rounded max-h-48 overflow-y-auto text-xs border border-[#000048]" dangerouslySetInnerHTML={{__html: analysisResult.sentiment_justification || "Not available"}} />
                        </div>
                        <div>
                          <h4 className="font-semibold text-slate-700 text-xs mb-1">Why this is {analysisResult.impact_level}?</h4>
                          <p className="text-slate-600 whitespace-pre-wrap bg-slate-50 p-3 rounded max-h-48 overflow-y-auto text-xs border border-[#000048]">
                            {analysisResult.impact_reason || "Not available"}
                          </p>
                        </div>
                        <div>
                          <h4 className="font-semibold text-slate-700 text-xs mb-1">Plan of Action:</h4>
                          <div className="text-slate-600 bg-slate-50 p-3 rounded max-h-48 overflow-y-auto text-xs border border-[#000048]" dangerouslySetInnerHTML={{__html: analysisResult.plan_of_action || "Not available"}} />
                        </div>
                      </div>
                    )}
                  </>
                )}
                {sidePanelFeature === 'summary' && (
                  <>
                    {summaryTargetUrl && (
                      <p className="text-xs text-slate-500 mb-2 break-all">
                        Summary for: <a href={summaryTargetUrl} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">{summaryTargetUrl}</a>
                      </p>
                    )}
                    {summaryFetchState === FetchState.LOADING && (
                      <div className="flex items-center space-x-2 p-3">
                        <LoadingSpinner size="small" message="" />
                        <span className="text-sm text-slate-600">Generating summary...</span>
                      </div>
                    )}
                    {summaryFetchState === FetchState.ERROR && summaryError && <ErrorMessage message={summaryError} />}
                    {summaryFetchState === FetchState.SUCCESS && summaryResult && (
                      <div className="space-y-4 text-xs">
                        <div>
                          <h4 className="font-semibold text-slate-700 text-xs mb-1">Summary:</h4>
                          <p className="text-slate-600 whitespace-pre-wrap bg-slate-50 p-3 rounded max-h-96 overflow-y-auto text-xs border border-[#000048]">
                            {summaryResult.summary || "No summary content available."}
                          </p>
                        </div>
                      </div>
                    )}
                  </>
                )}
                {sidePanelFeature === 'chat' && (
                  <>
                    {chatTargetUrl && (
                      <p className="text-xs text-slate-500 mb-2 break-all">
                        Chatting about: <a href={chatTargetUrl} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">{chatTargetUrl}</a>
                      </p>
                    )}
                    {(chatStatus === 'loading' || chatStatus === 'analyzing') && (
                      <div className="flex items-center space-x-2 p-3">
                        <LoadingSpinner size="small" message="" />
                        <span className="text-sm text-slate-600">{chatProgressMessage}</span>
                      </div>
                    )}
                    {chatStatus === 'error' && (
                      <ErrorMessage message={chatProgressMessage || 'Chat failed to load'} />
                    )}
                    {chatStatus === 'ready' && (
                      <div className="flex flex-col h-full max-h-full">
                        {/* Chat Messages */}
                        <div ref={chatContainerRef} className="flex-1 overflow-y-auto mb-4 space-y-3 min-h-0">
                          {chatMessages.map((msg, idx) => (
                            <div key={idx} className={`p-3 rounded-lg ${
                              msg.role === 'user' 
                                ? 'bg-blue-100 ml-4 text-right' 
                                : 'bg-slate-50 mr-4'
                            }`}>
                              <p className="text-xs whitespace-pre-wrap">{msg.content}</p>
                            </div>
                          ))}
                          {/* Loading indicator for new messages */}
                          {chatMessageLoading && (
                            <div className="bg-slate-50 mr-4 p-3 rounded-lg">
                              <div className="flex items-center space-x-2">
                                <LoadingSpinner size="small" message="" />
                                <span className="text-xs text-slate-600">Thinking...</span>
                              </div>
                            </div>
                          )}
                          <div ref={messagesEndRef} />
                        </div>
                        
                        {/* Suggested Questions */}
                        {chatSuggestedQuestions.length > 0 && (
                          <div className="mb-4">
                            <h4 className="font-semibold text-slate-700 text-xs mb-2">Suggested Questions:</h4>
                            <div className="space-y-1">
                              {chatSuggestedQuestions.map((question, idx) => (
                                <button
                                  key={idx}
                                  onClick={() => handleSendChatMessage(question)}
                                  className="w-full text-left p-2 text-xs bg-white border border-slate-200 rounded hover:bg-slate-50 transition-colors"
                                >
                                  {question}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                        
                        {/* Chat Input */}
                        <div className="border-t pt-3">
                          <div className="flex space-x-2">
                            <input
                              type="text"
                              placeholder="Ask a question..."
                              className="flex-1 p-2 text-xs border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                              onKeyPress={(e) => {
                                if (e.key === 'Enter') {
                                  const input = e.target as HTMLInputElement;
                                  handleSendChatMessage(input.value);
                                  input.value = '';
                                }
                              }}
                            />
                            <button
                              onClick={(e) => {
                                const input = (e.target as HTMLButtonElement).previousElementSibling as HTMLInputElement;
                                handleSendChatMessage(input.value);
                                input.value = '';
                              }}
                              className="px-3 py-2 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 transition-colors"
                            >
                              Send
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                )}
                {sidePanelFeature === 'deepsearch' && (
                  <div className="space-y-4">
                    {deepSearchLoading && (
                      <div className="flex items-center justify-center py-8">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#000048]"></div>
                        <span className="ml-2 text-sm text-slate-600">Searching related articles...</span>
                      </div>
                    )}
                    
                    {deepSearchError && (
                      <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4" role="alert">
                        <p className="font-bold">Search Error</p>
                        <p>{deepSearchError}</p>
                      </div>
                    )}
                    
                    {!deepSearchLoading && !deepSearchError && deepSearchResults.length > 0 && (
                      <div className="space-y-3">
                        <div className="flex justify-between items-center">
                          <h3 className="font-semibold text-[#000048] text-sm">Related Articles ({deepSearchResults.length})</h3>
                          {!showAllSources && deepSearchResults.length >= 5 && (
                            <button
                              onClick={() => handleShowAllSources(currentSearchTitle)}
                              className="bg-[#000048] hover:bg-[#000066] text-white px-3 py-1 rounded text-xs"
                            >
                              Show All Sources
                            </button>
                          )}
                        </div>
                        {deepSearchResults.map((result, index) => (
                          <div key={index} className="bg-slate-50 p-3 rounded border border-[#000048] text-xs">
                            <div className="flex justify-between items-start mb-2">
                              <h4 className="font-semibold text-[#000048] text-xs leading-tight flex-1 mr-2">
                                <a href={result.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                                  {result.title}
                                </a>
                              </h4>
                              <input 
                                type="checkbox" 
                                className="w-3 h-3 text-[#000048] bg-gray-100 border-gray-300 rounded focus:ring-[#000048] focus:ring-2 flex-shrink-0"
                                title={`Select ${result.title}`}
                                checked={selectedArticles.has(index)}
                                onChange={(e) => {
                                  const newSelected = new Set(selectedArticles);
                                  if (e.target.checked) {
                                    newSelected.add(index);
                                  } else {
                                    newSelected.delete(index);
                                  }
                                  setSelectedArticles(newSelected);
                                }}
                              />
                            </div>
                            <p className="text-slate-600 text-xs mb-2 line-clamp-2">{result.snippet}</p>
                            <div className="flex justify-between items-center text-xs">
                              <span className="text-[#000048] font-medium">{result.source}</span>
                              <span className="text-slate-500">{result.date}</span>
                            </div>
                          </div>
                        ))}
                        
                        {/* Generate Expanded Context Button */}
                        {selectedArticles.size > 0 && !contextGenerating && !contextGenerated && (
                          <div className="mt-4 pt-4 border-t border-slate-200">
                            <button
                              onClick={handleGenerateExpandedContext}
                              className="w-full bg-[#000048] hover:bg-[#000066] text-white font-medium py-2 px-4 rounded text-sm"
                            >
                              Generate Expanded Context ({selectedArticles.size} articles)
                            </button>
                          </div>
                        )}
                        
                        {/* Context Generation Progress */}
                        {contextGenerating && (
                          <div className="mt-4 pt-4 border-t border-slate-200">
                            <div className="flex items-center space-x-2 mb-2">
                              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-[#000048]"></div>
                              <span className="text-sm text-slate-600">Generating expanded context...</span>
                            </div>
                            <p className="text-xs text-slate-500">{contextProgress}</p>
                          </div>
                        )}
                        
                        {/* Report Generation Progress */}
                        {reportGenerating && (
                          <div className="mt-4 pt-4 border-t border-slate-200">
                            <div className="flex items-center space-x-2 mb-2">
                              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-[#000048]"></div>
                              <span className="text-sm text-slate-600">Generating strategic report...</span>
                            </div>
                            <p className="text-xs text-slate-500">{contextProgress}</p>
                          </div>
                        )}
                        
                        {/* Prepare Report Button */}
                        {contextGenerated && expandedContext.length > 0 && !reportGenerating && (
                          <div className="mt-4 pt-4 border-t border-slate-200">
                            <div className="mb-3">
                              <h4 className="font-semibold text-[#000048] text-sm mb-2">Context Generated ({expandedContext.length} articles)</h4>
                              <div className="max-h-64 overflow-y-auto space-y-2">
                                {expandedContext.map((ctx, idx) => (
                                  <div key={idx} className="text-xs bg-slate-50 border border-[#000048] rounded">
                                    <div 
                                      className="p-2 cursor-pointer hover:bg-slate-100 transition-colors"
                                      onClick={() => {
                                        const newExpanded = new Set(expandedContextItems);
                                        if (expandedContextItems.has(idx)) {
                                          newExpanded.delete(idx);
                                        } else {
                                          newExpanded.add(idx);
                                        }
                                        setExpandedContextItems(newExpanded);
                                      }}
                                    >
                                      <div className="flex justify-between items-center">
                                        <span className="font-medium text-[#000048]">{ctx.source}</span>
                                        <span className="text-[#000048]">{expandedContextItems.has(idx) ? '▼' : '▶'}</span>
                                      </div>
                                      <p className="text-[#000048] mt-1">
                                        {expandedContextItems.has(idx) ? ctx.title : `${ctx.title.substring(0, 60)}...`}
                                      </p>
                                    </div>
                                    {expandedContextItems.has(idx) && (
                                      <div className="p-3 border-t border-[#000048] bg-white">
                                        <div className="mb-3">
                                          <h5 className="font-semibold text-[#000048] text-xs mb-1">Summary:</h5>
                                          <p className="text-slate-700 text-xs whitespace-pre-wrap">{ctx.summary}</p>
                                        </div>
                                        <div className="mb-3">
                                          <h5 className="font-semibold text-[#000048] text-xs mb-1">Top Insights:</h5>
                                          <p className="text-slate-700 text-xs whitespace-pre-wrap">{ctx.insights}</p>
                                        </div>
                                        <div className="text-xs text-slate-500">
                                          <p><strong>URL:</strong> <a href={ctx.url} target="_blank" rel="noopener noreferrer" className="text-[#000048] hover:underline">{ctx.url}</a></p>
                                          <p><strong>Date:</strong> {ctx.date}</p>
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                            <button
                              onClick={handlePrepareReport}
                              className="w-full bg-[#000048] hover:bg-[#000066] text-white font-medium py-2 px-4 rounded text-sm"
                            >
                              Prepare Report
                            </button>
                          </div>
                        )}
                        
                        {/* Generated Report Display */}
                        {reportGenerated && reportContent && (
                          <div className="mt-4 pt-4 border-t border-slate-200">
                            <div className="mb-3">
                              <h4 className="font-semibold text-[#000048] text-sm mb-2">Strategic Analysis Report</h4>
                              <div className="bg-white border border-[#000048] rounded p-3 max-h-96 overflow-y-auto">
                                <pre className="text-xs whitespace-pre-wrap font-sans">{reportContent}</pre>
                              </div>
                            </div>
                            <div className="grid grid-cols-3 gap-2">
                              <button
                                onClick={() => handleDownloadPDF()}
                                className="bg-[#000048] hover:bg-[#000066] text-white font-medium py-2 px-4 rounded text-sm"
                              >
                                Download PDF
                              </button>
                              <button
                                onClick={() => {
                                  const blob = new Blob([reportContent], { type: 'text/plain' });
                                  const url = URL.createObjectURL(blob);
                                  const a = document.createElement('a');
                                  a.href = url;
                                  a.download = `Amgen_Strategic_Report_${new Date().toISOString().split('T')[0]}.txt`;
                                  document.body.appendChild(a);
                                  a.click();
                                  document.body.removeChild(a);
                                  URL.revokeObjectURL(url);
                                }}
                                className="bg-[#000048] hover:bg-[#000066] text-white font-medium py-2 px-4 rounded text-sm"
                              >
                                Download Text
                              </button>
                              <button
                                onClick={() => handleChatWithReport()}
                                className="bg-[#000048] hover:bg-[#000066] text-white font-medium py-2 px-4 rounded text-sm"
                              >
                                Chat
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    
                    {!deepSearchLoading && !deepSearchError && deepSearchResults.length === 0 && (
                      <div className="text-center py-8 text-slate-500">
                        <p>No related articles found from credible sources.</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      
      <footer className="w-full text-center text-slate-500 py-0 px-2 text-xs border-t border-slate-300 bg-white">
        <div className="flex flex-col sm:flex-row sm:justify-center sm:items-center sm:space-x-2">
          <p>&copy;2025 Cognizant All rights reserved.</p>
          <span className="hidden sm:inline">|</span>
          <a href="#" className="hover:underline mt-1 sm:mt-0">Terms of Use</a>
          <span className="hidden sm:inline">|</span>
          <span className="mt-1 sm:mt-0">This application uses Gen AI. Please validate the responses.</span>
        </div>
      </footer>




    </div>
  );
};

export default App;
