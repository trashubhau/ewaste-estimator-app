# backend/app.py
# ============================================
#      COMPLETE CODE FOR app.py
# ============================================

import os
import io
import json
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS # For allowing frontend to talk to backend
from PIL import Image
import traceback # Optional: for more detailed error logging

# --- Price Structure Definition ---
# Define your price ranges here
PRICE_STRUCTURE = {
    "smartphone": {"fair": [10, 50], "good": [51, 150], "great": [151, 400]},
    "laptop": {"fair": [30, 100], "good": [101, 350], "great": [351, 800]},
    "tablet": {"fair": [20, 70], "good": [71, 200], "great": [201, 500]},
    "monitor": {"fair": [5, 25], "good": [26, 75], "great": [76, 150]},
    "keyboard": {"fair": [1, 5], "good": [6, 15], "great": [16, 40]},
    "mouse": {"fair": [1, 5], "good": [6, 15], "great": [16, 35]},
    "unknown": {"fair": [1, 10], "good": [1, 10], "great": [1, 10]} # Fallback
}

# --- Helper Function: Gemini Analysis ---
def analyze_image_with_gemini(image_data):
    """Sends image data to Gemini for analysis and returns parsed JSON or error dict."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("FATAL ERROR: GEMINI_API_KEY environment variable not set on the server.")
        # Note: This error will likely prevent the app from starting if key is missing during init sometimes
        return {"error": "Server configuration error: API key missing."}
    try:
        # Configure the API key for this specific call (safer if app runs multiple things)
        genai.configure(api_key=api_key)
        # Choose a model that supports vision input
        model = genai.GenerativeModel('gemini-1.5-flash') # Or 'gemini-pro-vision'
        
        img_pil = Image.open(io.BytesIO(image_data))

        # Define the prompt asking for structured JSON output
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
        
        # Make the API call
        print("DEBUG: Sending request to Gemini API...")
        response = model.generate_content([prompt, img_pil], stream=False)
        response.resolve() # Ensure response is fully processed
        print("DEBUG: Received response from Gemini API.")

        # Clean potential markdown formatting around the JSON
        cleaned_text = response.text.strip().lstrip('```json').rstrip('```').strip()
        if not cleaned_text:
            print("Warning: Gemini returned empty response text.")
            return {"error": "Analysis returned no content."}

        # Parse the cleaned text as JSON
        return json.loads(cleaned_text)

    except json.JSONDecodeError as json_err:
        # Handle cases where Gemini response wasn't valid JSON
        print(f"Error decoding Gemini JSON response: {json_err}")
        raw_response = response.text if 'response' in locals() else 'N/A'
        print(f"Raw response text: {raw_response}")
        return {"error": "Failed to parse analysis result.", "raw_text": raw_response}
    except Exception as e:
        # Handle other potential errors (API connection, model issues, configuration)
        print(f"Error during Gemini API call or processing: {e}")
        # Log detailed traceback on the server for debugging
        traceback.print_exc()
        return {"error": "An error occurred during image analysis."}

# --- Helper Function: Condition Categorization ---
def categorize_condition(description):
    """Categorizes condition based on keywords in the description."""
    description_lower = description.lower() if description else ""
    # Define keywords for ranking condition (most severe first)
    fair_keywords = ["crack", "shatter", "broken", "major dent", "heavy wear", "missing", "deep scratch", "water damage", "bent", "severe damage"]
    great_keywords = ["like new", "pristine", "excellent", "no visible marks", "minimal wear", "very clean", "mint condition"]
    good_keywords = ["minor scratch", "scuff", "small dent", "moderate wear", "some signs of use", "good condition", "fully functional"]
    
    # Check in order of severity
    if any(k in description_lower for k in fair_keywords): return "fair"
    # Check for great only if no fair keywords found
    if any(k in description_lower for k in great_keywords): return "great"
     # Check for good only if no fair/great keywords found
    if any(k in description_lower for k in good_keywords): return "good"
    
    # Default if no specific keywords match
    print(f"DEBUG: No strong condition keywords matched for description: '{description_lower[:100]}...'. Defaulting to 'good'.")
    return "good"

# --- Helper Function: Price Lookup ---
def get_price_estimate(device_type, condition_category, price_db):
    """Retrieves the price range from the defined structure with fallbacks."""
    device_lower = device_type.lower().strip() if device_type else "unknown"
    
    # Fallback to "unknown" if the detected type isn't in our price structure
    if device_lower not in price_db:
        print(f"Warning: Device type '{device_lower}' not found in price structure. Using 'unknown'.")
        device_lower = "unknown"

    # Get prices for the device type, fallback to unknown prices if needed
    device_prices = price_db.get(device_lower, price_db["unknown"])
    
    # Get specific price range for the category, fallback to 'fair' price for that device type if category is invalid
    price_range = device_prices.get(condition_category, device_prices["fair"])

    # Format the price range string, with a final safety net
    if price_range and len(price_range) == 2:
        return f"${price_range[0]} - ${price_range[1]}"
    else:
        # This should ideally not happen if PRICE_STRUCTURE is well-formed
        print(f"ERROR: Invalid price range found for {device_lower}/{condition_category}. Using hardcoded fallback.")
        return "$1 - $5 (Error)"

# ============================================
#      Flask App Initialization & Routes
# ============================================

# Initialize Flask App
app = Flask(__name__)

# Enable CORS - Allow requests from your frontend domain
# Replace '*' with your specific frontend URL in production for better security
# e.g., origins="https://your-frontend-name.onrender.com"
CORS(app) # Allows all origins for now

# --- Home Route (Basic Health Check) ---
@app.route('/')
def home():
    """Simple route to confirm the backend is running."""
    print("DEBUG: Request received for / route")
    return "E-Waste Estimator Backend is Alive!"

# --- Estimation Route (Handles GET and POST) ---
@app.route('/estimate', methods=['GET', 'POST']) # Allow both GET and POST
def handle_estimation():
    """Handles GET requests with info and POST requests for image analysis."""
    
    # --- Handle GET Requests ---
    if request.method == 'GET':
        print("DEBUG: GET request received for /estimate")
        # Return an informational message for GET requests
        return jsonify({
            "message": "This endpoint estimates e-waste value via POST requests with image data.",
            "usage": "Send a POST request using multipart/form-data including an 'image' file part.",
            "status": "Ready for POST requests."
        }), 200 # OK status for GET

    # --- Handle POST Requests (Genuine Logic) ---
    # If not GET, it must be POST because of methods=['GET', 'POST']
    print("DEBUG: POST request received for /estimate")
    # Check if the 'image' file part is in the request
    if 'image' not in request.files:
        print("ERROR: 'image' file part missing in POST request.")
        return jsonify({"error": "No image file part in the request."}), 400 # Bad Request

    file = request.files['image']
    # Check if a filename exists (means a file was actually selected)
    if file.filename == '':
        print("ERROR: No file selected in POST request.")
        return jsonify({"error": "No image file selected."}), 400 # Bad Request

    # Process the image file
    try:
        print(f"DEBUG: Processing uploaded file: {file.filename}")
        img_data = file.read() # Read file content into memory

        # Optional: Retrieve text data if sent from frontend
        # brand = request.form.get('brand', '')
        # model = request.form.get('model', '')
        # issues = request.form.get('issues', '')
        # print(f"DEBUG: Optional data - Brand: {brand}, Model: {model}, Issues: {issues}")

        # Call Gemini for analysis
        print("DEBUG: Calling analyze_image_with_gemini...")
        analysis_result = analyze_image_with_gemini(img_data)
        # Log the full analysis result for easier debugging if needed
        print(f"DEBUG: Raw analysis result from helper: {analysis_result}")

        # Check for errors returned from the analysis helper function
        if not analysis_result or analysis_result.get("error"):
            error_msg = analysis_result.get("error", "Analysis failed without specific error.") if analysis_result else "Analysis failed: No result."
            print(f"ERROR: Analysis Helper Function Error: {error_msg}")
            # Return 500 Internal Server Error for issues during backend processing/API calls
            return jsonify({"error": error_msg}), 500

        # Extract data from successful analysis
        device_type = analysis_result.get("device_type", "unknown")
        condition_desc = analysis_result.get("condition_description", "")
        extracted_text = analysis_result.get("extracted_text", "")
        print(f"DEBUG: Parsed Analysis - Type: {device_type}, Condition Desc: '{condition_desc[:50]}...', Text: '{extracted_text}'")

        # Categorize condition based on Gemini's description
        condition_category = categorize_condition(condition_desc)
        print(f"DEBUG: Categorized condition as: {condition_category}")
        # Future Enhancement: Combine with 'issues' input from user if available

        # Get price range based on type and category
        price = get_price_estimate(device_type, condition_category, PRICE_STRUCTURE)
        print(f"DEBUG: Calculated estimated price range: {price}")

        # Prepare informative string for the frontend
        detected_info = f"Detected: {device_type.capitalize()} | Assessed Condition: {condition_category.capitalize()}"
        if extracted_text:
            detected_info += f" | Extracted Text: '{extracted_text}'"

        # Send successful response back to the frontend
        print("DEBUG: Sending successful POST response.")
        return jsonify({
            "estimated_price": price,
            "detected_info": detected_info
        }), 200 # OK status for successful POST

    except FileNotFoundError:
         # This shouldn't happen with request.files but added as safety
         print(f"ERROR: File not found during processing - unexpected.")
         return jsonify({"error": "File processing error."}), 500
    except Exception as e:
        # Catch any other unexpected errors during POST processing
        print(f"ERROR: Unexpected error in /estimate POST handler: {e}")
        # Log the full traceback to the server logs for detailed debugging
        traceback.print_exc()
        return jsonify({"error": "An unexpected server error occurred. Please try again later."}), 500

# ============================================
#      End of app.py
# ============================================
