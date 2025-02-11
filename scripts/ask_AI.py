import boto3
import json
import os
import time
import random
import requests
import base64
from groq import Groq
from openai import AzureOpenAI, OpenAI, AsyncAzureOpenAI, AsyncOpenAI
from dotenv import load_dotenv
import google.generativeai as genai
import anthropic
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

session = boto3.Session(profile_name='bedrockprofile')
brt = boto3.client(service_name='bedrock-runtime',region_name="us-east-1")

def is_retryable_error(e):
    """Determine if an error should trigger a retry"""
    error_str = str(e).lower()
    
    # Check for common error indicators
    if any(indicator in error_str for indicator in [
        'rate limit',
        'timeout',
        'internal server',
        'server error',
        'too many requests',
        '429',
        '500',
        '502',
        '503',
        '504',
        'connection',
        'network',
        'unavailable',
        'capacity',
        'overloaded',
        'throttle',
        'exhausted',
        'quota',
        'api error',
        'service unavailable'
    ]):
        return True
        
    # Check for specific error types
    if isinstance(e, (
        requests.exceptions.RequestException,
        anthropic.APIError,
        anthropic.APIConnectionError,
        anthropic.InternalServerError,
        anthropic.RateLimitError,
        genai.types.BlockedPromptException,
        ConnectionError,
        TimeoutError
    )):
        return True
        
    return False

def exponential_backoff(func, max_retries=10, initial_delay=1, factor=2, jitter=0.1, max_delay=300):
    """
    Decorator that implements exponential backoff for retrying functions.
    - max_retries: Maximum number of retry attempts
    - initial_delay: Initial delay between retries in seconds
    - factor: Multiplicative factor for delay after each retry
    - jitter: Random jitter factor to add to delay
    - max_delay: Maximum delay between retries in seconds
    """
    def wrapper(*args, **kwargs):
        retries = 0
        delay = initial_delay
        
        while True:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                retries += 1
                if not is_retryable_error(e) or retries >= max_retries:
                    logging.error(f"Error in {func.__name__} after {retries} retries: {str(e)}")
                    raise e
                
                # Calculate delay with jitter, capped at max_delay
                jitter_amount = random.uniform(-jitter * delay, jitter * delay)
                sleep_time = min(delay + jitter_amount, max_delay)
                
                logging.warning(f"API error in {func.__name__}: {str(e)}. Retry {retries}/{max_retries} in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                
                # Increase delay for next retry
                delay = min(delay * factor, max_delay)
    
    return wrapper

@exponential_backoff
def ask_aws_claude(prompt, max_tokens=200000):
    load_dotenv()
    newline = "\n\n"
    body = json.dumps({
        "max_tokens": int(max_tokens) if max_tokens is not None else 200000,
        "temperature": 0,
        "messages": [{"role": "user",
                    "content": f"{newline}Human: {prompt}{newline}Assistant:"}],
        "anthropic_version": "bedrock-2023-05-31"
    })
 
    modelId = 'anthropic.claude-3-5-sonnet-20240620-v1:0'
    accept = 'application/json'
    contentType = 'application/json'
    
    try:
        response = brt.invoke_model(body=body, modelId=modelId, accept=accept, contentType=contentType)
        response_body = json.loads(response.get("body").read())
        out = response_body.get("content")[0]["text"]
        logging.info(f"AWS Claude response: {out}")
        return out
    except Exception as e:
        logging.error(f"Error in AWS Claude API call: {str(e)}")
        raise

@exponential_backoff
def ask_claude(prompt, max_tokens=10000):
    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY")
    )

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=int(max_tokens) if max_tokens is not None else 1000,
            temperature=0,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        out = message.content[0].text
        logging.info(f"Claude response: {out}")
        return out
    except Exception as e:
        logging.error(f"Error in Claude API call: {str(e)}")
        raise

@exponential_backoff
def ask_gemini(prompt, max_tokens=None):
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash",
                                generation_config=genai.types.GenerationConfig(
                                    temperature=0
                                ))
    
    try:
        response = model.generate_content(prompt)
        logging.info(f"Gemini response: {response.text}")
        return response.text
    except Exception as e:
        logging.error(f"Error in Gemini API call: {str(e)}")
        raise

@exponential_backoff
def ask_gemma2(prompt, max_tokens=8192):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    model = 'gemma2-9b-it'
    
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=min(int(max_tokens) if max_tokens is not None else 8192, 8192),
            temperature=0
        )
        output = completion.choices[0].message.content
        logging.info(f"Gemma2 response: {output}")
        return output
    except Exception as e:
        logging.error(f"Error in Gemma2 API call: {str(e)}")
        raise

@exponential_backoff
def ask_llama3(prompt, max_tokens=32768):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    model = 'llama-3.3-70b-versatile'
    
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=min(int(max_tokens) if max_tokens is not None else 32768, 32768),
            temperature=0
        )
        output = completion.choices[0].message.content
        logging.info(f"Llama3 response: {output}")
        return output
    except Exception as e:
        logging.error(f"Error in Llama3 API call: {str(e)}")
        raise

@exponential_backoff
def ask_mixtral(prompt, max_tokens=32768):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    model = "mixtral-8x7b-32768"
    
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=min(int(max_tokens) if max_tokens is not None else 32768, 32768),
            temperature=0
        )
        output = completion.choices[0].message.content
        logging.info(f"Mixtral response: {output}")
        return output
    except Exception as e:
        logging.error(f"Error in Mixtral API call: {str(e)}")
        raise

def ask_ai(prompt, ai_model='claude', max_tokens=None):
    """
    Main function to route requests to specific AI models with error handling
    """
    logging.info(f"Asking {ai_model}")
    
    try:
        if ai_model == "claude":
            return ask_claude(prompt, max_tokens)
        elif ai_model == "aws_claude":
            return ask_aws_claude(prompt, max_tokens)
        elif ai_model == "gemini":
            return ask_gemini(prompt, max_tokens)
        elif ai_model == "gemma2":
            return ask_gemma2(prompt, max_tokens)
        elif ai_model == "llama3":
            return ask_llama3(prompt, max_tokens)
        elif ai_model == "mixtral":
            return ask_mixtral(prompt, max_tokens)
        else:
            raise ValueError(f"Unknown AI model: {ai_model}")
    except Exception as e:
        logging.error(f"Error in ask_ai with model {ai_model}: {str(e)}")
        raise

# Simple test
if __name__ == "__main__":
    ask_ai('why is sky blue?','claude')
    def test_is_retryable_error():
        test_cases = [
            (requests.exceptions.ConnectionError(), True),
            (TimeoutError(), True),
            (ValueError("Invalid input"), False),
            (Exception("Rate limit exceeded"), True),
            (Exception("Invalid request"), False)
        ]
        
        for error, expected in test_cases:
            result = is_retryable_error(error)
            print(f"Testing {error.__class__.__name__}: Expected {expected}, Got {result}")
            assert result == expected, f"Test failed for {error}"
    
    print("Running tests...")
    try:
        test_is_retryable_error()
        print("All tests passed!")
    except AssertionError as e:
        print(f"Test failed: {e}")
