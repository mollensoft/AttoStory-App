import os
import requests
import openai
from flask import Flask, render_template, request, jsonify
from io import BytesIO
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import abort 

load_dotenv()  # Load environment variables from .env file

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["15 per minute", "250 per day"]  
)

CATEGORIES = ["Cybersecurity", "Technology"]
NEWS_API_URL = "https://newsapi.org/v2/everything"

os.makedirs('static', exist_ok=True)

def fetch_news(category):
    """Fetch latest news articles for a given category."""
    params = {
        "q": category,
        "sortBy": "publishedAt",
        "language": "en",
        "apiKey": NEWS_API_KEY,
        "pageSize": 2
    }
    response = requests.get(NEWS_API_URL, params=params)

    if response.status_code != 200:
        print(f"Error fetching news for {category}: {response.json()}")
        return []

    return response.json().get("articles", [])

def analyze_news(article):
    """Use OpenAI to analyze the news article."""
    if not article or "title" not in article or "description" not in article:
        return {
            'title': 'Error',
            'source': 'Unknown',
            'url': '#', 
            'analysis': "No valid article data available."
        }

    
    article_text = f"""
    Title: {article.get('title', '')}
    
    Description: {article.get('description', '')}
    
    Content: {article.get('content', '')}
    """

    prompt = f"""
    Article to analyze:
    {article_text}

    Please provide a structured analysis with the following sections:

    Summary:
    Provide a clear, concise summary of the main points.

    Credibility:
    Assess the credibility by examining:
    - Source reputation ({article.get('source', {}).get('name', 'Unknown')})
    - Supporting evidence
    - Potential biases

    Sentiment:
    Determine whether the overall tone is positive, negative, or neutral, with a brief explanation.

    Please maintain these exact section headers in your response.
    """

    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a professional news analyst."},
                {"role": "user", "content": prompt}
            ]
        )
        return {
            'title': article.get('title', 'Untitled'),
            'source': article.get('source', {}).get('name', 'Unknown Source'),
            'url': article.get('url', '#'),
            'analysis': response.choices[0].message.content
        }
    except Exception as e:
        print(f"OpenAI API Error: {e}")
        return {
            'title': article.get('title', 'Untitled'),
            'source': article.get('source', {}).get('name', 'Unknown Source'),
            'url': article.get('url', '#'),
            'analysis': "Error processing article."
        }

@app.route("/")
def index():
    return render_template("index.html")


ALLOWED_CATEGORIES = {
    "technology": "Technology",
    "cybersecurity": "Cybersecurity",
    "ai": "AI & ML",
    "business": "Business"
}

@app.route("/generate", methods=["POST"])
@limiter.limit("5 per minute")  
def generate():
    try:
        data = request.get_json()

        # Validate data type
        if not isinstance(data, dict):
            abort(400, "Invalid request format")

        output_type = data.get("output_type")
        if output_type not in ["text", "audio"]:
            abort(400, "Invalid output type")

        received_categories = data.get("categories", [])
        if not isinstance(received_categories, list):
            abort(400, "Invalid category format")

        # Validate category input
        selected_category = None
        for category in received_categories:
            if isinstance(category, str) and category.lower() in ALLOWED_CATEGORIES:
                selected_category = category.lower()
                break

        if not selected_category:
            abort(400, "No valid category selected")

        # Process the single validated category
        results = []
        articles = fetch_news(ALLOWED_CATEGORIES[selected_category])
        
        if articles:
            for article in articles[:2]:  # Still limit to 2 articles
                analysis_result = analyze_news(article)
                results.append({
                    'category': ALLOWED_CATEGORIES[selected_category],
                    'title': analysis_result['title'],
                    'source': analysis_result['source'],
                    'url': analysis_result['url'],  # Add URL to results
                    'summary': analysis_result['analysis']
                })

        if output_type == "audio":
            full_text = "\n\n".join([
                f"{r['category']}: {r['title']} from {r['source']}\n{r['summary']}" 
                for r in results
            ])
            
            audio_data = generate_tts(full_text)
            if audio_data is None:
                return jsonify({"status": "error", "message": "Failed to generate audio"}), 500
                
            audio_path = os.path.join('static', 'news_summary.mp3')
            with open(audio_path, 'wb') as f:
                f.write(audio_data)
                
            return jsonify({
                "status": "success", 
                "audio_url": "/static/news_summary.mp3"
            })

        return jsonify({"status": "success", "summaries": results})

    except Exception as e:
        print(f"Error processing request: {str(e)}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500
    
def generate_tts(text):
    """
    Generate high-quality TTS using OpenAI's API.
    Returns the audio data as bytes.
    """
    try:
        response = openai.audio.speech.create(
            model="tts-1",  # Use "tts-1-hd" for even higher quality (costs the same)
            voice="alloy",  # Other options: "nova", "echo", "fable", "onyx", "shimmer"
            input=text
        )

        audio_data = response.content  # Get the audio bytes

        audio_path = "static/news_summary.mp3"
        with open(audio_path, "wb") as f:
            f.write(audio_data)

        return audio_data

    except Exception as e:
        print(f"Error generating TTS: {e}")
        return None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

