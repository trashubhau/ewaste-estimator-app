# backend/app.py
import os
import io
import json
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS # For allowing frontend to talk to backend
from PIL import Image

# --- Copy your price structure here ---
PRICE_STRUCTURE = {
    "smartphone": {"fair": [10, 50], "good": [51, 150], "great": [151, 400]},
    "laptop": {"fair": [30, 100], "good": [101, 350], "great": [351, 800]},
    "tablet": {"fair": [20, 70], "good": [71, 200], "great": [201, 500]},
    "monitor": {"fair": [5, 25], "good": [26, 75], "great": [76, 150]},
    "keyboard": {"fair": [1, 5], "good": [6, 15], "great": [16, 40]},
    "mouse": {"fair": [1, 5], "good": [6, 15], "great": [16, 35]},
    "unknown": {"fair": [1, 10], "good": [1, 10], "great": [1, 10]} # Fallback
}

# --- Copy your helper functions here (or keep them as defined below) ---
def analyze_image_with_gemini(image_data):
    # Get API Key safely from Render's secret environment variables
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("FATAL ERROR: GEMINI_API_KEY environment variable not set on the server.")
        return {"error": "Server configuration error: API key missing."}
    try:
        genai.configure(api_key=api_key)
        # Use a model that supports vision, like gemini-1.5-flash
        model = genai.GenerativeModel('gemini-1.5-flash')
        img_pil = Image.open(io.BytesIO(image_data))

        # The specific instructions for Gemini
        prompt = """
        Analyze the image of an electronic waste item. Respond ONLY with a valid JSON object containing these keys:
        - "device_type": string (e.g., "smartphone", "laptop", "tablet", "monitor", "keyboard", "mouse", "other", "unknown"). Use lowercase.
        - "condition_description": string (brief description of visible physical condition: scratches, cracks, dents, wear, cleanliness).
        - "extracted_text": string (any clearly visible brand or model text, otherwise empty string "").

        Example:
        {
          "device_type": "laptop",
          "condition_description": "Minor scratches on lid, screen looks intact.",
          "extracted_text": "Dell"
        }
        """
        response = model.generate_content([prompt, img_pil], stream=False)
        response.resolve() # Ensure response is complete

        # Clean potential markdown backticks and parse JSON robustly
        cleaned_text = response.text.strip().lstrip('```json').rstrip('```').strip()
        if not cleaned_text:
            print("Warning: Gemini returned empty response text.")
            return {"error": "Analysis returned no content."}
        
        return json.loads(cleaned_text)

    except json.JSONDecodeError as json_err:
        print(f"Error decoding Gemini JSON response: {json_err}")
        print(f"Raw response text: {response.text if 'response' in locals() else 'N/A'}")
        return {"error": "Failed to parse analysis result.", "raw_text": response.text if 'response' in locals() else ''}
    except Exception as e:
        # Catch other potential errors (API connection, configuration, etc.)
        print(f"Error during Gemini API call or processing: {e}")
        # Avoid leaking sensitive details in error messages if possible
        return {"error": "An error occurred during image analysis."}

def categorize_condition(description):
    description_lower = description.lower() if description else ""
    fair_keywords = ["crack", "shatter", "broken", "major dent", "heavy wear", "missing", "deep scratch", "water damage", "bent"]
    great_keywords = ["like new", "pristine", "excellent", "no visible marks", "minimal wear", "very clean"]
    good_keywords = ["minor scratch", "scuff", "small dent", "moderate wear", "some signs of use", "good condition"]
    # Order matters: check for worst conditions first
    if any(k in description_lower for k in fair_keywords): return "fair"
    if any(k in description_lower for k in great_keywords): return "great"
    if any(k in description_lower for k in good_keywords): return "good"
    return "good" # Default if nothing specific matches

def get_price_estimate(device_type, condition_category, price_db):
    device_lower = device_type.lower().strip() if device_type else "unknown"
    # Handle cases where Gemini might return 'unknown' or an unexpected type
    if device_lower not in price_db:
        device_lower = "unknown"

    device_prices = price_db.get(device_lower, price_db["unknown"]) # Fallback to unknown prices if type missing
    price_range = device_prices.get(condition_category, device_prices["fair"]) # Fallback to fair price if category missing

    if price_range and len(price_range) == 2:
        return f"${price_range[0]} - ${price_range[1]}"
    else:
        # Ultimate fallback if structure is broken
        return "$1 - $5 (Error)"
# --- End Helper Functions ---

# Initialize Flask App
app = Flask(__name__)
# Allow requests from your frontend domain on Render (and maybe localhost for testing)
# IMPORTANT: Replace 'https://your-frontend-name.onrender.com' with your ACTUAL frontend URL later
# For now, allowing '*' is okay for initial setup, but less secure.
CORS(app) # Allow all origins for now during setup

# Simple route to check if the backend is running
@app.route('/')
def home():
    return "E-Waste Estimator Backend is Alive!"

# The main endpoint for estimation
@app.route('/estimate', methods=['POST'])
def handle_estimation():
    if 'image' not in request.files:
        return jsonify({"error": "No image file part in the request."}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No image file selected."}), 400

    try:
        img_data = file.read()
        # Optional: Get text data if you added those fields
        # brand = request.form.get('brand', '')
        # model = request.form.get('model', '')
        # issues = request.form.get('issues', '')

        # Call Gemini for analysis
        analysis_result = analyze_image_with_gemini(img_data)

        # Check for errors returned from the analysis function
        if analysis_result.get("error"):
            print(f"Analysis Error Reported: {analysis_result['error']}")
            # Return a 500 Internal Server Error status code for server-side issues
            return jsonify({"error": analysis_result['error']}), 500

        # Process successful analysis
        device_type = analysis_result.get("device_type", "unknown")
        condition_desc = analysis_result.get("condition_description", "")
        extracted_text = analysis_result.get("extracted_text", "")

        # Categorize condition based on description
        condition_category = categorize_condition(condition_desc)
        # TODO: Optionally override category based on user 'issues' input if implemented

        # Get price range
        price = get_price_estimate(device_type, condition_category, PRICE_STRUCTURE)

        # Prepare useful info string for frontend
        detected_info = f"Detected: {device_type.capitalize()} | Assessed Condition: {condition_category.capitalize()}"
        if extracted_text:
            detected_info += f" | Extracted Text: '{extracted_text}'"

        # Send success response
        return jsonify({
            "estimated_price": price,
            "detected_info": detected_info
        })

    except Exception as e:
        # Catch any other unexpected errors during processing
        print(f"Unexpected error in /estimate endpoint: {e}")
        # Be careful not to expose too much detail in production errors
        return jsonify({"error": "An unexpected error occurred processing the request."}), 500

# Note: The following block is NOT used by Gunicorn on Render
# if __name__ == '__main__':
#    app.run(debug=True) # For local testing only
