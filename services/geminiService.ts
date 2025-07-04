
import { GoogleGenAI, GenerateContentResponse } from "@google/genai";
import { Article, GroundingChunk, Sentiment } from '../types'; // Article, GroundingChunk, Sentiment might be unused if types.ts is simplified heavily

const API_KEY = process.env.API_KEY;

export interface FetchArticlesResult {
  articles: Article[];
  groundingSources: GroundingChunk[];
}

export const fetchArticlesFromGemini = async (targetUrl: string): Promise<FetchArticlesResult> => {
  if (!API_KEY) {
    console.error("API_KEY is not set in environment variables.");
    throw new Error("API_KEY for Gemini is missing. Please ensure it is configured.");
  }
  if (!targetUrl.trim()) {
    throw new Error("Target URL cannot be empty.");
  }

  const ai = new GoogleGenAI({ apiKey: API_KEY });

  const prompt = `
    You are an assistant for Amgen, a major life sciences company. Your task is to analyze news articles from the website: ${targetUrl}.
    Use Google Search to find news articles, press releases, blog posts, and fact sheets on this website.

    For each distinct article found, extract the following information:
    1.  'title': The full title of the article.
    2.  'link': The direct, absolute URL to the article.
    3.  'date': The publication date, if available (try to format as YYYY-MM-DD, otherwise return an empty string or null).
    4.  'summary': A brief one or two-sentence summary, if readily available (otherwise return an empty string or null).
    5.  'aiSuggestedSentiment': Classify the article's potential impact on Amgen as 'positive', 'negative', or 'neutral'. Prioritize identifying 'negative' impacts accurately. If unsure, classify as 'neutral'.

    Hint for extracting titles and links from the source HTML of sites like cms.gov:
    Article links are often structured as an '<a>' tag. The 'href' attribute of this '<a>' tag is the article link.
    The full article title is frequently found within a '<span>' tag that has the class 'ds-u-visibility--screen-reader' (or similar screen-reader-only spans), and this span is often a child of the aforementioned '<a>' tag. The text content of this span (sometimes after a prefix like "about ") is the title.
    Example HTML structure hinting at this: <a href="[link_url]" class="ds-c-button newsroom-main-view-link"><span class="ds-u-visibility--screen-reader">about [article_title]</span></a>

    Return the extracted information as a JSON array of objects. Each object should have 'title', 'link', 'date', 'summary', and 'aiSuggestedSentiment' properties.
    The title and link are mandatory. If a date, summary, or sentiment cannot be reliably determined, use empty strings or null for date/summary, and 'neutral' for aiSuggestedSentiment if truly ambiguous.

    Example JSON output:
    [
      {
        "title": "CMS Rolls Out Aggressive Strategy to Enhance Medicare Advantage Audits",
        "link": "https://www.cms.gov/newsroom/press-releases/cms-rolls-out-aggressive-strategy-enhance-and-accelerate-medicare-advantage-audits",
        "date": "2023-01-30",
        "summary": "Today, CMS announced new efforts to strengthen oversight of Medicare Advantage plans.",
        "aiSuggestedSentiment": "negative" 
      },
      {
        "title": "Amgen Announces Positive Phase 3 Trial Results for New Drug",
        "link": "https://www.example-pharma-news.com/amgen-positive-trial",
        "date": "2023-02-15",
        "summary": "Amgen reported successful outcomes from its late-stage clinical trial for drug X.",
        "aiSuggestedSentiment": "positive"
      }
    ]

    Ensure the output is ONLY a valid JSON array of these article objects.
    Do not include any other text, explanations, or markdown formatting like \`\`\`json or \`\`\` around the JSON array.
    If no relevant articles are found, return an empty JSON array: [].
  `;

  try {
    const response: GenerateContentResponse = await ai.models.generateContent({
      model: "gemini-2.5-flash-preview-04-17",
      contents: prompt,
      config: {
        tools: [{googleSearch: {}}],
      },
    });

    if (typeof response.text !== 'string') {
      const firstCandidate = response.candidates?.[0];
      const promptFeedback = response.promptFeedback;
      let specificDetail = "The model's response did not contain a readable text field.";

      if (firstCandidate?.finishReason && firstCandidate.finishReason !== "STOP" && firstCandidate.finishReason !== "MAX_TOKENS") {
        specificDetail = `Model generation stopped prematurely. Finish reason: ${firstCandidate.finishReason}${firstCandidate.finishMessage ? ` (${firstCandidate.finishMessage})` : ''}.`;
      } else if (promptFeedback?.blockReason) {
        specificDetail = `Request was blocked. Reason: ${promptFeedback.blockReason}${promptFeedback.blockReasonMessage ? ` (${promptFeedback.blockReasonMessage})` : ''}.`;
      } else if (!firstCandidate?.content?.parts || firstCandidate.content.parts.length === 0) {
        specificDetail = "Model returned no content parts, so no text could be extracted.";
         if (firstCandidate?.finishReason) {
            specificDetail += ` (Finish Reason: ${firstCandidate.finishReason})`;
        }
      }
      
      console.error(`Gemini Error Detail: ${specificDetail}. Full response for context:`, JSON.stringify(response, null, 2));
      throw new Error(`Failed to get a valid response from Gemini: ${specificDetail}`);
    }

    let jsonStr = response.text.trim();
    
    if (jsonStr === '') {
      console.warn("Gemini API response text field was empty after trimming. Assuming no articles found. Response:", JSON.stringify(response, null, 2));
      jsonStr = "[]"; 
    }
    
    const fenceRegex = /^```(\w*)?\s*\n?(.*?)\n?\s*```$/s;
    const match = jsonStr.match(fenceRegex);
    if (match && match[2]) {
      jsonStr = match[2].trim();
    }

    let parsedArticles: Article[] = [];
    try {
      const parsedData = JSON.parse(jsonStr);
      if (Array.isArray(parsedData) && parsedData.every(item => 
          typeof item === 'object' && item !== null &&
          typeof item.title === 'string' &&
          typeof item.link === 'string' &&
          (typeof item.date === 'string' || item.date === null) &&
          (typeof item.summary === 'string' || item.summary === null) &&
          (item.aiSuggestedSentiment === undefined || ['positive', 'negative', 'neutral'].includes(item.aiSuggestedSentiment))
      )) {
        parsedArticles = parsedData.map(item => {
          let initialSentiment: Sentiment = 'unclassified';
          if (item.aiSuggestedSentiment && ['positive', 'negative', 'neutral'].includes(item.aiSuggestedSentiment)) {
            initialSentiment = item.aiSuggestedSentiment as Sentiment;
          }
          return {
            title: item.title,
            link: item.link,
            date: item.date || '',
            summary: item.summary || '',
            aiSuggestedSentiment: item.aiSuggestedSentiment,
            sentiment: initialSentiment 
          };
        });
      } else if (jsonStr === "[]") { 
         parsedArticles = [];
      } else {
        console.error("Gemini response is not in the expected Article[] format after parsing JSON:", parsedData, "Original JSON string:", jsonStr);
        throw new Error("Received malformed article data from the AI; expected a JSON array of Article objects with sentiment.");
      }
    } catch(e) {
      console.error("Failed to parse JSON response from Gemini for articles. String was:", jsonStr, "Error:", e);
      if (jsonStr !== "[]") {
         throw new Error(`Failed to parse article data from the AI. Expected a JSON array of Article objects. Raw response snippet: ${jsonStr.substring(0,500)}`);
      }
      parsedArticles = [];
    }
    
    const groundingSources = response.candidates?.[0]?.groundingMetadata?.groundingChunks || [];

    return { articles: parsedArticles, groundingSources };

  } catch (error) {
    console.error("Error fetching articles from Gemini:", error);
    if (error instanceof Error) {
      if (error.message.startsWith("Failed to get a valid response from Gemini:") || 
          error.message.startsWith("Failed to parse article data from the AI") ||
          error.message.startsWith("API_KEY for Gemini is missing") ||
          error.message.startsWith("Target URL cannot be empty") ||
          error.message.startsWith("Received malformed article data")) {
        throw error;
      }
      if (error.message.includes("400 Bad Request") && error.message.includes("tool")) {
        throw new Error(`Failed to fetch articles using Google Search: The model may have had an issue with the tool configuration or request. Original error: ${error.message}`);
      }
      throw new Error(`An error occurred while processing articles with Gemini: ${error.message}`);
    }
    throw new Error("An unknown error occurred while fetching and processing articles from Gemini.");
  }
};
