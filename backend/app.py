# Import necessary libraries
import os # To get environment variables (like the API key)
import google.generativeai as genai
from flask import Flask, request, render_template, redirect, url_for, flash # Flask is for the web app part
from PIL import Image # To handle images
import io # To handle image data in memory
import json # To work with Gemini's JSON response
# NOTE: No 'files' or 'userdata' import needed here - that's Colab-specific

# --- Configuration ---

# Initialize the Flask app
app = Flask(__name__)
# Add a secret key for flashing messages (important for user feedback)
# You can replace 'your_very_secret_key_here' with any random string
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_very_secret_key_here')

# --- Gemini API Configuration ---
# IMPORTANT: We get the API key from Render's Environment Variables, NOT Colab secrets
API_KEY = os.environ.get('GOOGLE_API_KEY')
model = None # Initialize model as None

if not API_KEY:
    print("🚨 FATAL ERROR: GOOGLE_API_KEY environment variable not set.")
    # In a real app, you might prevent it from starting fully
else:
    try:
        genai.configure(api_key=API_KEY)
        # Initialize the Gemini Model (using the same one as before)
        model = genai.GenerativeModel('gemini-1.5-flash')
        print(f"✅ Gemini API Key configured and model loaded: {model.model_name}")
    except Exception as e:
        print(f"🚨 ERROR configuring Gemini API or loading model: {e}")
        # Model remains None if configuration fails

# --- E-Waste Price Structure (Same as before) ---
PRICE_STRUCTURE = {
    "smartphone": {"fair": [10, 50], "good": [51, 150], "great": [151, 400]},
    "laptop": {"fair": [30, 100], "good": [101, 350], "great": [351, 800]},
    "tablet": {"fair": [20, 70], "good": [71, 200], "great": [201, 500]},
    "monitor": {"fair": [5, 25], "good": [26, 75], "great": [76, 150]},
    "keyboard": {"fair": [1, 5], "good": [6, 15], "great": [16, 40]},
    "mouse": {"fair": [1, 5], "good": [6, 15], "great": [16, 35]},
    "unknown": {"fair": [1, 10], "good": [1, 10], "great": [1, 10]}
}
print("✅ Price structure defined.")

# --- Helper Functions (Adapted from Colab) ---

# analyze_image_with_gemini: Takes image *bytes* now, not Colab data
def analyze_image_with_gemini(image_bytes, gen_model):
    if not image_bytes:
        print("⚠️ analyze_image_with_gemini: No image bytes provided.")
        return None
    if not gen_model:
        print("⚠️ analyze_image_with_gemini: Gemini model not available.")
        return {"error": "Gemini model not configured on server."} # Return error info

    try:
        img_pil = Image.open(io.BytesIO(image_bytes))

        prompt = """
        Analyze the following image of an electronic waste item.
        Provide your response ONLY as a valid JSON object with the following keys:
        - "device_type": Identify the main type of device (e.g., smartphone, laptop, tablet, monitor, keyboard, mouse, other, unknown). Use lowercase. If unsure, use "unknown".
        - "condition_description": Briefly describe the visible physical condition (e.g., scratches, cracks, dents, wear, cleanliness). Be objective.
        - "extracted_text": Extract any clearly visible brand name or model number text, if present. If none is clearly visible, use an empty string "".

        Example JSON output:
        {"device_type": "smartphone", "condition_description": "Screen appears cracked...", "extracted_text": "iPhone"}
        """

        print("⏳ Sending image to Gemini...")
        response = gen_model.generate_content([prompt, img_pil], stream=False)
        response.resolve()
        print("✅ Received response from Gemini.")

        # Clean potential markdown fences and extract JSON
        cleaned_text = response.text.strip().removeprefix('```json').removesuffix('```').strip()
        start_index = cleaned_text.find('{')
        end_index = cleaned_text.rfind('}')

        if start_index != -1 and end_index != -1 and start_index < end_index:
            json_text = cleaned_text[start_index:end_index+1]
            result_json = json.loads(json_text)
            print("✅ Successfully parsed JSON response.")
            return result_json
        else:
            print("⚠️ Warning: Could not find valid JSON structure '{...}' in the response.")
            print(f"Raw response was: {response.text}")
            return {"error": "Gemini response was not valid JSON.", "raw_text": response.text}

    except json.JSONDecodeError as json_err:
        print(f"⚠️ Warning: Gemini did not return valid JSON. Error: {json_err}")
        print(f"Raw response text was:\n---\n{response.text}\n---")
        return {"error": "Failed to parse Gemini JSON response.", "raw_text": response.text}
    except (genai.types.generation_types.BlockedPromptException, genai.types.generation_types.StopCandidateException) as safety_err:
         print(f"🚨 ERROR: Gemini API safety block or stop: {safety_err}")
         return {"error": f"Analysis blocked by content safety filter: {safety_err}"}
    except Exception as e:
        # Catching potential errors like invalid image data for PIL
        if "cannot identify image file" in str(e):
            print(f"🚨 ERROR: Could not process the uploaded file as an image: {e}")
            return {"error": "Invalid image file format. Please upload JPEG, PNG, etc."}
        else:
            print(f"🚨 An error occurred during Gemini API call or image processing: {e}")
            return {"error": f"An unexpected error occurred during analysis: {e}"}

# categorize_condition: (Mostly unchanged, added print for clarity)
def categorize_condition(description):
    description_lower = description.lower() if description else ""
    if not description_lower: return "fair" # Default

    fair_keywords = ["crack", "shatter", "broken", "major dent", "heavy wear", "missing", "doesn't power", "water damage", "deep scratch", "severe", "unusable", "parts only"]
    great_keywords = ["like new", "pristine", "excellent", "no visible marks", "minimal wear", "mint"]
    good_keywords = ["minor scratch", "scuff", "small dent", "moderate wear", "fully functional", "good condition", "some wear", "cosmetic"]

    if any(keyword in description_lower for keyword in fair_keywords):
        print("Condition categorized as: fair")
        return "fair"
    elif any(keyword in description_lower for keyword in great_keywords):
        if not any(keyword in description_lower for keyword in good_keywords + fair_keywords if keyword not in great_keywords):
            print("Condition categorized as: great")
            return "great"
        else:
            print("Condition categorized as: good (mixed great/other signals)")
            return "good"
    elif any(keyword in description_lower for keyword in good_keywords):
        print("Condition categorized as: good")
        return "good"
    else:
        print("Condition categorized as: good (default - no strong keywords)")
        return "good"

# get_price_estimate: (Mostly unchanged, added print for clarity)
def get_price_estimate(device_type, condition_category, price_db):
    device_type_lower = device_type.lower().strip() if device_type else "unknown"

    # Basic normalization
    if "laptop" in device_type_lower: device_type_lower = "laptop"
    elif "smart phone" in device_type_lower or "cell phone" in device_type_lower: device_type_lower = "smartphone"
    elif "computer monitor" in device_type_lower: device_type_lower = "monitor"

    if device_type_lower not in price_db:
        print(f"⚠️ Device type '{device_type}' (normalized to '{device_type_lower}') not found. Using 'unknown'.")
        device_type_lower = "unknown"

    category_prices = price_db.get(device_type_lower, {})
    price_range = category_prices.get(condition_category)

    if price_range and len(price_range) == 2:
        estimate = f"${price_range[0]} - ${price_range[1]}"
        print(f"Price estimate for {device_type_lower}/{condition_category}: {estimate}")
        return estimate
    else:
        fallback_range = price_db.get("unknown", {}).get("fair", [1, 10])
        estimate = f"${fallback_range[0]} - ${fallback_range[1]} (Default Fallback)"
        print(f"⚠️ Price range not found for {device_type_lower}/{condition_category}. Using fallback: {estimate}")
        return estimate

# --- Flask Routes (Web Page Logic) ---

# Route for the main page (/)
@app.route('/', methods=['GET'])
def index():
    # Just show the HTML page
    # 'index.html' is the name of our HTML file in the 'templates' folder
    return render_template('index.html')

# Route to handle the image upload and analysis (/analyze)
@app.route('/analyze', methods=['POST'])
def analyze():
    global model # Make sure we're using the globally loaded model

    # 1. Check if Gemini model is ready
    if model is None:
        flash("🚨 Error: The analysis service is not configured correctly on the server. Missing API Key?", "error")
        return redirect(url_for('index')) # Go back to the main page

    # 2. Check if a file was uploaded in the form
    if 'image_file' not in request.files:
        flash("⚠️ Please select an image file to upload.", "warning")
        return redirect(url_for('index'))

    file = request.files['image_file']

    # 3. Check if the filename is empty (user didn't select a file)
    if file.filename == '':
        flash("⚠️ No file selected. Please choose an image.", "warning")
        return redirect(url_for('index'))

    # 4. Check if the file seems like an image (basic check)
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        flash("⚠️ Invalid file type. Please upload an image (png, jpg, jpeg, gif, webp).", "error")
        return redirect(url_for('index'))

    # 5. Try to read the file data
    try:
        image_bytes = file.read()
        print(f"✅ Image '{file.filename}' read successfully ({len(image_bytes)} bytes).")
    except Exception as e:
        print(f"🚨 Error reading uploaded file: {e}")
        flash(f"🚨 Error reading uploaded file: {e}", "error")
        return redirect(url_for('index'))

    # 6. Analyze the image with Gemini
    analysis_result = analyze_image_with_gemini(image_bytes, model)

    # 7. Process the results
    if analysis_result and 'error' not in analysis_result:
        # Success! Extract info, categorize, estimate price
        device_type = analysis_result.get("device_type", "unknown")
        condition_description = analysis_result.get("condition_description", "N/A")
        extracted_text = analysis_result.get("extracted_text", "None")
        if not device_type: device_type = "unknown"
        if not extracted_text: extracted_text = "None"

        condition_category = categorize_condition(condition_description)
        estimated_price = get_price_estimate(device_type, condition_category, PRICE_STRUCTURE)

        # Prepare results to show on the webpage
        results_data = {
            "device_type": device_type.capitalize(),
            "condition_description": condition_description,
            "extracted_text": extracted_text,
            "condition_category": condition_category.capitalize(),
            "estimated_price": estimated_price,
            "success": True
        }
        flash("✅ Analysis complete!", "success")
        # Send results back to the same HTML page to be displayed
        return render_template('index.html', results=results_data)

    else:
        # Handle errors from Gemini analysis
        error_message = "🚨 Analysis failed."
        if analysis_result and 'error' in analysis_result:
            error_message += f" Reason: {analysis_result['error']}"
            if 'raw_text' in analysis_result:
                 # Optionally show raw text if debugging needed, but maybe not to end user
                 # error_message += f" Raw Response: {analysis_result['raw_text'][:100]}..."
                 pass
        elif not analysis_result:
             error_message += " Could not get any response from the analysis service."

        flash(error_message, "error")
        return redirect(url_for('index')) # Go back to main page on failure


# --- Main execution block ---
# This part is needed to run the app locally for testing,
# but Render uses Gunicorn (specified in Procfile) instead.
if __name__ == '__main__':
    # Use port provided by environment or default to 5000
    port = int(os.environ.get('PORT', 5000))
    # Run the Flask app.
    # debug=False is important for production (Render)
    # host='0.0.0.0' makes it accessible on the network
    app.run(host='0.0.0.0', port=port, debug=False)
