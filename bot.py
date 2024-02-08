from flask import Flask, request, session
from twilio.twiml.messaging_response import MessagingResponse
from flask_session import Session  # Import Flask-Session
import requests
import random
from newspaper import Article
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lex_rank import LexRankSummarizer
import nltk
nltk.download('punkt')
import secrets
from nltk.tokenize import sent_tokenize
import re


app = Flask(__name__)

app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SESSION_TYPE'] = 'filesystem'  # Use filesystem-based session storage
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
Session(app)

NEWS_API_KEY = 'e545f0a9cc294a1389e04d423cad4c5c'
NEWS_API_URL = 'https://newsapi.org/v2/top-headlines'
NEWS_API_EVERYTHING_URL = 'https://newsapi.org/v2/everything'


BOT_NAME = 'NewsBot'

RESPONSES_GREETING = [
    f'👋 Hi there! I am {BOT_NAME}. How can I assist you today? Type "help" to see available commands.',
    f'Hello! {BOT_NAME} here. Ready to bring you the latest headlines. Just type "help" to view commands.',
    f'Hey, I\'m {BOT_NAME}! Let\'s explore the news. Type "help" to see what I can do.'
]

RESPONSES_GIBBERISH = [
    f'I\'m sorry, I couldn\'t understand that. Please type "help" to see available commands.',
    f' Hmmm, I didn\'t quite catch that. For assistance, simply type "help".'
]

HELP_COMMANDS = [
    'Here are the available commands:',
    '"in" - Retrieve news headlines for India',
    '"us" - Retrieve news headlines for the United States',
    '"summarize" - Receive a summary of the news',
    '"end" or "stop" - Terminate the conversation',
    'Alternatively, you can input a specific news topic for searching.'
]

searchnews = False

def get_country_headlines(country_code):
    params = {
        'country': country_code,
        'apiKey': NEWS_API_KEY
    }
    response = requests.get(NEWS_API_URL, params=params)
    data = response.json()
    articles = []

    if data['status'] == 'ok':
        articles_data = data['articles']
        for article in articles_data:
            title = article.get('title', 'N/A')
            description = article.get('description', 'No description available.')
            url = article.get('url', '')
            articles.append({
                'title': title,
                'url': url
            })

    return articles
    
def get_news_by_input(input_text):
    params = {
        'q': input_text,
        'language': 'en',
        'apiKey': NEWS_API_KEY
    }
    response = requests.get(NEWS_API_EVERYTHING_URL, params=params)
    data = response.json()
    articles = []

    if data['status'] == 'ok':
        articles_data = data['articles']
        for article in articles_data:
            title = article.get('title', 'N/A')
            url = article.get('url', '')
            articles.append({
                'title': title,
                'url': url
            })

    return articles


def extract_text_content(url):
    article = Article(url)
    article.download()
    article.parse()
    return article.text

def preprocess_text(text):
    # Split the text into sentences using NLTK's sentence tokenizer
    sentences = sent_tokenize(text)
    
    # Remove noisy or irrelevant content (you can customize this)
    cleaned_sentences = [sentence for sentence in sentences if len(sentence.split()) > 3]
    
    # Clean up the text by removing special characters and extra spaces
    cleaned_text = ' '.join(cleaned_sentences)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    
    return cleaned_text

def summarize_text(text):
    num_sentences = 4
    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = LexRankSummarizer()
    summary = summarizer(parser.document, num_sentences)
    result = ' '.join([str(sentence) for sentence in summary])
    return result

@app.route('/webhook', methods=['POST'])
def bot():
    global searchnews
    incoming_msg = request.values.get('Body', '').lower()
    resp = MessagingResponse()
    msg = resp.message()


    if any(greeting in incoming_msg for greeting in ['hi', 'hey', 'hello', 'hola']):
        session.clear()  # Reset session data
        msg.body(random.choice(RESPONSES_GREETING))
        searchnews = False
    elif 'help' in incoming_msg:
        msg.body('\n'.join(HELP_COMMANDS))
        searchnews = True
    elif incoming_msg in ['us', 'in']:
        session.clear()  # Reset session data
        country_code = incoming_msg
        headlines = get_country_headlines(country_code)
        if headlines:
            session['headlines'] = headlines
            session['current_index'] = 0
            msg.body(
                f"Latest headlines in {country_code.upper()}:\n\n{headlines[0]['title']}\n{headlines[0]['url']}\n\nType 'more' for the next news article, 'summarize' to get a summary, or 'end' to exit.")
            searchnews = False
        else:
            msg.body(f'No headlines available for {country_code.upper()} at the moment.')
    elif 'more' in incoming_msg:
        if session.get('summarize_mode'):
            current_index = session.get('current_index', 0)
            search_results = session.get('search_results', [])
            if current_index < len(search_results) - 1:
                next_index = current_index + 1
                session['current_index'] = next_index
                msg.body(f"Title: {search_results[next_index]['title']} \nURL: {search_results[next_index]['url']}")
                msg.body("*Type 'summarize' for a summary, 'more' for the next article, or 'end' to exit.*")
            else:
                msg.body("No more search results available. That's all for now.")
                session['summarize_mode'] = False  # Deactivate summarize mode after displaying all search results
        elif session.get('search_mode'):
            try:
                search_results = session.get('search_results', [])
                current_index = session.get('current_index', 0)
                if current_index < len(search_results) - 1:
                    next_index = current_index + 1
                    session['current_index'] = next_index
                    msg.body(f'Search results for "{session["search_query"]}":\n\n')
                    msg.body(f"Title: {search_results[next_index]['title']} \nURL: {search_results[next_index]['url']}")
                    msg.body("*Type 'summarize' for a summary, 'more' for the next article, or 'end' to exit.*")
                else:
                    msg.body("No more search results available. That's all for now.")
            except Exception as e:
                error_message = f"An error occurred: {str(e)}"
                msg.body(error_message)
        else:
            headlines = session.get('headlines', [])
            current_index = session.get('current_index', 0)
            if current_index < len(headlines) - 1:
                next_index = current_index + 1
                session['current_index'] = next_index
                msg.body(
                    f"{headlines[next_index]['title']} \n{headlines[next_index]['url']}\n\nType 'more' for the next news article, 'summarize' to get a summary, or 'end' to exit.")
            else:
                msg.body('No more headlines available. That\'s all for now.')
    elif 'summarize' in incoming_msg:
        if session.get('summarize_mode'):
            current_index = session.get('current_index', 0)
            search_results = session.get('search_results', [])
            if current_index < len(search_results):
                url = search_results[current_index]['url']
                text_content = extract_text_content(url)
                cleaned_text = preprocess_text(text_content)
                summarized_text = summarize_text(cleaned_text)
                msg.body(f"Summary:\n{summarized_text}")
                msg.body("*Type 'summarize' for another summary, 'more' for the next article, or 'end' to exit.*")
            else:
                msg.body("No more search results available. That's all for now.")
                session['summarize_mode'] = False  # Deactivate summarize mode after displaying all search results
        elif session.get('search_mode'):
            current_index = session.get('current_index', 0)
            search_results = session.get('search_results', [])
            if current_index < len(search_results):
                url = search_results[current_index]['url']
                text_content = extract_text_content(url)
                cleaned_text = preprocess_text(text_content)
                summarized_text = summarize_text(cleaned_text)
                msg.body(f"Summary:\n{summarized_text}")
                msg.body(
                    "*Type 'summarize' for a summary, 'more' for the next article, or 'end' to exit.*")
            else:
                msg.body("No more search results available. That's all for now.")
                session['summarize_mode'] = False  # Deactivate summarize mode after displaying all search results
        else:
            current_index = session.get('current_index', 0)
            headlines = session.get('headlines', [])
            if current_index < len(headlines):
                url = headlines[current_index]['url']
                text_content = extract_text_content(url)
                cleaned_text = preprocess_text(text_content)
                summarized_text = summarize_text(cleaned_text)
                msg.body(f"Summary:\n{summarized_text}")
                msg.body("*Type 'more' for the next article or 'end' to exit.*")
            else:
                msg.body("No more headlines available. That's all for now.")
    else:
        try:
            if searchnews:  # Check if news search is enabled
                search_results = get_news_by_input(incoming_msg)
                if search_results:
                    session['search_mode'] = True
                    session['summarize_mode'] = True  # Enable summarize mode for search results
                    session['search_results'] = search_results
                    session['current_index'] = 0
                    session['search_query'] = incoming_msg
                    msg.body(f'Search results for "{incoming_msg}":\n\n')
                    msg.body(f"Title: {search_results[0]['title']} \nURL: {search_results[0]['url']}")
                    msg.body(
                        "*Type 'summarize' for a summary, 'more' for the next article, or 'end' to exit.*")
                else:
                    msg.body(f'No news articles found for "{incoming_msg}".')
            else:
                msg.body("To search for news, type 'search'. For other commands, type 'help'.")
        except Exception as e:
            error_message = f"An error occurred while searching: {str(e)}"
            msg.body(error_message)
    
    

    return str(resp)

if __name__ == '__main__':
    app.run(debug=True)

