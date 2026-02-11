#!/usr/bin/env python3
"""
Test script to compare DeepSeek model performance via OpenRouter.

Tests different DeepSeek models to determine which is fastest and most reliable.
"""
import os
import time
import logging
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load API key from environment
api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    logger.error("OPENROUTER_API_KEY not found in environment")
    exit(1)

# Initialize OpenRouter client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key
)

# Test prompt (simple JSON extraction task)
test_prompt = """Extract the team name and narrative type from this news:

TITLE: Manchester United manager confirms squad rotation for upcoming match
SNIPPET: The manager has indicated that several key players will be rested for the upcoming fixture, with youth players expected to get significant playing time.

OUTPUT (strict JSON only):
{
  "team": "Full Team Name",
  "type": "B_TEAM" or "CRISIS" or "KEY_RETURN" or "NONE",
  "confidence": 0-10
}"""

# Models to test
models_to_test = [
    "deepseek/deepseek-r1-0528:free",  # Current model (free tier)
    "deepseek/deepseek-r1-0528",         # Paid version (no :free suffix)
    "deepseek/deepseek-chat",              # Standard V3 model
]

results = []

for model_id in models_to_test:
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing model: {model_id}")
    logger.info(f"{'='*60}")
    
    try:
        start_time = time.time()
        
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "You extract football team names and narrative types from news. Output only JSON."},
                {"role": "user", "content": test_prompt}
            ],
            temperature=0.3,
            max_tokens=1000,
            timeout=60  # 60 second timeout
        )
        
        latency = time.time() - start_time
        content = response.choices[0].message.content
        
        # Log results
        logger.info(f"✅ Response received successfully")
        logger.info(f"⏱️ Latency: {latency:.2f}s")
        logger.info(f"📝 Response length: {len(content)} characters")
        logger.info(f"📄 Response preview: {content[:200]}...")
        
        # Store results
        results.append({
            'model': model_id,
            'latency': latency,
            'response_length': len(content),
            'success': True,
            'content': content
        })
        
    except Exception as e:
        latency = time.time() - start_time
        logger.error(f"❌ Error: {e}")
        logger.info(f"⏱️ Time to error: {latency:.2f}s")
        
        results.append({
            'model': model_id,
            'latency': latency,
            'response_length': 0,
            'success': False,
            'error': str(e)
        })
    
    # Wait a bit between tests to avoid rate limiting
    time.sleep(2)

# Print summary
logger.info(f"\n{'='*60}")
logger.info("📊 PERFORMANCE SUMMARY")
logger.info(f"{'='*60}\n")

# Sort by latency
results_sorted = sorted(results, key=lambda x: x['latency'])

for i, result in enumerate(results_sorted, 1):
    status = "✅ SUCCESS" if result['success'] else "❌ FAILED"
    logger.info(f"{i}. {result['model']}")
    logger.info(f"   Status: {status}")
    logger.info(f"   Latency: {result['latency']:.2f}s")
    if result['success']:
        logger.info(f"   Response length: {result['response_length']} chars")
    else:
        logger.info(f"   Error: {result['error']}")
    logger.info("")

# Recommendation
if results_sorted:
    fastest = results_sorted[0]
    if fastest['success']:
        logger.info(f"🏆 RECOMMENDATION: Use '{fastest['model']}' for best performance")
        logger.info(f"   Average latency: {fastest['latency']:.2f}s")
    else:
        logger.warning("⚠️ All models failed. Check API key and network connection.")
